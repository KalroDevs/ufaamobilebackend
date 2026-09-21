# apps/live_operations/tasks.py
import logging
from datetime import timedelta

from celery import shared_task
from django.db import connections, transaction
from django.utils import timezone

from apps.accounts.models import Notification
from apps.claims.models import Claim, ClaimStatusHistory
from .models import LiveSyncState
from .services import LiveDatabaseService

logger = logging.getLogger(__name__)


# ==================== PUSH TASKS ====================

@shared_task(
    bind=True,
    name="apps.live_operations.tasks.push_pending_claims_to_live",
)
def push_pending_claims_to_live(self):
    """
    Push all pending and under-review claims to the live Online Claim table.
    """
    logger.info(
        "Starting scheduled task: push_pending_claims_to_live (task_id=%s)",
        self.request.id,
    )

    try:
        result = LiveDatabaseService.push_pending_claims_to_live()

        if result.get("success"):
            logger.info(
                "Push task completed. Pushed=%s, Failed=%s, Skipped=%s",
                result.get("pushed", 0),
                result.get("failed", 0),
                result.get("skipped", 0),
            )
        else:
            logger.error(
                "Push task failed: %s",
                result.get("message", "Unknown error"),
            )

        return result

    except Exception as exc:
        logger.exception(
            "Unhandled error in push_pending_claims_to_live: %s", exc,
        )
        return {
            "success": False,
            "message": str(exc),
            "pushed": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }


@shared_task(
    bind=True,
    name="apps.live_operations.tasks.push_single_claim_to_live",
)
def push_single_claim_to_live(self, claim_id):
    """Push one claim header to the live Online Claim table."""
    logger.info(
        "Starting push_single_claim_to_live for claim ID %s (task_id=%s)",
        claim_id,
        self.request.id,
    )

    try:
        result = LiveDatabaseService.push_claim_to_live(claim_id)

        if result.get("success"):
            logger.info(
                "Claim ID %s pushed successfully as %s",
                claim_id,
                result.get("claim_no"),
            )
        else:
            logger.error(
                "Failed to push claim ID %s: %s",
                claim_id,
                result.get("message", "Unknown error"),
            )

        return result

    except Exception as exc:
        logger.exception(
            "Unhandled error pushing claim ID %s: %s", claim_id, exc,
        )
        return {
            "success": False,
            "claim_id": claim_id,
            "message": str(exc),
        }


