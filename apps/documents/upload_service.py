# apps/documents/upload_service.py
"""
Document upload service for claim documents.

The bytes go to SharePoint (via ClaimDocument.file → SharePointStorage).
Only metadata is kept in Postgres. This service never touches
``FileField.path`` — SharePointStorage raises ``NotImplementedError``
for cloud files, so only ``.url``, ``.open('rb')``, ``.storage.exists``,
``.storage.size``, and ``.storage.delete`` are used.
"""

import logging
import mimetypes
import os

from django.utils import timezone

from apps.claims.models import Claim, ClaimDocument

logger = logging.getLogger(__name__)


class DocumentUploadService:
    """Handles document upload, listing, and verification for claims."""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    ALLOWED_EXTENSIONS = [
        'pdf', 'jpg', 'jpeg', 'png',
        'doc', 'docx', 'xls', 'xlsx', 'txt',
    ]

    # ---------------------------------------------------------------- #
    # UPLOAD
    # ---------------------------------------------------------------- #

    def upload_claim_document(
        self,
        *,
        file,
        document_type: str,
        claim: Claim,
        user,
        claim_number: str = None,
    ) -> dict:
        """
        Persist a document for a claim.

        The bytes are written through ``ClaimDocument.file``, which is
        backed by ``SharePointStorage``. Postgres only stores the
        relative path plus metadata.

        Returns:
            dict: {
                "success": True,
                "document_id": int,
                "file_url": str,
                "file_name": str,
                "message": str,
            }
            or
            {"success": False, "error": "..."}
        """
        try:
            # ---- Validate ----
            if file is None:
                return {"success": False, "error": "No file provided."}

            size = getattr(file, "size", None) or 0
            if size <= 0:
                return {"success": False, "error": "File is empty."}

            if size > self.MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": (
                        f"File too large. Maximum size is "
                        f"{self.MAX_FILE_SIZE // (1024 * 1024)}MB."
                    ),
                }

            ext = self._extension(file.name)
            if ext not in self.ALLOWED_EXTENSIONS:
                return {
                    "success": False,
                    "error": (
                        f"File type '{ext}' is not allowed. "
                        f"Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"
                    ),
                }

            document_name = os.path.basename(file.name)

            # ---- Persist ----
            # The FileField's storage (SharePointStorage) uploads the
            # bytes; the DB stores the relative path returned by
            # get_available_name().
            with transaction.atomic():
                doc = ClaimDocument.objects.create(
                    claim=claim,
                    document_type=document_type,
                    document_name=document_name,
                    file=file,
                    file_size=size,
                    file_extension=ext,
                    uploaded_by=(
                        user
                        if getattr(user, "is_authenticated", False)
                        else None
                    ),
                )

            # ---- Build the download URL ----
            file_url = None
            try:
                file_url = doc.file.url
            except Exception:
                logger.exception(
                    "Could not resolve URL for uploaded document %s", doc.id
                )

            logger.info(
                "Uploaded document %s for claim %s (%s, %d bytes, backend=%s)",
                doc.id, claim.no, document_name, size,
                getattr(doc, "storage_backend", "sharepoint"),
            )

            return {
                "success": True,
                "document_id": doc.id,
                "claim_id": claim.id,
                "claim_no": claim.no,
                "claim_number": claim_number,
                "document_type": doc.document_type,
                "document_type_display": doc.get_document_type_display(),
                "document_name": doc.document_name,
                "file_name": doc.document_name,
                "file_size": doc.file_size,
                "file_extension": doc.file_extension,
                "storage_backend": getattr(
                    doc, "storage_backend", "sharepoint"
                ),
                "file_url": file_url,
                "uploaded_at": doc.uploaded_at.isoformat(),
                "message": "Document uploaded successfully",
            }

        except Exception as exc:
            logger.exception(
                "Document upload failed for claim %s", getattr(claim, "id", "?")
            )
            return {"success": False, "error": str(exc)}

    # ---------------------------------------------------------------- #
    # LIST
    # ---------------------------------------------------------------- #

    def get_claim_documents(self, claim_id: int, claim_number: str = None):
        """
        Return a list of dicts describing the documents attached to a
        claim. Never touches ``file.path``.
        """
        docs = (
            ClaimDocument.objects
            .filter(claim_id=claim_id)
            .select_related("claim", "uploaded_by", "verified_by")
            .order_by("-uploaded_at")
        )

        results = []
        for doc in docs:
            url = None
            if doc.file:
                try:
                    url = doc.file.url
                except Exception:
                    logger.warning(
                        "Could not resolve URL for document %s", doc.id
                    )

            results.append({
                "id": doc.id,
                "claim": doc.claim_id,
                "claim_no": doc.claim.no if doc.claim else None,
                "document_type": doc.document_type,
                "document_type_display": doc.get_document_type_display(),
                "document_name": doc.document_name,
                "file_name": doc.document_name,
                "file_url": url,
                "file_size": doc.file_size,
                "file_extension": doc.file_extension,
                "storage_backend": getattr(
                    doc, "storage_backend", "sharepoint"
                ),
                "uploaded_by": doc.uploaded_by_id,
                "uploaded_by_name": (
                    doc.uploaded_by.get_full_name()
                    if doc.uploaded_by else None
                ),
                "uploaded_at": doc.uploaded_at.isoformat(),
                "is_verified": doc.is_verified,
                "verified_by": doc.verified_by_id,
                "verified_by_name": (
                    doc.verified_by.get_full_name()
                    if doc.verified_by else None
                ),
                "verified_at": (
                    doc.verified_at.isoformat() if doc.verified_at else None
                ),
                "verification_notes": doc.verification_notes,
                "is_rejected": doc.is_rejected,
                "rejection_reason": doc.rejection_reason,
                "version": doc.version,
                "is_latest": doc.is_latest,
            })

        return results

    # ---------------------------------------------------------------- #
    # VERIFY
    # ---------------------------------------------------------------- #

    def verify_document(self, document_id: int, user) -> ClaimDocument:
        """Mark a document as verified and return the instance."""
        doc = ClaimDocument.objects.get(id=document_id)
        doc.is_verified = True
        doc.verified_by = user
        doc.verified_at = timezone.now()
        doc.save(update_fields=["is_verified", "verified_by", "verified_at"])
        return doc

    # ---------------------------------------------------------------- #
    # HELPERS
    # ---------------------------------------------------------------- #

    @staticmethod
    def _extension(filename: str) -> str:
        if not filename or "." not in filename:
            return ""
        return filename.rsplit(".", 1)[-1].lower()
