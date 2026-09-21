# apps/claims/admin.py
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.db import connections
import os

from .models import (
    Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory,
    JointOwner, JointOwnerConsent, JointPaymentInstruction
)


# ============================================================
# FILTERS
# ============================================================

class LiveRejectedFilter(SimpleListFilter):
    """
    Filter claims by whether they are flagged as rejected
    ([Rejected] = 1) on the live Online Claim table.
    """

    title = 'Live rejection'
    parameter_name = 'live_rejected'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Rejected in live'),
            ('no', 'Not rejected'),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val not in ('yes', 'no'):
            return queryset

        from apps.live_operations.services import LiveDatabaseService

        claim_numbers = list(queryset.values_list('no', flat=True))
        if not claim_numbers:
            return queryset

        matching = []
        try:
            with connections["ereunify"].cursor() as cursor:
                CHUNK = 500
                for start in range(0, len(claim_numbers), CHUNK):
                    chunk = claim_numbers[start:start + CHUNK]
                    placeholders = ','.join(['%s'] * len(chunk))
                    cursor.execute(
                        f"""
                            SELECT [No_], [Rejected]
                            FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                            WHERE [No_] IN ({placeholders})
                        """,
                        chunk,
                    )
                    for claim_no, rejected in cursor.fetchall():
                        if val == 'yes' and bool(rejected):
                            matching.append(claim_no)
                        elif val == 'no' and not bool(rejected):
                            matching.append(claim_no)
        except Exception:
            return queryset.none()

        return queryset.filter(no__in=matching)


