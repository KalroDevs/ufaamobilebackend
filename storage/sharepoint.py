"""
SharePoint storage backend for Django using Microsoft Graph API.

Includes local storage delegation for admin interface media (favicons, logos)
to ensure admin login pages render instantly without Microsoft Graph dependencies.

Requires in settings.py (or .env):
    SHAREPOINT_URL              e.g. https://your-domain.sharepoint.com
    SHAREPOINT_SITE             e.g. /sites/UFAA
    SHAREPOINT_DOCUMENT_LIBRARY e.g. Claim Documents
    SHAREPOINT_TENANT_ID
    SHAREPOINT_CLIENT_ID
    SHAREPOINT_CLIENT_SECRET
    SHAREPOINT_FILE_OVERWRITE   e.g. False (optional, default False)
    SHAREPOINT_LOCAL_PREFIXES   e.g. ["admin-interface/", "admin/"] (optional)

Azure AD app must have APPLICATION permissions (admin-consented):
    Sites.ReadWrite.All
    Files.ReadWrite.All
"""

import logging
import mimetypes
import os
from tempfile import SpooledTemporaryFile
from urllib.parse import quote

import msal
import requests
from django.conf import settings
from django.core.cache import cache
from django.core.files import File
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


@deconstructible
class LocalAdminThemeStorage(FileSystemStorage):
    """
    Dedicated local storage backend for admin theme media (favicons, logos).
    Forces files to be saved on local disk under MEDIA_ROOT/admin-interface/.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("location", getattr(settings, "MEDIA_ROOT", ""))
        kwargs.setdefault("base_url", getattr(settings, "MEDIA_URL", "/media/"))
        super().__init__(**kwargs)


@deconstructible
class SharePointStorage(Storage):
    """
    Django storage backend that stores files in a SharePoint document library
    via Microsoft Graph API, with automatic local fallback for admin theme media.
    """

    SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024  # 4 MB limit for simple PUT
    UPLOAD_CHUNK_SIZE = 16 * 320 * 1024  # 5.24 MB (must be multiple of 320 KiB)
    
    # Timeouts: (connect, read)
    HTTP_TIMEOUT = (10, 120)
    URL_HTTP_TIMEOUT = (2, 4)  # Fast timeout for URL resolution to avoid hanging login pages

    def __init__(self, **kwargs):
        self.site_url = (getattr(settings, "SHAREPOINT_URL", "") or "").rstrip("/")
        self.site_path = (getattr(settings, "SHAREPOINT_SITE", "") or "").strip("/")
        self.library_name = getattr(settings, "SHAREPOINT_DOCUMENT_LIBRARY", "") or ""
        self.tenant_id = getattr(settings, "SHAREPOINT_TENANT_ID", "") or ""
        self.client_id = getattr(settings, "SHAREPOINT_CLIENT_ID", "") or ""
        self.client_secret = getattr(settings, "SHAREPOINT_CLIENT_SECRET", "") or ""
        self.file_overwrite = getattr(settings, "SHAREPOINT_FILE_OVERWRITE", False)

        # Paths that bypass SharePoint and remain on local disk (e.g. django-admin-interface assets)
        default_local_prefixes = ["admin-interface/", "admin/"]
        configured_prefixes = getattr(settings, "SHAREPOINT_LOCAL_PREFIXES", default_local_prefixes)
        self.local_prefixes = [p.strip("/") + "/" for p in configured_prefixes]

        self._local_storage = FileSystemStorage()
        self._site_id = None
        self._drive_id = None

    def _is_local_path(self, name):
        """Check if a path should be handled by local storage instead of SharePoint."""
        clean = self._clean_name(name)
        return any(clean.startswith(prefix) for prefix in self.local_prefixes)

    # ------------------------------------------------------------------ #
    # Authentication & Graph Setup
    # ------------------------------------------------------------------ #
    def _get_access_token(self):
        """Get a valid Graph API access token using Django cache."""
        cache_key = f"sharepoint_token_{self.client_id}"
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise RuntimeError(
                "SharePoint credentials incomplete. Verify SHAREPOINT_TENANT_ID, "
                "SHAREPOINT_CLIENT_ID, and SHAREPOINT_CLIENT_SECRET in settings."
            )

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority,
        )

        result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)

        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            description = result.get("error_description", "No description")
            raise RuntimeError(
                f"Failed to acquire SharePoint token: {error} - {description}"
            )

        token = result["access_token"]
        expires_in = int(result.get("expires_in", 3600)) - 120  # 2-minute safety margin
        cache.set(cache_key, token, timeout=max(60, expires_in))

        return token

    def _headers(self, content_type=None):
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _get_hostname(self):
        return (
            self.site_url.replace("https://", "")
            .replace("http://", "")
            .rstrip("/")
        )

    def _get_site_id(self):
        if self._site_id:
            return self._site_id

        hostname = self._get_hostname()
        path = self.site_path.strip("/")
        url = f"{GRAPH_BASE}/sites/{hostname}:/{path}"

        r = requests.get(url, headers=self._headers(), timeout=self.HTTP_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(
                f"Could not resolve SharePoint site ({r.status_code}): {r.text}. URL: {url}"
            )

        self._site_id = r.json()["id"]
        return self._site_id

    def _get_drive_id(self):
        if self._drive_id:
            return self._drive_id

        site_id = self._get_site_id()
        url = f"{GRAPH_BASE}/sites/{site_id}/drives"

        r = requests.get(url, headers=self._headers(), timeout=self.HTTP_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"Could not list drives ({r.status_code}): {r.text}")

        drives = r.json().get("value", [])
        target = self.library_name.lower()

        for drive in drives:
            if (drive.get("name") or "").lower() == target:
                self._drive_id = drive["id"]
                return self._drive_id

        available = [d.get("name") for d in drives]
        raise RuntimeError(
            f"Document library '{self.library_name}' not found. Available libraries: {available}"
        )

    # ------------------------------------------------------------------ #
    # Path Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean_name(name):
        return (name or "").replace("\\", "/").lstrip("/")

    def _item_url(self, name):
        drive_id = self._get_drive_id()
        clean = self._clean_name(name)
        if not clean:
            return f"{GRAPH_BASE}/drives/{drive_id}/root"
        encoded = quote(clean, safe="/")
        return f"{GRAPH_BASE}/drives/{drive_id}/root:/{encoded}"

    # ------------------------------------------------------------------ #
    # Django Storage API Implementation
    # ------------------------------------------------------------------ #
    def _save(self, name, content):
        if self._is_local_path(name):
            return self._local_storage._save(name, content)

        name = self._clean_name(name)
        content_type = (
            getattr(content, "content_type", None)
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream"
        )

        if hasattr(content, "size"):
            size = content.size
        else:
            content.seek(0, os.SEEK_END)
            size = content.tell()
            content.seek(0)

        if size <= self.SIMPLE_UPLOAD_MAX:
            self._simple_upload(name, content, content_type)
        else:
            self._chunked_upload(name, content, size, content_type)

        logger.info("[SharePoint] Saved '%s' (%d bytes)", name, size)
        return name

    def _simple_upload(self, name, content, content_type):
        url = f"{self._item_url(name)}:/content"
        content.seek(0)

        r = requests.put(
            url,
            headers=self._headers(content_type),
            data=content.read(),
            timeout=self.HTTP_TIMEOUT,
        )

        if r.status_code not in (200, 201):
            raise RuntimeError(f"SharePoint upload failed ({r.status_code}): {r.text}")

    def _chunked_upload(self, name, content, size, content_type):
        session_resp = requests.post(
            f"{self._item_url(name)}:/createUploadSession",
            headers=self._headers("application/json"),
            json={
                "item": {
                    "@microsoft.graph.conflictBehavior": "replace",
                    "name": os.path.basename(name),
                }
            },
            timeout=self.HTTP_TIMEOUT,
        )

        if session_resp.status_code != 200:
            raise RuntimeError(
                f"Could not create upload session ({session_resp.status_code}): {session_resp.text}"
            )

        upload_url = session_resp.json()["uploadUrl"]
        content.seek(0)
        offset = 0

        while offset < size:
            chunk = content.read(self.UPLOAD_CHUNK_SIZE)
            if not chunk:
                break

            chunk_len = len(chunk)
            end = offset + chunk_len - 1

            r = requests.put(
                upload_url,
                headers={
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
                data=chunk,
                timeout=self.HTTP_TIMEOUT,
            )

            if r.status_code not in (200, 201, 202):
                raise RuntimeError(
                    f"Chunk upload failed at offset {offset} ({r.status_code}): {r.text}"
                )

            offset += chunk_len

    def _open(self, name, mode="rb"):
        if self._is_local_path(name):
            return self._local_storage._open(name, mode)

        if "w" in mode or "a" in mode:
            raise NotImplementedError("SharePointStorage does not support write modes on _open.")

        r = requests.get(
            f"{self._item_url(name)}:/content",
            headers=self._headers(),
            timeout=self.HTTP_TIMEOUT,
            stream=True,
        )

        if r.status_code != 200:
            raise FileNotFoundError(f"SharePoint file not found: {name}")

        file_obj = SpooledTemporaryFile(max_size=10 * 1024 * 1024)
        for chunk in r.iter_content(chunk_size=8192):
            file_obj.write(chunk)
        file_obj.seek(0)

        return File(file_obj, name=name)

    def exists(self, name):
        if self._is_local_path(name):
            return self._local_storage.exists(name)

        if not name:
            return False
        try:
            r = requests.get(
                self._item_url(name),
                headers=self._headers(),
                timeout=self.HTTP_TIMEOUT,
            )
            return r.status_code == 200
        except Exception as e:
            logger.warning("[SharePoint] exists() error for '%s': %s", name, e)
            return False

    def delete(self, name):
        if self._is_local_path(name):
            return self._local_storage.delete(name)

        r = requests.delete(
            self._item_url(name),
            headers=self._headers(),
            timeout=self.HTTP_TIMEOUT,
        )
        if r.status_code not in (204, 404):
            raise RuntimeError(f"SharePoint delete failed ({r.status_code}): {r.text}")

    def size(self, name):
        if self._is_local_path(name):
            return self._local_storage.size(name)

        r = requests.get(
            self._item_url(name),
            headers=self._headers(),
            timeout=self.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            raise FileNotFoundError(name)
        return r.json().get("size", 0)

    def path(self, name):
        if self._is_local_path(name):
            return self._local_storage.path(name)
        raise NotImplementedError("This storage engine does not support local paths for cloud files.")

    def url(self, name):
        """
        Return a accessible URL. Uses local storage for admin media, or fetches
        a short-lived download link from Graph API for cloud files. Fully defensive
        to prevent login page crashes if Graph API fails.
        """
        if self._is_local_path(name):
            return self._local_storage.url(name)

        name = self._clean_name(name)
        cache_key = f"sharepoint_url_{name}"

        try:
            cached_url = cache.get(cache_key)
            if cached_url:
                return cached_url
        except Exception:
            pass

        try:
            r = requests.get(
                self._item_url(name),
                headers=self._headers(),
                timeout=self.URL_HTTP_TIMEOUT,  # Short timeout prevents HTTP hanging
            )

            if r.status_code == 200:
                download_url = r.json().get("@microsoft.graph.downloadUrl")
                if download_url:
                    try:
                        cache.set(cache_key, download_url, timeout=3000)
                    except Exception:
                        pass
                    return download_url

                logger.warning("[SharePoint] No downloadUrl found for '%s'", name)

        except Exception as e:
            logger.error("[SharePoint] Safe fallback in url('%s'): %s", name, e)

        # Defensive fallback: Returns local media URL so template rendering never raises 500
        return self._local_storage.url(name)

    def get_available_name(self, name, max_length=None):
        if self._is_local_path(name):
            return self._local_storage.get_available_name(name, max_length=max_length)

        if self.file_overwrite:
            self.delete(name)
            return self._clean_name(name)
        return super().get_available_name(self._clean_name(name), max_length=max_length)

    def get_valid_name(self, name):
        if self._is_local_path(name):
            return self._local_storage.get_valid_name(name)
        return self._clean_name(name)
