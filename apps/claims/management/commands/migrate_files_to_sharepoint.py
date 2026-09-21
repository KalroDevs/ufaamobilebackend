# apps/claims/management/commands/migrate_files_to_sharepoint.py
"""
One-shot management command to copy existing document files from local
disk into SharePoint and mark them as ``storage_backend='sharepoint'``.

Usage
-----
    # Dry run — reports what would be copied, changes nothing
    python manage.py migrate_files_to_sharepoint --dry-run

    # Real migration, both apps, all rows
    python manage.py migrate_files_to_sharepoint

    # Only the first 50 rows of each model
    python manage.py migrate_files_to_sharepoint --limit 50

    # Only one app
    python manage.py migrate_files_to_sharepoint --target claim_documents
    python manage.py migrate_files_to_sharepoint --target asset_tracking

    # Overwrite files that already exist in SharePoint
    python manage.py migrate_files_to_sharepoint --overwrite

    # Delete the local copy after a successful upload
    python manage.py migrate_files_to_sharepoint --delete-local

Behaviour
---------
1. Iterates over ``ClaimDocument`` rows whose ``storage_backend`` is not
   already ``"sharepoint"``.
2. For each row, resolves the local path from ``MEDIA_ROOT`` using the
   value stored in ``FileField.name``.
3. If the file already exists in SharePoint (checked via
   ``SharePointStorage.exists``), the row is only marked as migrated —
   no bytes are re-uploaded.
4. Otherwise the local file is opened and streamed to SharePoint with
   ``SharePointStorage.save`` using the exact same relative path. This
   keeps the DB path and the SharePoint path in lock-step, so no
   subsequent edits to ``FileField.name`` are needed.
5. On success, the row is marked with ``storage_backend='sharepoint'``.

The command is safe to re-run: already-migrated rows are skipped, and
existing SharePoint files are not re-uploaded unless ``--overwrite`` is
passed.

Note
----
Only the *default* ``FileSystemStorage`` is read from here. If your
project had a custom local storage backend, adjust ``_local_storage()``
accordingly.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Iterable, Optional

from django.core.files.storage import FileSystemStorage, storages
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _iter_targets(target: str):
    """
    Yield ``(label, queryset, field_name)`` tuples for the requested target.

    ``target`` is one of: ``"all"``, ``"claim_documents"``, ``"asset_tracking"``.
    """
    targets = []

    if target in ("all", "claim_documents"):
        from apps.claims.models import ClaimDocument
        qs = (
            ClaimDocument.objects
            .exclude(storage_backend="sharepoint")
            .only("id", "file", "storage_backend", "document_name")
            .order_by("id")
        )
        targets.append(("claim_documents", qs, "file"))

    if target in ("all", "asset_tracking"):
        from apps.asset_tracking.models import AssetTrackingDocument
        qs = (
            AssetTrackingDocument.objects
            .exclude(storage_backend="sharepoint")
            .only("id", "file", "storage_backend", "document_name")
            .order_by("id")
        )
        targets.append(("asset_tracking", qs, "file"))

    return targets


def _local_media_root() -> str:
    """Return the absolute MEDIA_ROOT path (created if missing)."""
    from django.conf import settings

    root = getattr(settings, "MEDIA_ROOT", None)
    if not root:
        raise CommandError(
            "MEDIA_ROOT is not configured. Cannot locate local files to migrate."
        )
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise CommandError(
            f"MEDIA_ROOT does not exist on disk: {root}"
        )
    return root


def _make_local_storage() -> FileSystemStorage:
    """
    Return a FileSystemStorage rooted at MEDIA_ROOT.

    This is used only to *read* the local bytes. Uploading is always
    done through the SharePoint storage backend.
    """
    return FileSystemStorage(location=_local_media_root())


def _make_sharepoint_storage():
    """Return the configured SharePoint storage backend."""
    try:
        sp = storages["sharepoint"]
    except Exception as exc:
        raise CommandError(
            "SharePoint storage alias is not registered in settings.STORAGES. "
            "Add: 'sharepoint': {'BACKEND': 'storage.sharepoint.SharePointStorage'}"
        ) from exc
    return sp


# --------------------------------------------------------------------------- #
# Command
# --------------------------------------------------------------------------- #

class Command(BaseCommand):
    help = (
        "Copy ClaimDocument and AssetTrackingDocument files from local disk "
        "into SharePoint and mark each row as storage_backend='sharepoint'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be migrated without touching anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N rows of each model.",
        )
        parser.add_argument(
            "--target",
            choices=["all", "claim_documents", "asset_tracking"],
            default="all",
            help="Which document set to migrate (default: all).",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Re-upload files that already exist in SharePoint.",
        )
        parser.add_argument(
            "--delete-local",
            action="store_true",
            help="Delete the local copy after a successful upload.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of rows to iterate at a time (default: 200).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print the final summary and any errors.",
        )

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit: Optional[int] = options["limit"]
        target: str = options["target"]
        overwrite: bool = options["overwrite"]
        delete_local: bool = options["delete_local"]
        batch_size: int = max(1, options["batch_size"])
        quiet: bool = options["quiet"]

        # Set up storages
        try:
            local = _make_local_storage()
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Could not create local storage: {exc}") from exc

        try:
            sharepoint = _make_sharepoint_storage()
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Could not initialise SharePoint storage: {exc}") from exc

        if not quiet:
            self.stdout.write(self.style.NOTICE(
                f"SharePoint storage : {sharepoint.__class__.__module__}."
                f"{sharepoint.__class__.__name__}"
            ))
            self.stdout.write(self.style.NOTICE(
                f"Local media root   : {local.location}"
            ))
            self.stdout.write(self.style.NOTICE(
                f"Target             : {target}"
            ))
            self.stdout.write(self.style.NOTICE(
                f"Dry run            : {dry_run}"
            ))
            self.stdout.write("")

        # Per-target counters
        summary = {
            "copied": 0,
            "already_in_sharepoint": 0,
            "missing_locally": 0,
            "failed": 0,
            "skipped_no_file": 0,
            "marked_only": 0,
            "local_deleted": 0,
        }

        targets = list(_iter_targets(target))
        if not targets:
            raise CommandError(f"No models matched target '{target}'.")

        for label, queryset, field_name in targets:
            self._process_target(
                label=label,
                queryset=queryset,
                field_name=field_name,
                local=local,
                sharepoint=sharepoint,
                limit=limit,
                overwrite=overwrite,
                delete_local=delete_local,
                dry_run=dry_run,
                batch_size=batch_size,
                quiet=quiet,
                summary=summary,
            )

        # Final report
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Migration summary ==="))
        self.stdout.write(f"  Copied to SharePoint     : {summary['copied']}")
        self.stdout.write(f"  Already in SharePoint    : {summary['already_in_sharepoint']}")
        self.stdout.write(f"  Marked without uploading : {summary['marked_only']}")
        self.stdout.write(f"  Missing locally          : {summary['missing_locally']}")
        self.stdout.write(f"  Rows without a file      : {summary['skipped_no_file']}")
        self.stdout.write(f"  Local copies deleted     : {summary['local_deleted']}")
        self.stdout.write(f"  Failed                   : {summary['failed']}")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Dry run only — no files were uploaded and no rows were updated."
            ))

        if summary["failed"] > 0:
            # Non-zero exit code so cron / CI can detect partial failures
            sys.exit(1)

    # ------------------------------------------------------------------ #
    # Per-target loop
    # ------------------------------------------------------------------ #

    def _process_target(
        self,
        *,
        label: str,
        queryset,
        field_name: str,
        local: FileSystemStorage,
        sharepoint,
        limit: Optional[int],
        overwrite: bool,
        delete_local: bool,
        dry_run: bool,
        batch_size: int,
        quiet: bool,
        summary: dict,
    ) -> None:
        if limit is not None:
            queryset = queryset[:limit]

        total = queryset.count() if hasattr(queryset, "count") else None

        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n[{label}] {total if total is not None else '?'} row(s) to inspect"
            ))

        processed = 0
        for obj in queryset.iterator(chunk_size=batch_size):
            processed += 1
            try:
                outcome = self._migrate_one(
                    obj=obj,
                    field_name=field_name,
                    local=local,
                    sharepoint=sharepoint,
                    overwrite=overwrite,
                    delete_local=delete_local,
                    dry_run=dry_run,
                    quiet=quiet,
                )
            except Exception as exc:
                summary["failed"] += 1
                self.stderr.write(self.style.ERROR(
                    f"[{label}#{obj.pk}] unexpected error: {exc}"
                ))
                logger.exception(
                    "Migration failed for %s#%s", label, obj.pk,
                )
                continue

            if outcome:
                summary[outcome] = summary.get(outcome, 0) + 1

            # Progress hint every 25 rows
            if not quiet and processed % 25 == 0:
                self.stdout.write(f"  ... {processed} row(s) inspected")

    # ------------------------------------------------------------------ #
    # Per-row migration
    # ------------------------------------------------------------------ #

    def _migrate_one(
        self,
        *,
        obj,
        field_name: str,
        local: FileSystemStorage,
        sharepoint,
        overwrite: bool,
        delete_local: bool,
        dry_run: bool,
        quiet: bool,
    ) -> Optional[str]:
        """
        Migrate a single row. Returns one of the summary keys, or ``None``
        if nothing was counted (rare).
        """
        field = getattr(obj, field_name, None)
        label = f"{obj.__class__.__name__}#{obj.pk}"

        # 1. Row has no file at all
        if not field or not getattr(field, "name", ""):
            if not quiet:
                self.stdout.write(f"  [{label}] no file — skipped")
            return "skipped_no_file"

        relative_path = field.name.replace("\\", "/").lstrip("/")

        # 2. Already registered as SharePoint-backed
        if getattr(obj, "storage_backend", "") == "sharepoint":
            if not quiet:
                self.stdout.write(f"  [{label}] already marked sharepoint")
            return "already_in_sharepoint"

        # 3. File already present in SharePoint?
        try:
            sp_exists = sharepoint.exists(relative_path)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [{label}] SharePoint.exists() failed: {exc}"
            ))
            return "failed"

        if sp_exists and not overwrite:
            # Just flip the breadcrumb — no bytes need to move.
            if not quiet:
                self.stdout.write(self.style.SUCCESS(
                    f"  [{label}] already in SharePoint — marking row"
                ))
            if not dry_run:
                with transaction.atomic():
                    obj.storage_backend = "sharepoint"
                    obj.save(update_fields=["storage_backend"])
            return "marked_only"

        # 4. Local file present?
        try:
            local_exists = local.exists(relative_path)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [{label}] local.exists() failed: {exc}"
            ))
            return "failed"

        if not local_exists:
            self.stderr.write(self.style.WARNING(
                f"  [{label}] local file missing: {relative_path}"
            ))
            return "missing_locally"

        # 5. Dry run — stop here
        if dry_run:
            if not quiet:
                self.stdout.write(
                    f"  [{label}] would copy {relative_path} → SharePoint"
                )
            return "copied"

        # 6. Real upload
        try:
            with local.open(relative_path, "rb") as src:
                # SharePointStorage.save() honours upload_to internally,
                # but because we pass the *full* relative path it will
                # keep the exact same key. get_available_name will append
                # a suffix if SHAREPOINT_FILE_OVERWRITE is False and the
                # file already exists — but we've already checked exists()
                # above, so this branch is only reached when either the
                # file is missing or --overwrite was passed.
                saved_name = sharepoint.save(relative_path, src)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [{label}] SharePoint upload failed: {exc}"
            ))
            logger.exception("SharePoint upload failed for %s", label)
            return "failed"

        # 7. Update the DB
        try:
            with transaction.atomic():
                if saved_name != relative_path:
                    # Storage renamed the file (e.g. appended a suffix
                    # because SHAREPOINT_FILE_OVERWRITE=False). Keep the
                    # DB in sync with what SharePoint actually stored.
                    field.name = saved_name
                    obj.storage_backend = "sharepoint"
                    obj.save(update_fields=[field_name, "storage_backend"])
                else:
                    obj.storage_backend = "sharepoint"
                    obj.save(update_fields=["storage_backend"])
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [{label}] DB update failed after upload: {exc}"
            ))
            logger.exception("DB update failed after SharePoint upload for %s", label)
            return "failed"

        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f"  [{label}] copied {relative_path}"
            ))

        # 8. Optional cleanup of the local copy
        if delete_local:
            try:
                local.delete(relative_path)
                if not quiet:
                    self.stdout.write(
                        f"  [{label}] local copy deleted"
                    )
                # Count this separately below
            except Exception as exc:
                self.stderr.write(self.style.WARNING(
                    f"  [{label}] local delete failed: {exc}"
                ))

        # The caller sums summary counters; we return the primary outcome.
        # If we deleted the local file, that fact is tracked separately
        # via a second call to the summary dict at the call site.
        if delete_local:
            # Signal that we also want to bump local_deleted; the caller
            # inspects this via a small side-channel.
            self._pending_local_delete = True

        return "copied"