class StorageBackendFilter(SimpleListFilter):
    """
    Filter documents by which storage backend holds the bytes.

    Useful during the local → SharePoint migration to find rows that
    still resolve through the local filesystem.
    """

    title = 'Storage backend'
    parameter_name = 'storage_backend'

    def lookups(self, request, model_admin):
        return (
            ('sharepoint', 'SharePoint'),
            ('local', 'Local disk'),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'sharepoint':
            return queryset.filter(storage_backend='sharepoint')
        if val == 'local':
            return queryset.exclude(storage_backend='sharepoint')
        return queryset


# ============================================================
# INLINES
# ============================================================

class ClaimAssetInline(admin.TabularInline):
    model = ClaimAsset
    extra = 1
    fields = ['asset_no', 'holder_name', 'asset_type', 'value', 'source', 'name', 'id_number']
    readonly_fields = ['added_at']


class ClaimDocumentInline(admin.TabularInline):
    model = ClaimDocument
    extra = 1
    fields = [
        'document_links',
        'document_type',
        'document_name',
        'storage_backend',
        'is_verified',
        'is_rejected',
    ]
    readonly_fields = ['uploaded_at', 'uploaded_by', 'document_links', 'storage_backend']

    def document_links(self, obj):
        """
        Render View/Download links pointing at the API endpoints.

        The API endpoints redirect to SharePoint, so this never
        touches ``obj.file.path``.
        """
        if obj and obj.id and getattr(obj, 'file', None):
            try:
                view_url = f"/api/documents/{obj.id}/view/"
                download_url = f"/api/documents/{obj.id}/download/"
                return format_html(
                    '<div>'
                    '<a href="{}" target="_blank">View</a> | '
                    '<a href="{}">Download</a>'
                    '</div>',
                    view_url,
                    download_url,
                )
            except Exception:
                return "Error"
        return "No file"

    document_links.short_description = 'Document'

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


class ClaimNoteInline(admin.TabularInline):
    model = ClaimNote
    extra = 1
    fields = ['note_type', 'content', 'is_public']
    readonly_fields = ['created_at', 'created_by']


class ClaimStatusHistoryInline(admin.TabularInline):
    model = ClaimStatusHistory
    extra = 0
    fields = ['previous_status', 'new_status', 'reason']
    readonly_fields = ['changed_at', 'changed_by']


class JointOwnerInline(admin.TabularInline):
    model = JointOwner
    extra = 1
    fields = [
        'full_name', 'id_number', 'phone_number', 'email',
        'ownership_percentage', 'has_consented',
    ]


# ============================================================
# CLAIM ADMIN
# ============================================================

@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = [
        'no',
        'name',
        'id_number',
        'status',
        'claim_type',
        'amount',
        'document_count',
        'push_status_display',
        'live_status_display',
        'live_rejected_display',
        'created_at',
    ]
    list_filter = [
        'status', 'claim_type', 'category', 'payment_category', 'created_at',
        LiveRejectedFilter,
    ]
    search_fields = ['no', 'name', 'id_number', 'phone_no', 'e_mail', 'claimant__username']
    readonly_fields = [
        'no', 'created_at', 'updated_at', 'submitted_at',
        'approved_at', 'paid_at', 'completed_at',
    ]

    actions = [
        'push_to_live_action',
        'check_rejected_claims_action',
    ]

    fieldsets = (
        ('Claim Information', {
            'fields': (
                'no', 'status', 'claim_type', 'category',
                'sub_category', 'agent_name', 'claim_origin',
            )
        }),
        ('Claimant Information', {
            'fields': (
                'name', 'id_number', 'phone_no', 'e_mail',
                'address', 'city', 'county', 'gender',
                'passport_no', 'kra_pin', 'claimant_birth_date',
            )
        }),
        ('Asset Details', {
            'fields': ('asset_no', 'amount', 'currency', 'shares', 'safe_deposit')
        }),
        ('Payment Information', {
            'fields': (
                'payment_category', 'bank_name', 'bank_account_no',
                'mpesa_mobile_no', 'bank_code', 'branch_code',
                'swift_code', 'international_payment',
            )
        }),
        ('Status & Tracking', {
            'fields': (
                'submitted_at', 'approved_at', 'paid_at', 'completed_at',
                'rejection_reason', 'internal_remarks', 'portal_comments',
            )
        }),
        ('Staff Information', {
            'fields': (
                'claimant', 'assigned_to', 'approved_by',
                'created_by', 'customer_care_id',
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [
        ClaimAssetInline,
        ClaimDocumentInline,
        ClaimNoteInline,
        ClaimStatusHistoryInline,
        JointOwnerInline,
    ]

    # ---------------------------------------------------------------- #
    # Display columns
    # ---------------------------------------------------------------- #

    def document_count(self, obj):
        if obj:
            count = obj.documents.count()
            if count > 0:
                return format_html(
                    '<span style="color: green; font-weight: bold;">📄 {}</span>',
                    count,
                )
            return mark_safe('<span style="color: gray;">0</span>')
        return "0"

    document_count.short_description = 'Documents'

    def push_status_display(self, obj):
        if obj.status in ['Pending', 'Under_Review']:
            return mark_safe('<span style="color: orange;">⏳ Pushable</span>')
        elif obj.status in ['Approved', 'Paid', 'Completed']:
            return mark_safe('<span style="color: green;">✅ Completed</span>')
        elif obj.status in ['Rejected', 'Cancelled']:
            return mark_safe('<span style="color: red;">❌ Not Pushable</span>')
        return mark_safe('<span style="color: gray;">-</span>')

    push_status_display.short_description = 'Push Status'

    def live_status_display(self, obj):
        try:
            from apps.live_operations.services import LiveDatabaseService

            if obj.no:
                exists = LiveDatabaseService.claim_exists_in_live(obj.no)
                if exists:
                    return mark_safe(
                        '<span style="color: green; font-weight: bold;">'
                        '✅ In Live</span>'
                    )
                return mark_safe(
                    '<span style="color: gray;">⏳ Not Pushed</span>'
                )
            return mark_safe('<span style="color: gray;">-</span>')
        except Exception:
            return mark_safe('<span style="color: gray;">⚠️ Unknown</span>')

    live_status_display.short_description = 'Live Status'

    def live_rejected_display(self, obj):
        """Show whether the claim is rejected in the live Online Claim table."""
        if not obj or not obj.no:
            return mark_safe('<span style="color: gray;">-</span>')

        try:
            from apps.live_operations.services import LiveDatabaseService

            with connections["ereunify"].cursor() as cursor:
                cursor.execute(
                    f"""
                        SELECT TOP 1 [Rejected]
                        FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                        WHERE [No_] = %s
                    """,
                    [obj.no],
                )
                row = cursor.fetchone()

            if row is None:
                return mark_safe(
                    '<span style="color: gray;">Not in live</span>'
                )

            if bool(row[0]):
                return mark_safe(
                    '<span style="color: red; font-weight: bold;">'
                    '❌ Rejected in live</span>'
                )
            return mark_safe(
                '<span style="color: green;">✅ Not rejected</span>'
            )
        except Exception:
            return mark_safe('<span style="color: gray;">⚠️ Unknown</span>')

    live_rejected_display.short_description = 'Live Rejection'

    # ---------------------------------------------------------------- #
    # Save
    # ---------------------------------------------------------------- #

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.no:
                obj.no = obj.generate_fallback_claim_number()
        super().save_model(request, obj, form, change)

    # ---------------------------------------------------------------- #
    # Push-to-live action
    # ---------------------------------------------------------------- #

    def push_to_live_action(self, request, queryset):
        """Admin action to push selected claims to live."""
        if 'apply' in request.POST:
            selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
            if not selected:
                self.message_user(
                    request, 'No claims selected', level='ERROR'
                )
                return HttpResponseRedirect(request.get_full_path())

            pushed = 0
            failed = 0
            skipped = 0
            already_exists = 0
            errors = []

            for claim_id in selected:
                try:
                    claim = Claim.objects.get(id=claim_id)
                    if claim.status not in ['Pending', 'Under_Review']:
                        skipped += 1
                        errors.append(
                            f"{claim.no}: Not in pushable status "
                            f"(current: {claim.status})"
                        )
                        continue

                    from apps.live_operations.services import LiveDatabaseService

                    try:
                        exists = LiveDatabaseService.claim_exists_in_live(claim.no)
                        if exists:
                            already_exists += 1
                            errors.append(
                                f"{claim.no}: Already exists in live database"
                            )
                            continue
                    except Exception as e:
                        failed += 1
                        errors.append(
                            f"{claim.no}: Error checking existence - {str(e)}"
                        )
                        continue

                    result = LiveDatabaseService.push_claim_to_live(claim_id)

                    if result.get('success'):
                        pushed += 1
                        claim.status = 'Under_Review'
                        claim.save(update_fields=['status'])
                    else:
                        failed += 1
                        errors.append(
                            f"{claim.no}: "
                            f"{result.get('message', 'Unknown error')}"
                        )

                except Claim.DoesNotExist:
                    failed += 1
                    errors.append(f"Claim ID {claim_id} not found")
                except Exception as e:
                    failed += 1
                    errors.append(str(e))

            if pushed > 0:
                self.message_user(
                    request,
                    f'✅ Successfully pushed {pushed} claims to live. '
                    f'Failed: {failed}, Skipped: {skipped}, '
                    f'Already exists: {already_exists}',
                    level='SUCCESS',
                )
            else:
                self.message_user(
                    request,
                    f'❌ No claims were pushed. Failed: {failed}, '
                    f'Skipped: {skipped}, Already exists: {already_exists}',
                    level='WARNING',
                )

            if errors:
                error_list = '<br>'.join(errors[:10])
                if len(errors) > 10:
                    error_list += f'<br>... and {len(errors) - 10} more errors'
                self.message_user(
                    request,
                    mark_safe(f'<b>Details:</b><br>{error_list}'),
                    level='ERROR',
                )

            return HttpResponseRedirect(request.get_full_path())

        return self._show_push_confirmation(request, queryset)

    push_to_live_action.short_description = (
        "Push selected claims to live database"
    )

    # ---------------------------------------------------------------- #
    # Check rejected claims action
    # ---------------------------------------------------------------- #

    def check_rejected_claims_action(self, request, queryset):
        """
        Run the rejected-claims sync on the selected claims.

        For each claim, look up its row in the live Online Claim table.
        If [Rejected] = 1, move the local claim back to Draft, record
        the claimant-facing remark from [Send Remarks], and create a
        notification for the claimant.
        """
        from apps.accounts.models import Notification
        from apps.live_operations.services import LiveDatabaseService
        from django.db import transaction
        from django.utils import timezone

        processed = 0
        notified = 0
        skipped = 0
        not_in_live = 0
        errors = []

        for claim in queryset:
            try:
                if not claim.no:
                    skipped += 1
                    errors.append(f"{claim.id}: Claim has no number")
                    continue

                with connections["ereunify"].cursor() as cursor:
                    cursor.execute(
                        f"""
                            SELECT
                                [Rejected]                 AS rejected,
                                [Send Remarks]             AS reason,
                                [Claimant Action Required] AS action_required,
                                [$systemModifiedAt]        AS modified_at
                            FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                            WHERE [No_] = %s
                        """,
                        [claim.no],
                    )
                    row = cursor.fetchone()
                    columns = (
                        [c[0] for c in cursor.description] if row else []
                    )

                if not row:
                    not_in_live += 1
                    continue

                live = dict(zip(columns, row))

                if not bool(live.get('rejected')):
                    skipped += 1
                    continue

                modified_at_str = str(live.get('modified_at'))
                reason = (live.get('reason') or '').strip()
                action_required = bool(live.get('action_required'))

                existing = Notification.objects.filter(
                    user=claim.claimant,
                    category='claim_rejected',
                    related_model='Claim',
                    related_object_id=str(claim.id),
                ).first()

                if (
                    existing
                    and existing.metadata.get('modified_at') == modified_at_str
                ):
                    skipped += 1
                    continue

                with transaction.atomic():
                    previous_status = claim.status

                    claim.status = 'Draft'
                    claim.rejected = True
                    if reason:
                        claim.rejection_reason = reason
                    if action_required:
                        claim.claimant_action_required = True
                    claim.submitted_at = None

                    claim.save(update_fields=[
                        'status', 'rejected', 'rejection_reason',
                        'claimant_action_required', 'submitted_at',
                        'updated_at',
                    ])

                    ClaimStatusHistory.objects.create(
                        claim=claim,
                        previous_status=previous_status,
                        new_status='Draft',
                        changed_by=request.user,
                        reason=(
                            "Rejected in live database (manual check): "
                            f"{reason or 'no reason provided'}"
                        ),
                    )

                    if claim.claimant:
                        Notification.objects.update_or_create(
                            user=claim.claimant,
                            category='claim_rejected',
                            related_model='Claim',
                            related_object_id=str(claim.id),
                            defaults={
                                'title': (
                                    f"Claim {claim.no} needs your attention"
                                ),
                                'body': (
                                    reason
                                    or 'Please review your claim and resubmit.'
                                ),
                                'metadata': {
                                    'claim_no': claim.no,
                                    'status': 'Draft',
                                    'rejected': True,
                                    'action_required': action_required,
                                    'modified_at': modified_at_str,
                                    'source': 'admin_manual_check',
                                },
                            },
                        )
                        notified += 1

                    processed += 1

            except Exception as e:
                errors.append(f"{claim.no or claim.id}: {str(e)}")

        if processed > 0:
            self.message_user(
                request,
                (
                    f"✅ Rejected {processed} claim(s); "
                    f"{notified} claimant(s) notified. "
                    f"Skipped: {skipped}, Not in live: {not_in_live}"
                ),
                level='SUCCESS',
            )
        else:
            self.message_user(
                request,
                (
                    f"⚠️ No claims were updated. "
                    f"Skipped: {skipped}, Not in live: {not_in_live}"
                ),
                level='WARNING',
            )

        if errors:
            preview = '<br>'.join(errors[:10])
            if len(errors) > 10:
                preview += f'<br>... and {len(errors) - 10} more'
            self.message_user(
                request,
                mark_safe(f'<b>Errors:</b><br>{preview}'),
                level='ERROR',
            )

    check_rejected_claims_action.short_description = (
        "Check rejected claims in live database"
    )

    # ---------------------------------------------------------------- #
    # Actions / URLs / helpers
    # ---------------------------------------------------------------- #

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'push-to-live/<int:claim_id>/',
                self.admin_site.admin_view(self.push_to_live_single_view),
                name='push_to_live_single',
            ),
            path(
                'push-to-live-bulk/',
                self.admin_site.admin_view(self.push_to_live_bulk_view),
                name='push_to_live_bulk',
            ),
            path(
                'push-all-pending/',
                self.admin_site.admin_view(self.push_all_pending_view),
                name='push_all_pending',
            ),
            path(
                'push-live-status/',
                self.admin_site.admin_view(self.push_live_status_view),
                name='push_live_status',
            ),
        ]
        return custom_urls + urls

    def push_to_live_single_view(self, request, claim_id):
        try:
            claim = Claim.objects.get(id=claim_id)

            if claim.status not in ['Pending', 'Under_Review']:
                self.message_user(
                    request,
                    f'⚠️ Claim {claim.no} is not in pushable status '
                    f'(current: {claim.status})',
                    level='WARNING',
                )
                return HttpResponseRedirect(
                    reverse('admin:claims_claim_changelist')
                )

            from apps.live_operations.services import LiveDatabaseService

            try:
                exists = LiveDatabaseService.claim_exists_in_live(claim.no)
                if exists:
                    self.message_user(
                        request,
                        f'⚠️ Claim {claim.no} already exists in live database',
                        level='WARNING',
                    )
                    return HttpResponseRedirect(
                        reverse('admin:claims_claim_changelist')
                    )
            except Exception as e:
                self.message_user(
                    request,
                    f'❌ Error checking if claim exists: {str(e)}',
                    level='ERROR',
                )
                return HttpResponseRedirect(
                    reverse('admin:claims_claim_changelist')
                )

            result = LiveDatabaseService.push_claim_to_live(claim_id)

            if result.get('success'):
                claim.status = 'Under_Review'
                claim.save(update_fields=['status'])

                self.message_user(
                    request,
                    f'✅ Claim {claim.no} was successfully pushed to live '
                    f'with Location Source = 1',
                    level='SUCCESS',
                )
            else:
                self.message_user(
                    request,
                    f'❌ Failed to push claim {claim.no}: '
                    f'{result.get("message")}',
                    level='ERROR',
                )

        except Claim.DoesNotExist:
            self.message_user(
                request, f'Claim {claim_id} not found', level='ERROR'
            )
        except Exception as e:
            self.message_user(request, f'Error: {str(e)}', level='ERROR')

        return HttpResponseRedirect(
            reverse('admin:claims_claim_changelist')
        )

    def push_to_live_bulk_view(self, request):
        if request.method == 'POST':
            status_filter = request.POST.getlist('status')
            days_old = request.POST.get('days_old')

            filters = {}
            if status_filter:
                filters['status__in'] = status_filter
            else:
                filters['status__in'] = ['Pending', 'Under_Review']

            if days_old and days_old.isdigit():
                from django.utils import timezone
                from datetime import timedelta
                cutoff = timezone.now() - timedelta(days=int(days_old))
                filters['created_at__lte'] = cutoff

            claims = Claim.objects.filter(**filters)
            claim_ids = list(claims.values_list('id', flat=True))

            if not claim_ids:
                self.message_user(
                    request,
                    'No claims found matching the filters',
                    level='WARNING',
                )
                return HttpResponseRedirect(request.get_full_path())

            try:
                from apps.live_operations.tasks import push_claims_by_ids

                if (
                    hasattr(settings, 'CELERY_BROKER_URL')
                    and settings.CELERY_BROKER_URL
                ):
                    task = push_claims_by_ids.delay(claim_ids)
                    self.message_user(
                        request,
                        f'📤 Scheduled {len(claim_ids)} claims for pushing. '
                        f'Task ID: {task.id}',
                        level='SUCCESS',
                    )
                else:
                    result = push_claims_by_ids(claim_ids)
                    self.message_user(
                        request,
                        f'✅ Pushed {result.get("pushed", 0)} claims. '
                        f'Failed: {result.get("failed", 0)}, '
                        f'Already exists: {result.get("already_exists", 0)}',
                        level='SUCCESS',
                    )
            except (ImportError, ModuleNotFoundError):
                from apps.live_operations.services import LiveDatabaseService
                pushed = 0
                failed = 0
                already_exists = 0

                for claim_id in claim_ids:
                    try:
                        claim = Claim.objects.get(id=claim_id)
                        if LiveDatabaseService.claim_exists_in_live(claim.no):
                            already_exists += 1
                            continue
                        result = LiveDatabaseService.push_claim_to_live(
                            claim_id
                        )
                        if result.get('success'):
                            pushed += 1
                            claim.status = 'Under_Review'
                            claim.save(update_fields=['status'])
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

                self.message_user(
                    request,
                    f'✅ Pushed {pushed} claims. Failed: {failed}, '
                    f'Already exists: {already_exists}',
                    level='SUCCESS' if pushed > 0 else 'WARNING',
                )

            return HttpResponseRedirect(
                reverse('admin:claims_claim_changelist')
            )

        from django import forms

        class BulkPushForm(forms.Form):
            status = forms.MultipleChoiceField(
                choices=[
                    ('Pending', 'Pending'),
                    ('Under_Review', 'Under Review'),
                ],
                required=False,
                widget=forms.CheckboxSelectMultiple,
                label='Status Filter',
            )
            days_old = forms.IntegerField(
                required=False,
                min_value=1,
                label='Only push claims older than X days',
                help_text='Leave empty for all claims',
            )

        form = BulkPushForm()

        context = {
            'title': 'Push Claims to Live - Bulk',
            'form': form,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }

        return self.admin_site.admin_view(
            self._render_bulk_push_form
        )(request, context)

    def push_all_pending_view(self, request):
        try:
            from apps.live_operations.services import LiveDatabaseService

            claims = Claim.objects.filter(
                status__in=['Pending', 'Under_Review']
            )

            if not claims.exists():
                self.message_user(
                    request, 'No pending claims to push', level='WARNING'
                )
                return HttpResponseRedirect(
                    reverse('admin:claims_claim_changelist')
                )

            pushed = 0
            failed = 0
            already_exists = 0

            for claim in claims:
                try:
                    if LiveDatabaseService.claim_exists_in_live(claim.no):
                        already_exists += 1
                        continue

                    result = LiveDatabaseService.push_claim_to_live(claim.id)
                    if result.get('success'):
                        pushed += 1
                        claim.status = 'Under_Review'
                        claim.save(update_fields=['status'])
                    else:
                        failed += 1
                except Exception:
                    failed += 1

            self.message_user(
                request,
                f'✅ Pushed {pushed} claims. Failed: {failed}, '
                f'Already exists: {already_exists}',
                level='SUCCESS' if pushed > 0 else 'WARNING',
            )

        except Exception as e:
            self.message_user(
                request,
                f'❌ Error pushing pending claims: {str(e)}',
                level='ERROR',
            )

        return HttpResponseRedirect(
            reverse('admin:claims_claim_changelist')
        )

    def push_live_status_view(self, request):
        try:
            from apps.live_operations.models import LiveOnlineClaim

            total = LiveOnlineClaim.objects.count()
            recent = LiveOnlineClaim.objects.order_by('-created_at')[:10]
        except (ImportError, ModuleNotFoundError):
            total = 0
            recent = []

        context = {
            'title': 'Live Database Status',
            'total': total,
            'recent': recent,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }

        return self.admin_site.admin_view(
            self._render_status_page
        )(request, context)

    def _show_push_confirmation(self, request, queryset):
        context = {
            'title': 'Push to Live - Confirm',
            'queryset': queryset,
            'count': queryset.count(),
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'action_checkbox_name': ACTION_CHECKBOX_NAME,
            'media': self.media,
        }

        return self.admin_site.admin_view(
            self._render_confirmation
        )(request, context)

    def _render_confirmation(self, request, context):
        return self.admin_site.admin_view(
            lambda r: self._render_template(
                r,
                'admin/push_to_live_confirmation.html',
                context,
            )
        )(request)

    def _render_bulk_push_form(self, request, context):
        return self.admin_site.admin_view(
            lambda r: self._render_template(
                r,
                'admin/push_to_live_bulk_form.html',
                context,
            )
        )(request)

    def _render_status_page(self, request, context):
        return self.admin_site.admin_view(
            lambda r: self._render_template(
                r,
                'admin/push_to_live_status.html',
                context,
            )
        )(request)

    def _render_template(self, request, template, context):
        from django.template.response import TemplateResponse
        return TemplateResponse(request, template, context)

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if isinstance(list_display, tuple):
            list_display = list(list_display)
        if 'push_to_live_button' not in list_display:
            list_display.append('push_to_live_button')
        return list_display

    def push_to_live_button(self, obj):
        if obj.status in ['Pending', 'Under_Review']:
            try:
                from apps.live_operations.services import LiveDatabaseService
                exists = LiveDatabaseService.claim_exists_in_live(obj.no)
                if exists:
                    return mark_safe(
                        '<span style="color: green; font-weight: bold;">'
                        '✅ Already in Live</span>'
                    )
            except Exception:
                pass

            url = reverse('admin:push_to_live_single', args=[obj.id])
            return format_html(
                '<a class="button" href="{}" '
                'style="background-color: #28a745; color: white; '
                'padding: 4px 8px; border-radius: 3px; '
                'text-decoration: none; font-size: 12px;">'
                '🚀 Push to Live</a>',
                url,
            )
        elif obj.status in ['Approved', 'Paid', 'Completed']:
            return mark_safe(
                '<span style="color: green; font-weight: bold;">'
                '✅ Processed</span>'
            )
        else:
            return mark_safe(
                '<span style="color: gray; font-size: 12px;">'
                'Not pushable</span>'
            )

    push_to_live_button.short_description = 'Push to Live'
    push_to_live_button.allow_tags = True


# ============================================================
# CLAIM ASSET ADMIN
# ============================================================

@admin.register(ClaimAsset)
class ClaimAssetAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'claim_link',
        'asset_no',
        'holder_name',
        'asset_type',
        'value',
        'line_push_status_display',
        'push_line_button',
        'added_at',
    ]
    list_filter = ['asset_type', 'source']
    search_fields = [
        'asset_no', 'holder_name', 'name', 'id_number', 'claim__no',
    ]
    readonly_fields = ['added_at']
    fields = [
        'claim', 'asset_no', 'is_selected', 'value', 'holder_name',
        'asset_type', 'source', 'name', 'id_number', 'description',
        'cds_account_no', 'added_at',
    ]

    actions = ['push_selected_lines_to_live']

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def line_push_status_display(self, obj):
        if not obj or not obj.asset_no or not obj.claim or not obj.claim.no:
            return mark_safe('<span style="color: gray;">-</span>')

        try:
            from apps.live_operations.services import LiveDatabaseService

            batch_no = LiveDatabaseService.safe_string(obj.claim.no, 50)

            with connections["ereunify"].cursor() as cursor:
                cursor.execute(
                    f"""
                        SELECT COUNT(*)
                        FROM {LiveDatabaseService.ONLINE_CLAIM_LINE_TABLE}
                        WHERE [Batch No_] = %s
                          AND [Asset No_] = %s
                    """,
                    [
                        batch_no,
                        LiveDatabaseService.safe_string(obj.asset_no, 100),
                    ],
                )
                exists = cursor.fetchone()[0] > 0

            if exists:
                return mark_safe(
                    '<span style="color: green; font-weight: bold;">'
                    '✅ In Live</span>'
                )
            return mark_safe(
                '<span style="color: orange;">⏳ Not Pushed</span>'
            )
        except Exception:
            return mark_safe('<span style="color: gray;">⚠️ Unknown</span>')

    line_push_status_display.short_description = 'Line Status'

    def push_line_button(self, obj):
        if not obj or not obj.asset_no or not obj.claim or not obj.claim.no:
            return mark_safe(
                '<span style="color: gray; font-size: 12px;">-</span>'
            )

        try:
            from apps.live_operations.services import LiveDatabaseService
            header_exists = LiveDatabaseService.claim_exists_in_live(
                obj.claim.no
            )
        except Exception:
            header_exists = False

        if not header_exists:
            return mark_safe(
                '<span style="color: gray; font-size: 12px;">'
                'Header not in live</span>'
            )

        url = reverse('admin:claims_claimasset_push_line', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" '
            'style="background-color: #0d6efd; color: white; '
            'padding: 4px 8px; border-radius: 3px; '
            'text-decoration: none; font-size: 12px;">'
            '📋 Push Line</a>',
            url,
        )

    push_line_button.short_description = 'Push Line'
    push_line_button.allow_tags = True

    def push_selected_lines_to_live(self, request, queryset):
        from apps.live_operations.services import LiveDatabaseService

        pushed_total = 0
        failed_total = 0
        skipped_total = 0
        already_exists_total = 0
        errors = []

        claim_cache = {}

        for asset in queryset:
            try:
                if not asset.claim or not asset.claim.no:
                    skipped_total += 1
                    errors.append(
                        f"Asset {asset.id}: no parent claim or claim number"
                    )
                    continue

                claim_no = asset.claim.no
                if claim_no not in claim_cache:
                    claim_cache[claim_no] = (
                        LiveDatabaseService.claim_exists_in_live(claim_no)
                    )

                if not claim_cache[claim_no]:
                    skipped_total += 1
                    errors.append(
                        f"{claim_no}: Header not in live — push header first"
                    )
                    continue

                result = LiveDatabaseService.push_claim_lines_to_live(
                    asset.claim.id
                )

                pushed_total += result.get("pushed", 0)
                failed_total += result.get("failed", 0)
                skipped_total += result.get("skipped", 0)
                already_exists_total += result.get("already_exists", 0)

                if result.get("failed", 0) > 0:
                    errors.append(f"{claim_no}: {result.get('message')}")

            except Exception as e:
                failed_total += 1
                errors.append(f"Asset {asset.id}: {str(e)}")

        if pushed_total > 0:
            self.message_user(
                request,
                f"✅ Pushed {pushed_total} line(s). "
                f"Failed: {failed_total}, Skipped: {skipped_total}, "
                f"Already existed: {already_exists_total}",
                level="SUCCESS",
            )
        else:
            self.message_user(
                request,
                f"⚠️ No new lines pushed. "
                f"Failed: {failed_total}, Skipped: {skipped_total}, "
                f"Already existed: {already_exists_total}",
                level="WARNING",
            )

        if errors:
            preview = "<br>".join(errors[:10])
            if len(errors) > 10:
                preview += f"<br>... and {len(errors) - 10} more"
            self.message_user(
                request,
                mark_safe(f"<b>Details:</b><br>{preview}"),
                level="ERROR",
            )

    push_selected_lines_to_live.short_description = (
        "Push selected assets to live (Online Claim Lines)"
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:asset_id>/push-line/',
                self.admin_site.admin_view(self.push_line_single_view),
                name='claims_claimasset_push_line',
            ),
        ]
        return custom_urls + urls

    def push_line_single_view(self, request, asset_id):
        from apps.live_operations.services import LiveDatabaseService
        try:
            asset = ClaimAsset.objects.select_related('claim').get(id=asset_id)

            if not asset.claim or not asset.claim.no:
                self.message_user(
                    request,
                    "⚠️ Asset has no parent claim or claim number",
                    level="WARNING",
                )
                return HttpResponseRedirect(
                    reverse("admin:claims_claimasset_changelist")
                )

            if not LiveDatabaseService.claim_exists_in_live(asset.claim.no):
                self.message_user(
                    request,
                    f"⚠️ Claim header {asset.claim.no} is not in the live "
                    f"database. Push the header first.",
                    level="WARNING",
                )
                return HttpResponseRedirect(
                    reverse("admin:claims_claimasset_changelist")
                )

            result = LiveDatabaseService.push_claim_lines_to_live(
                asset.claim.id
            )

            if result.get("failed", 0) > 0:
                self.message_user(
                    request, f"⚠️ {result.get('message')}", level="WARNING"
                )
            else:
                self.message_user(
                    request, f"✅ {result.get('message')}", level="SUCCESS"
                )

        except ClaimAsset.DoesNotExist:
            self.message_user(
                request, f"Asset {asset_id} not found", level="ERROR"
            )
        except Exception as e:
            self.message_user(request, f"Error: {str(e)}", level="ERROR")

        return HttpResponseRedirect(
            reverse("admin:claims_claimasset_changelist")
        )


# ============================================================
# CLAIM DOCUMENT ADMIN
# ============================================================

@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'claim_link',
        'document_type',
        'document_name',
        'is_verified',
        'storage_badge',                 # 👈 NEW
        'live_document_status_display',
        'push_document_button',
        'uploaded_at',
    ]
    list_filter = [
        'document_type',
        'is_verified',
        'is_rejected',
        StorageBackendFilter,            # 👈 NEW
        'uploaded_at',
    ]
    search_fields = ['document_name', 'claim__no', 'uploaded_by__username']
    readonly_fields = [
        'uploaded_at',
        'uploaded_by',
        'document_links',
        'storage_backend',               # 👈 NEW
    ]
    fields = [
        'claim', 'document_type', 'document_name', 'document_links', 'file',
        'storage_backend',               # 👈 NEW
        'uploaded_by', 'uploaded_at',
        'is_verified', 'verified_by', 'verified_at',
        'verification_notes', 'is_rejected', 'rejection_reason',
        'version', 'is_latest',
    ]

    actions = ['push_documents_action']

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def document_links(self, obj):
        """
        Render the View / Download buttons.

        These point at the API endpoints, which redirect to SharePoint.
        They never touch ``obj.file.path``.
        """
        if obj and obj.id and getattr(obj, 'file', None):
            try:
                view_url = f"/api/documents/{obj.id}/view/"
                download_url = f"/api/documents/{obj.id}/download/"
                return format_html(
                    '<div>'
                    '<a href="{}" target="_blank" '
                    'style="background-color: #4CAF50; color: white; '
                    'padding: 5px 10px; text-decoration: none; '
                    'border-radius: 3px; margin-right: 5px;">'
                    '📄 View</a>'
                    '<a href="{}" '
                    'style="background-color: #008CBA; color: white; '
                    'padding: 5px 10px; text-decoration: none; '
                    'border-radius: 3px;">'
                    '⬇️ Download</a>'
                    '</div>',
                    view_url, download_url,
                )
            except Exception:
                return "Error loading document"
        return "No file uploaded"

    document_links.short_description = 'Document Actions'

    # ---------------------------------------------------------------- #
    # Storage badge
    # ---------------------------------------------------------------- #

    @admin.display(description='Storage')
    def storage_badge(self, obj):
        backend = (getattr(obj, 'storage_backend', '') or 'unknown').lower()
        if backend == 'sharepoint':
            return mark_safe(
                '<span style="color:#0d6efd; font-weight:600;">'
                '☁️ SharePoint</span>'
            )
        return mark_safe('<span style="color:#6c757d;">💾 Local</span>')

    # ---------------------------------------------------------------- #
    # Save / delete
    # ---------------------------------------------------------------- #

    def save_model(self, request, obj, form, change):
        if 'file' in form.changed_data and obj.file:
            # Mark the backend so the badge reflects reality.
            obj.storage_backend = 'sharepoint'
            try:
                obj.file_size = obj.file.size
                obj.file_extension = (
                    os.path.splitext(obj.file.name)[1].lower().lstrip('.')
                )
            except Exception:
                # Don't let a Graph hiccup block the DB write.
                pass
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.file:
            try:
                obj.file.delete(save=False)
            except Exception:
                pass
        super().delete_model(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def push_documents_action(self, request, queryset):
        from apps.live_operations.services import LiveDatabaseService

        pushed_total = 0
        failed_total = 0
        skipped_total = 0
        already_exists_total = 0
        errors = []

        claim_cache = {}

        for doc in queryset.select_related("claim"):
            try:
                if not doc.claim or not doc.claim.no:
                    skipped_total += 1
                    errors.append(
                        f"Doc {doc.id}: no parent claim or claim number"
                    )
                    continue

                claim_no = doc.claim.no
                if claim_no not in claim_cache:
                    claim_cache[claim_no] = (
                        LiveDatabaseService.claim_exists_in_live(claim_no)
                    )

                if not claim_cache[claim_no]:
                    skipped_total += 1
                    errors.append(
                        f"{claim_no}: Header not in live — push header first"
                    )
                    continue

                result = LiveDatabaseService.push_claim_documents_to_live(
                    doc.claim.id
                )

                pushed_total += result.get("pushed", 0)
                failed_total += result.get("failed", 0)
                skipped_total += result.get("skipped", 0)
                already_exists_total += result.get("already_exists", 0)

                if result.get("failed", 0) > 0:
                    errors.append(f"{claim_no}: {result.get('message')}")

            except Exception as e:
                failed_total += 1
                errors.append(f"Doc {doc.id}: {str(e)}")

        if pushed_total > 0:
            self.message_user(
                request,
                f"✅ Pushed {pushed_total} document(s). "
                f"Failed: {failed_total}, Skipped: {skipped_total}, "
                f"Already existed: {already_exists_total}",
                level="SUCCESS",
            )
        else:
            self.message_user(
                request,
                f"⚠️ No new documents pushed. "
                f"Failed: {failed_total}, Skipped: {skipped_total}, "
                f"Already existed: {already_exists_total}",
                level="WARNING",
            )

        if errors:
            preview = "<br>".join(errors[:10])
            if len(errors) > 10:
                preview += f"<br>... and {len(errors) - 10} more"
            self.message_user(
                request,
                mark_safe(f"<b>Details:</b><br>{preview}"),
                level="ERROR",
            )

    push_documents_action.short_description = (
        "Push selected documents to live (Attached Documents - Claims)"
    )

    def live_document_status_display(self, obj):
        if not obj or not obj.claim or not obj.claim.no:
            return mark_safe('<span style="color: gray;">-</span>')

        try:
            from apps.live_operations.services import LiveDatabaseService

            document_no = LiveDatabaseService.safe_string(obj.claim.no, 50)
            code = LiveDatabaseService.DOCUMENT_TYPE_CODE_MAPPING.get(
                obj.document_type, (obj.document_type or "").upper()
            )

            with connections["ereunify"].cursor() as cursor:
                cursor.execute(
                    f"""
                        SELECT COUNT(*)
                        FROM {LiveDatabaseService.ATTACHED_DOCUMENT_TABLE}
                        WHERE [Document No_] = %s
                          AND [Code] = %s
                    """,
                    [document_no, code],
                )
                exists = cursor.fetchone()[0] > 0

            if exists:
                return mark_safe(
                    '<span style="color: green; font-weight: bold;">'
                    '✅ In Live</span>'
                )
            return mark_safe(
                '<span style="color: orange;">⏳ Not Pushed</span>'
            )
        except Exception:
            return mark_safe('<span style="color: gray;">⚠️ Unknown</span>')

    live_document_status_display.short_description = "Live Status"

    def push_document_button(self, obj):
        if not obj or not obj.claim or not obj.claim.no:
            return mark_safe(
                '<span style="color: gray; font-size: 12px;">-</span>'
            )

        try:
            from apps.live_operations.services import LiveDatabaseService
            header_exists = LiveDatabaseService.claim_exists_in_live(
                obj.claim.no
            )
        except Exception:
            header_exists = False

        if not header_exists:
            return mark_safe(
                '<span style="color: gray; font-size: 12px;">'
                'Header not in live</span>'
            )

        url = reverse(
            "admin:claims_claimdocument_push_document", args=[obj.id]
        )
        return format_html(
            '<a class="button" href="{}" '
            'style="background-color: #6f42c1; color: white; '
            'padding: 4px 8px; border-radius: 3px; '
            'text-decoration: none; font-size: 12px;">'
            '📎 Push Document</a>',
            url,
        )

    push_document_button.short_description = "Push Document"
    push_document_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:doc_id>/push-document/",
                self.admin_site.admin_view(self.push_document_single_view),
                name="claims_claimdocument_push_document",
            ),
        ]
        return custom_urls + urls

    def push_document_single_view(self, request, doc_id):
        from apps.live_operations.services import LiveDatabaseService

        try:
            doc = ClaimDocument.objects.select_related("claim").get(id=doc_id)

            if not doc.claim or not doc.claim.no:
                self.message_user(
                    request,
                    "⚠️ Document has no parent claim or claim number",
                    level="WARNING",
                )
                return HttpResponseRedirect(
                    reverse("admin:claims_claimdocument_changelist")
                )

            if not LiveDatabaseService.claim_exists_in_live(doc.claim.no):
                self.message_user(
                    request,
                    f"⚠️ Claim header {doc.claim.no} is not in the live "
                    f"database. Push the header first.",
                    level="WARNING",
                )
                return HttpResponseRedirect(
                    reverse("admin:claims_claimdocument_changelist")
                )

            result = LiveDatabaseService.push_claim_documents_to_live(
                doc.claim.id
            )

            if result.get("failed", 0) > 0:
                self.message_user(
                    request, f"⚠️ {result.get('message')}", level="WARNING"
                )
            else:
                self.message_user(
                    request, f"✅ {result.get('message')}", level="SUCCESS"
                )

        except ClaimDocument.DoesNotExist:
            self.message_user(
                request, f"Document {doc_id} not found", level="ERROR"
            )
        except Exception as e:
            self.message_user(request, f"Error: {str(e)}", level="ERROR")

        return HttpResponseRedirect(
            reverse("admin:claims_claimdocument_changelist")
        )