@shared_task(
    bind=True,
    name="apps.live_operations.tasks.push_claims_by_ids",
)
def push_claims_by_ids(self, claim_ids):
    """
    Push selected claim headers to the live Online Claim table.

    Each claim is pushed independently so one failure does not stop the
    rest of the batch.
    """
    claim_ids = list(dict.fromkeys(claim_ids or []))

    logger.info(
        "Starting push_claims_by_ids for %s claim(s) (task_id=%s)",
        len(claim_ids),
        self.request.id,
    )

    if not claim_ids:
        return {
            "success": True,
            "message": "No claim IDs were provided",
            "pushed": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

    pushed = 0
    failed = 0
    skipped = 0
    details = []

    for claim_id in claim_ids:
        try:
            claim = Claim.objects.filter(id=claim_id).only(
                "id", "no", "status",
            ).first()

            if not claim:
                failed += 1
                details.append({
                    "claim_id": claim_id,
                    "status": "failed",
                    "message": "Claim not found",
                })
                continue

            if claim.status not in ["Pending", "Under_Review"]:
                skipped += 1
                details.append({
                    "claim_id": claim_id,
                    "claim_no": claim.no,
                    "status": "skipped",
                    "message": f"Claim status {claim.status} is not pushable",
                })
                continue

            if claim.no and LiveDatabaseService.claim_exists_in_live(claim.no):
                skipped += 1
                details.append({
                    "claim_id": claim_id,
                    "claim_no": claim.no,
                    "status": "skipped",
                    "message": "Already exists in live database",
                })
                continue

            result = LiveDatabaseService.push_claim_to_live(claim_id)

            if result.get("success"):
                pushed += 1
                status = "success"
            else:
                failed += 1
                status = "failed"

            detail = {
                "claim_id": claim_id,
                "claim_no": claim.no,
                "status": status,
                "message": result.get("message", ""),
            }
            if result.get("claim_no"):
                detail["live_claim_no"] = result["claim_no"]
            if result.get("stage"):
                detail["stage"] = result["stage"]
            details.append(detail)

        except Exception as exc:
            failed += 1
            logger.exception(
                "Error processing claim ID %s in batch: %s", claim_id, exc,
            )
            details.append({
                "claim_id": claim_id,
                "status": "failed",
                "message": str(exc),
            })

    return {
        "success": failed == 0,
        "message": (
            f"Push completed: {pushed} pushed, "
            f"{failed} failed, {skipped} skipped"
        ),
        "pushed": pushed,
        "failed": failed,
        "skipped": skipped,
        "details": details,
    }


@shared_task(
    bind=True,
    name="apps.live_operations.tasks.push_pending_claims_with_filter",
)
def push_pending_claims_with_filter(
    self,
    status_filter=None,
    days_old=None,
    limit=None,
):
    """Push claim headers matching optional status, age and limit filters."""
    logger.info(
        "Starting filtered push task. status_filter=%s, days_old=%s, "
        "limit=%s, task_id=%s",
        status_filter,
        days_old,
        limit,
        self.request.id,
    )

    try:
        allowed_statuses = ["Pending", "Under_Review"]

        if status_filter:
            requested_statuses = (
                [status_filter]
                if isinstance(status_filter, str)
                else list(status_filter)
            )
            selected_statuses = [
                s for s in requested_statuses if s in allowed_statuses
            ]
        else:
            selected_statuses = allowed_statuses

        if not selected_statuses:
            return {
                "success": True,
                "message": "No valid pushable statuses were supplied",
                "pushed": 0,
                "failed": 0,
                "skipped": 0,
                "details": [],
            }

        claims = Claim.objects.filter(
            status__in=selected_statuses
        ).order_by("id")

        if days_old is not None:
            days_old = int(days_old)
            if days_old < 0:
                raise ValueError("days_old cannot be negative")

            cutoff = timezone.now() - timedelta(days=days_old)
            field_names = {field.name for field in Claim._meta.get_fields()}
            date_field = next(
                (
                    f for f in (
                        "created_at",
                        "date_created",
                        "submitted_at",
                        "document_date",
                    )
                    if f in field_names
                ),
                None,
            )
            if date_field:
                claims = claims.filter(**{f"{date_field}__lte": cutoff})
            else:
                logger.warning(
                    "No supported date field exists on Claim; "
                    "days_old filter was ignored"
                )

        if limit is not None:
            limit = int(limit)
            if limit <= 0:
                return {
                    "success": True,
                    "message": "Limit must be greater than zero",
                    "pushed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "details": [],
                }
            claims = claims[:limit]

        claim_ids = list(claims.values_list("id", flat=True))

        if not claim_ids:
            return {
                "success": True,
                "message": "No claims matched the supplied filters",
                "pushed": 0,
                "failed": 0,
                "skipped": 0,
                "details": [],
            }

        result = push_claims_by_ids.run(claim_ids)

        logger.info(
            "Filtered push completed: %s", result.get("message"),
        )
        return result

    except Exception as exc:
        logger.exception(
            "Error in push_pending_claims_with_filter: %s", exc,
        )
        return {
            "success": False,
            "message": str(exc),
            "pushed": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }


# ==================== STATUS SYNC ====================

@shared_task(
    bind=True,
    name="apps.live_operations.tasks.sync_claim_statuses",
)
def sync_claim_statuses(self):
    """
    Synchronize statuses from the live Online Claim table to local claims.
    """
    logger.info(
        "Starting scheduled task: sync_claim_statuses (task_id=%s)",
        self.request.id,
    )

    try:
        from .models import LiveOnlineClaim

        status_mapping = {
            0: "Draft",
            1: "Pending",
            2: "Under_Review",
            3: "In_Progress",
            4: "Processing",
            5: "Approved",
            6: "Rejected",
            7: "Paid",
            8: "Completed",
            9: "Archived",
            10: "Cancelled",
        }

        synced = 0
        failed = 0
        skipped = 0
        details = []

        live_claims = LiveOnlineClaim.objects.all().iterator(chunk_size=500)

        for live_claim in live_claims:
            claim_no = getattr(live_claim, "claim_no", None)

            try:
                if not claim_no:
                    skipped += 1
                    continue

                claim = Claim.objects.filter(no=claim_no).first()
                if not claim:
                    skipped += 1
                    continue

                live_status = getattr(live_claim, "status", None)
                if isinstance(live_status, int):
                    live_status = status_mapping.get(live_status, "Pending")

                if not live_status or claim.status == live_status:
                    skipped += 1
                    continue

                claim.status = live_status
                claim.save(update_fields=["status"])
                synced += 1

                details.append({
                    "claim_no": claim_no,
                    "status": "synced",
                    "new_status": live_status,
                })

            except Exception as exc:
                failed += 1
                logger.exception(
                    "Error syncing claim %s: %s", claim_no, exc,
                )
                details.append({
                    "claim_no": claim_no,
                    "status": "failed",
                    "message": str(exc),
                })

        result = {
            "success": failed == 0,
            "synced": synced,
            "failed": failed,
            "skipped": skipped,
            "total": synced + failed + skipped,
            "message": (
                f"Synced {synced} claims, {failed} failed, {skipped} skipped"
            ),
            "details": details,
        }

        logger.info("Sync task completed: %s", result["message"])
        return result

    except Exception as exc:
        logger.exception(
            "Unhandled error in sync_claim_statuses: %s", exc,
        )
        return {
            "success": False,
            "message": str(exc),
            "synced": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "details": [],
        }


# ==================== REJECTED CLAIMS SYNC ====================

REJECTED_SYNC_NAME = "rejected_claims"


@shared_task(
    bind=True,
    name="apps.live_operations.tasks.sync_rejected_claims",
    max_retries=3,
    default_retry_delay=60,
)
def sync_rejected_claims(self):
    """
    Poll the live Online Claim table for newly rejected claims.

    For each match:
      - Move the local claim back to Draft so the claimant can edit
        and resubmit.
      - Flag the claim as rejected and record the reason.
      - Log a ClaimStatusHistory entry.
      - Create or refresh an in-app notification for the claimant.

    Idempotency:
        Each processed rejection is keyed on the live row's
        $systemModifiedAt. A subsequent run that sees the same
        modification time skips that row. A later re-rejection bumps
        the timestamp, so the sync catches it again.
    """
    state, _ = LiveSyncState.objects.get_or_create(name=REJECTED_SYNC_NAME)
    since = state.last_success_at

    logger.info(
        "sync_rejected_claims: starting (task_id=%s, since=%s)",
        self.request.id,
        since,
    )

    try:
        rows = LiveDatabaseService.fetch_rejected_claims(only_after=since)
    except Exception as exc:
        state.last_run_at = timezone.now()
        state.last_error = str(exc)
        state.save(update_fields=["last_run_at", "last_error"])
        logger.exception("sync_rejected_claims: fetch failed")
        raise self.retry(exc=exc)

    if not rows:
        state.last_run_at = timezone.now()
        state.last_success_at = timezone.now()
        state.last_error = ""
        state.save(update_fields=[
            "last_run_at", "last_success_at", "last_error",
        ])
        logger.info("sync_rejected_claims: no new rejected claims")
        return {"processed": 0, "notified": 0, "skipped": 0}

    processed = 0
    notified = 0
    skipped = 0
    details = []

    for row in rows:
        claim_no = (row.get("no") or "").strip()
        if not claim_no:
            skipped += 1
            continue

        claim = Claim.objects.filter(no=claim_no).first()
        if not claim:
            logger.debug(
                "sync_rejected_claims: no local Claim for live %s",
                claim_no,
            )
            skipped += 1
            details.append({
                "claim_no": claim_no,
                "status": "skipped",
                "message": "No local claim found",
            })
            continue

        modified_at_str = str(row.get("modified_at"))

        # Idempotency check on the previous notification's metadata.
        existing_notification = Notification.objects.filter(
            user=claim.claimant,
            category="claim_rejected",
            related_model="Claim",
            related_object_id=str(claim.id),
        ).first()

        if (
            existing_notification
            and existing_notification.metadata.get("modified_at") == modified_at_str
        ):
            skipped += 1
            continue

        rejection_reason = (row.get("rejection_reason") or "").strip()
        action_required = bool(row.get("action_required"))

        try:
            with transaction.atomic():
                previous_status = claim.status

                # ---- 1. Move the local claim back to Draft ----
                claim.status = "Draft"

                # ---- 2. Record the rejection on the claim itself ----
                claim.rejected = True
                if rejection_reason:
                    claim.rejection_reason = rejection_reason
                if action_required:
                    claim.claimant_action_required = True

                # Clear submitted_at so a resubmission gets a new one.
                claim.submitted_at = None

                claim.save(update_fields=[
                    "status",
                    "rejected",
                    "rejection_reason",
                    "claimant_action_required",
                    "submitted_at",
                    "updated_at",
                ])

                # ---- 3. Log the status transition ----
                ClaimStatusHistory.objects.create(
                    claim=claim,
                    previous_status=previous_status,
                    new_status="Draft",
                    changed_by=None,  # system-triggered
                    reason=(
                        "Rejected in live database: "
                        f"{rejection_reason or 'no reason provided'}"
                    ),
                )

                # ---- 4. Notify the claimant ----
                if claim.claimant:
                    Notification.objects.update_or_create(
                        user=claim.claimant,
                        category="claim_rejected",
                        related_model="Claim",
                        related_object_id=str(claim.id),
                        defaults={
                            "title": f"Claim {claim.no} needs your attention",
                            "body": (
                                rejection_reason
                                or "Please review your claim and resubmit."
                            ),
                            "metadata": {
                                "claim_no": claim.no,
                                "status": "Draft",
                                "rejected": True,
                                "action_required": action_required,
                                "modified_at": modified_at_str,
                            },
                        },
                    )
                    notified += 1

                processed += 1
                details.append({
                    "claim_no": claim.no,
                    "status": "processed",
                    "rejection_reason": rejection_reason,
                    "notified": bool(claim.claimant),
                })

        except Exception as exc:
            skipped += 1
            logger.exception(
                "sync_rejected_claims: failed to process %s", claim_no,
            )
            details.append({
                "claim_no": claim_no,
                "status": "failed",
                "message": str(exc),
            })

    state.last_run_at = timezone.now()
    state.last_success_at = timezone.now()
    state.last_error = ""
    state.save(update_fields=[
        "last_run_at", "last_success_at", "last_error",
    ])

    logger.info(
        "sync_rejected_claims: processed=%s notified=%s skipped=%s",
        processed, notified, skipped,
    )

    return {
        "success": True,
        "processed": processed,
        "notified": notified,
        "skipped": skipped,
        "message": (
            f"Processed {processed} rejected claim(s), "
            f"notified {notified}, skipped {skipped}"
        ),
        "details": details,
    }


# ==================== MAINTENANCE ====================

@shared_task(
    bind=True,
    name="apps.live_operations.tasks.cleanup_duplicate_claims",
)
def cleanup_duplicate_claims(self):
    """
    Remove older duplicate records from the live Online Claim header table.
    """
    logger.info(
        "Starting cleanup_duplicate_claims task (task_id=%s)",
        self.request.id,
    )

    table = LiveDatabaseService.ONLINE_CLAIM_TABLE

    try:
        with connections["ereunify"].cursor() as cursor:
            cursor.execute(
                f"""
                    SELECT [No_], COUNT(*) AS duplicate_count
                    FROM {table}
                    GROUP BY [No_]
                    HAVING COUNT(*) > 1
                """
            )
            duplicates = cursor.fetchall()

            if not duplicates:
                return {
                    "success": True,
                    "message": "No duplicate claims found",
                    "duplicates_found": 0,
                    "cleaned": 0,
                    "details": [],
                }

            cleaned = 0
            details = []

            for claim_no, duplicate_count in duplicates:
                cursor.execute(
                    f"""
                        DELETE FROM {table}
                        WHERE [No_] = %s
                          AND [$systemCreatedAt] < (
                              SELECT MAX([$systemCreatedAt])
                              FROM {table}
                              WHERE [No_] = %s
                          )
                    """,
                    [claim_no, claim_no],
                )

                removed = cursor.rowcount
                cleaned += removed

                details.append({
                    "claim_no": claim_no,
                    "duplicates": duplicate_count,
                    "removed": removed,
                })

                logger.info(
                    "Removed %s duplicate record(s) for claim %s",
                    removed,
                    claim_no,
                )

            return {
                "success": True,
                "message": f"Cleaned {cleaned} duplicate claim record(s)",
                "duplicates_found": len(duplicates),
                "cleaned": cleaned,
                "details": details,
            }

    except Exception as exc:
        logger.exception(
            "Error in cleanup_duplicate_claims: %s", exc,
        )
        return {
            "success": False,
            "message": str(exc),
            "duplicates_found": 0,
            "cleaned": 0,
            "details": [],
        }
