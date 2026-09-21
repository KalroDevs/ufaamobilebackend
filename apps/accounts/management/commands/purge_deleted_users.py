# apps/accounts/management/commands/purge_deleted_users.py
"""
Management command to permanently remove User rows that were soft-deleted
more than N days ago.

Soft delete (see DeleteAccountSerializer) anonymizes the user's PII and
keeps the row for referential integrity — claims, audit logs, login history,
etc. still point to a valid user_id.

This command completes the "right to be forgotten" by physically purging
those rows once the retention window has passed. Audit records in
AccountDeletionRequest survive because they don't use a ForeignKey.

Usage:
    # Dry run: show what would be deleted (safe, no writes)
    python manage.py purge_deleted_users --days=30 --dry-run

    # Real run: purge rows older than 30 days
    python manage.py purge_deleted_users --days=30

    # Aggressive: purge anything soft-deleted, regardless of age
    python manage.py purge_deleted_users --days=0

Recommended: schedule weekly via cron.
    0 3 * * 0 /var/www/ufaa_reunify_mobile_backend/ufaa_env/bin/python \\
      /var/www/ufaa_reunify_mobile_backend/ufaamobilebackend/manage.py \\
      purge_deleted_users --days=30 \\
      >> /var/log/ufaa/purge.log 2>&1
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, AccountDeletionRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Permanently delete User rows soft-deleted more than N days ago. "
        "Related rows cascade; AccountDeletionRequest audit rows survive."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help=(
                "Age in days after which soft-deleted users are purged. "
                "Use 0 to purge every soft-deleted user regardless of age. "
                "(default: 30)"
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Show what would be deleted without making any changes.",
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help="Number of users to purge per batch (default: 500).",
        )
        parser.add_argument(
            '--keep-audit',
            action='store_true',
            default=True,
            help=(
                "Keep AccountDeletionRequest rows (default: True). "
                "There is no supported way to disable this."
            ),
        )

    # ---------------------------------------------------------------- #
    # Main handler
    # ---------------------------------------------------------------- #
    def handle(self, *args, **options):
        days = options['days']
        dry = options['dry_run']
        batch_size = options['batch_size']

        if days < 0:
            raise CommandError("--days must be >= 0.")

        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1.")

        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.NOTICE(
                f"Purge window: users soft-deleted on or before "
                f"{cutoff.isoformat()} (i.e., {days} day(s) ago or earlier)."
            )
        )

        # Count how many are eligible
        total = User.all_objects.filter(
            is_deleted=True,
            deleted_at__lte=cutoff,
        ).count()

        self.stdout.write(
            f"Found {total} eligible soft-deleted user(s)."
        )

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to purge."))
            return

        # -------- Dry run --------
        if dry:
            self.stdout.write(
                self.style.WARNING("DRY RUN — no rows will be deleted.")
            )

            preview = (
                User.all_objects
                .filter(is_deleted=True, deleted_at__lte=cutoff)
                .order_by('deleted_at')
                .values_list('id', 'username', 'deleted_at', 'deletion_reason')[:20]
            )

            for uid, uname, deleted_at, reason in preview:
                self.stdout.write(
                    f"  [DRY] id={uid} username={uname} "
                    f"deleted_at={deleted_at} reason={reason or '-'}"
                )

            if total > 20:
                self.stdout.write(f"  ... and {total - 20} more.")

            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN complete. Would purge {total} row(s)."
                )
            )
            return

        # -------- Real run --------
        deleted_total = 0
        failed_batches = 0

        while True:
            batch_ids = list(
                User.all_objects
                .filter(is_deleted=True, deleted_at__lte=cutoff)
                .order_by('deleted_at')
                .values_list('id', flat=True)[:batch_size]
            )

            if not batch_ids:
                break

            try:
                with transaction.atomic():
                    # Delete via all_objects to bypass the default manager's
                    # soft-delete filter — we want to physically remove.
                    count, details = (
                        User.all_objects
                        .filter(id__in=batch_ids)
                        .delete()
                    )
                deleted_total += count

                logger.info(
                    "Purged batch: %d user(s) (deleted_total=%d)",
                    len(batch_ids), deleted_total,
                )
                self.stdout.write(
                    f"  purged {len(batch_ids)} user(s); "
                    f"rows affected = {count}; "
                    f"running total = {deleted_total}"
                )

            except Exception as e:
                failed_batches += 1
                logger.exception(
                    "Failed to purge batch of %d user(s): %s",
                    len(batch_ids), e,
                )
                self.stderr.write(
                    self.style.ERROR(
                        f"  ✗ batch failed ({len(batch_ids)} ids): {e}"
                    )
                )
                # Break to avoid an infinite loop on a persistent error
                break

        # -------- Post-purge report --------
        audit_count = AccountDeletionRequest.objects.count()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Permanently deleted {deleted_total} user row(s) and "
                f"cascaded related rows."
            )
        )
        self.stdout.write(
            f"Audit rows in AccountDeletionRequest: {audit_count} "
            f"(preserved, no ForeignKey to User)."
        )

        if failed_batches:
            self.stdout.write(
                self.style.WARNING(
                    f"{failed_batches} batch(es) failed — check logs."
                )
            )

        # Sanity check: are there still rows eligible?
        remaining = User.all_objects.filter(
            is_deleted=True, deleted_at__lte=cutoff,
        ).count()

        if remaining == 0:
            self.stdout.write(self.style.SUCCESS("All eligible rows purged."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"{remaining} row(s) still eligible — may be the "
                    f"result of the failed batch above."
                )
            )