# ============================================================
# OTHER ADMINS
# ============================================================

@admin.register(ClaimNote)
class ClaimNoteAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'claim_link', 'note_type', 'content_preview',
        'created_by', 'created_at',
    ]
    list_filter = ['note_type', 'is_public', 'created_at']
    search_fields = ['content', 'claim__no', 'created_by__username']
    readonly_fields = ['created_at', 'created_by']
    fields = [
        'claim', 'note_type', 'content', 'is_public',
        'created_by', 'created_at',
    ]

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def content_preview(self, obj):
        if obj and obj.content:
            return (
                obj.content[:50] + '...'
                if len(obj.content) > 50 else obj.content
            )
        return ""

    content_preview.short_description = 'Content'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(ClaimStatusHistory)
class ClaimStatusHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'claim_link', 'previous_status', 'new_status',
        'changed_by', 'changed_at',
    ]
    list_filter = ['previous_status', 'new_status', 'changed_at']
    search_fields = ['claim__no', 'reason', 'changed_by__username']
    readonly_fields = ['changed_at', 'changed_by']
    fields = [
        'claim', 'previous_status', 'new_status',
        'changed_by', 'reason', 'changed_at',
    ]

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(JointOwner)
class JointOwnerAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'claim_link', 'full_name', 'id_number',
        'phone_number', 'has_consented',
    ]
    list_filter = ['nationality', 'gender', 'has_disability', 'has_consented']
    search_fields = [
        'full_name', 'id_number', 'email', 'phone_number', 'claim__no',
    ]
    fields = [
        'claim', 'surname', 'given_name', 'full_name', 'id_number',
        'kra_pin', 'birth_date', 'phone_number', 'email', 'nationality',
        'gender', 'physical_address', 'postal_address', 'county',
        'has_disability', 'disability_category', 'ownership_percentage',
        'is_primary_claimant', 'has_consented', 'consent_date',
        'consent_form_uploaded',
    ]

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(JointOwnerConsent)
class JointOwnerConsentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'joint_owner_link', 'claim_link', 'status',
        'requested_at', 'responded_at',
    ]
    list_filter = ['status', 'notification_sent', 'reminder_sent']
    search_fields = [
        'joint_owner__full_name', 'claim__no', 'consent_token',
    ]
    readonly_fields = ['requested_at', 'consent_token']

    def joint_owner_link(self, obj):
        if obj and obj.joint_owner:
            url = reverse(
                'admin:claims_jointowner_change', args=[obj.joint_owner.id]
            )
            return format_html(
                '<a href="{}">{}</a>', url, obj.joint_owner.full_name
            )
        return "-"

    joint_owner_link.short_description = 'Joint Owner'

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(JointPaymentInstruction)
class JointPaymentInstructionAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'payment_method', 'created_at']
    list_filter = ['payment_method']
    search_fields = [
        'claim__no', 'joint_account_name', 'joint_account_number',
    ]
    fields = [
        'claim', 'payment_method', 'split_percentages',
        'joint_account_name', 'joint_account_number',
        'joint_bank_name', 'joint_branch_name', 'nominee_owner_id',
        'nominee_consent_received', 'no_objection_letter_path',
        'joint_consent_form_path', 'additional_notes',
    ]

    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"

    claim_link.short_description = 'Claim'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


admin.site.site_header = 'Claims Management System'
admin.site.site_title = 'Claims Admin'
admin.site.index_title = 'Welcome to Claims Management System'
