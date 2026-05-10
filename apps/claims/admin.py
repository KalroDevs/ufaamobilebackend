from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import (
    Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
)


class ClaimAssetInline(admin.TabularInline):
    """Inline for ClaimAsset model"""
    model = ClaimAsset
    extra = 0
    fields = ('asset', 'asset_no', 'holder_name', 'value', 'is_selected')
    readonly_fields = ('asset_no', 'holder_name', 'value')
    raw_id_fields = ('asset',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('asset')


class ClaimDocumentInline(admin.TabularInline):
    """Inline for ClaimDocument model"""
    model = ClaimDocument
    extra = 0
    fields = ('document_type', 'document_name', 'is_verified', 'uploaded_at')
    readonly_fields = ('uploaded_at',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by')


class ClaimNoteInline(admin.TabularInline):
    """Inline for ClaimNote model"""
    model = ClaimNote
    extra = 0
    fields = ('note_type', 'content', 'created_by', 'created_at', 'is_public')
    readonly_fields = ('created_at',)
    raw_id_fields = ('created_by',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


class ClaimStatusHistoryInline(admin.TabularInline):
    """Inline for ClaimStatusHistory model"""
    model = ClaimStatusHistory
    extra = 0
    fields = ('previous_status', 'new_status', 'changed_by', 'reason', 'changed_at')
    readonly_fields = ('changed_at',)
    raw_id_fields = ('changed_by',)
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('changed_by')


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    """Admin interface for Claim model"""
    
    list_display = (
        'no', 'name', 'id_number', 'category', 'status', 
        'amount', 'created_at', 'status_badge'
    )
    list_filter = (
        'status', 'category', 'claim_type', 'payment_category', 
        'created_at'
    )
    search_fields = (
        'no', 'name', 'id_number', 'phone_no', 'e_mail',
        'address', 'agent_name'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'submitted_at', 'approved_at', 'paid_at',
        'no'
    )
    raw_id_fields = ('claimant', 'assigned_to', 'approved_by')
    inlines = [
        ClaimAssetInline, 
        ClaimDocumentInline, 
        ClaimNoteInline, 
        ClaimStatusHistoryInline
    ]
    list_per_page = 25
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('no', 'status', 'category', 'sub_category', 'claim_type')
        }),
        (_('Claimant Information'), {
            'fields': (
                'name', 'id_number', 'passport_no', 'phone_no', 'secondary_phone_no',
                'e_mail', 'residence', 'gender', 'claimant_birth_date',
                'person_living_with_disability', 'kra_pin', 'business_registration_no'
            ),
            'classes': ('wide',)
        }),
        (_('Address Information'), {
            'fields': (
                'address', 'address_2', 'post_code', 'city', 'county',
                'home_county', 'county_code', 'county_name'
            ),
            'classes': ('wide',)
        }),
        (_('Asset Information'), {
            'fields': ('amount', 'amount_lcy', 'shares', 'safe_deposit', 'currency'),
            'classes': ('wide',)
        }),
        (_('Location Information'), {
            'fields': ('location', 'location_sent_to', 'location_sent_to_name', 'location_source'),
            'classes': ('wide',)
        }),
        (_('Payment Information'), {
            'fields': (
                'payment_category', 'bank_code', 'bank_name', 'branch_code',
                'branch_name', 'bank_account_no', 'bank_account_name',
                'account_currency', 'swift_code', 'international_payment',
                'international_bank_name', 'mpesa_mobile_no'
            ),
            'classes': ('wide',)
        }),
        (_('Comments & Remarks'), {
            'fields': (
                'portal_comments', 'internal_remarks', 'draft_remarks',
                'send_remarks_to_claimant', 'rejection_reason', 'approval_notes'
            ),
            'classes': ('wide',)
        }),
        (_('Staff Information'), {
            'fields': ('assigned_to', 'created_by', 'customer_care_id', 'profile_id'),
            'classes': ('wide',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at', 'submitted_at', 'approved_at', 'paid_at'),
            'classes': ('wide',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status as colored badge"""
        status_colors = {
            'Draft': 'gray',
            'Pending': 'orange',
            'Under_Review': 'blue',
            'Approved': 'green',
            'Rejected': 'red',
            'Paid': 'purple',
            'Completed': 'teal',
            'Archived': 'darkgray',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.status
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    actions = [
        'approve_claims', 'reject_claims', 'process_payments', 
        'complete_claims', 'mark_pending_review', 'mark_under_review'
    ]
    
    @admin.action(description='Approve selected claims')
    def approve_claims(self, request, queryset):
        updated = queryset.update(
            status='Approved', 
            approved_at=timezone.now(),
            approved_by=request.user
        )
        for claim in queryset:
            ClaimStatusHistory.objects.create(
                claim=claim,
                previous_status=claim.status,
                new_status='Approved',
                changed_by=request.user,
                reason='Approved via admin action'
            )
        self.message_user(request, f'{updated} claims approved.')
    
    @admin.action(description='Reject selected claims')
    def reject_claims(self, request, queryset):
        updated = queryset.update(status='Rejected', rejected=True)
        for claim in queryset:
            ClaimStatusHistory.objects.create(
                claim=claim,
                previous_status=claim.status,
                new_status='Rejected',
                changed_by=request.user,
                reason='Rejected via admin action'
            )
        self.message_user(request, f'{updated} claims rejected.')
    
    @admin.action(description='Process payment for selected claims')
    def process_payments(self, request, queryset):
        updated = queryset.update(status='Paid', paid_at=timezone.now())
        for claim in queryset:
            ClaimStatusHistory.objects.create(
                claim=claim,
                previous_status=claim.status,
                new_status='Paid',
                changed_by=request.user,
                reason='Payment processed via admin action'
            )
        self.message_user(request, f'{updated} claims payment processed.')
    
    @admin.action(description='Complete selected claims')
    def complete_claims(self, request, queryset):
        updated = queryset.update(status='Completed')
        for claim in queryset:
            ClaimStatusHistory.objects.create(
                claim=claim,
                previous_status=claim.status,
                new_status='Completed',
                changed_by=request.user,
                reason='Completed via admin action'
            )
        self.message_user(request, f'{updated} claims completed.')
    
    @admin.action(description='Mark as pending review')
    def mark_pending_review(self, request, queryset):
        updated = queryset.filter(status='Draft').update(status='Pending')
        for claim in queryset:
            if claim.status == 'Draft':
                ClaimStatusHistory.objects.create(
                    claim=claim,
                    previous_status='Draft',
                    new_status='Pending',
                    changed_by=request.user,
                    reason='Marked for review via admin action'
                )
        self.message_user(request, f'{updated} claims marked as pending review.')
    
    @admin.action(description='Mark as under review')
    def mark_under_review(self, request, queryset):
        updated = queryset.filter(status='Pending').update(status='Under_Review')
        for claim in queryset:
            if claim.status == 'Pending':
                ClaimStatusHistory.objects.create(
                    claim=claim,
                    previous_status='Pending',
                    new_status='Under_Review',
                    changed_by=request.user,
                    reason='Marked under review via admin action'
                )
        self.message_user(request, f'{updated} claims marked as under review.')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'claimant', 'assigned_to', 'approved_by'
        )
    
    def save_model(self, request, obj, form, change):
        """Override to ensure status history is tracked"""
        old_status = None
        if change and obj.pk:
            old_status = Claim.objects.get(pk=obj.pk).status
        super().save_model(request, obj, form, change)
        if change and old_status != obj.status:
            ClaimStatusHistory.objects.create(
                claim=obj,
                previous_status=old_status,
                new_status=obj.status,
                changed_by=request.user,
                reason='Status updated via admin'
            )


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    """Admin interface for ClaimDocument model"""
    
    list_display = (
        'claim', 'document_type', 'document_name', 'is_verified', 
        'is_rejected', 'uploaded_at', 'verification_status'
    )
    list_filter = ('document_type', 'is_verified', 'is_rejected', 'uploaded_at')
    search_fields = ('claim__no', 'document_name', 'verification_notes')
    readonly_fields = ('uploaded_at', 'file_size', 'file_extension')
    raw_id_fields = ('claim', 'uploaded_by', 'verified_by', 'rejected_by')
    list_select_related = ('claim', 'uploaded_by', 'verified_by')
    
    fieldsets = (
        (None, {
            'fields': ('claim', 'document_type', 'document_name')
        }),
        (_('File Information'), {
            'fields': ('file_path', 'file_size', 'file_extension', 'version', 'is_latest')
        }),
        (_('Verification'), {
            'fields': ('is_verified', 'verified_by', 'verified_at', 'verification_notes')
        }),
        (_('Rejection'), {
            'fields': ('is_rejected', 'rejected_by', 'rejected_at', 'rejection_reason')
        }),
        (_('Timestamps'), {
            'fields': ('uploaded_at',)
        }),
    )
    
    def verification_status(self, obj):
        """Display verification status as badge"""
        if obj.is_verified:
            return format_html('<span style="color: green;">✓ Verified</span>')
        elif obj.is_rejected:
            return format_html('<span style="color: red;">✗ Rejected</span>')
        return format_html('<span style="color: orange;">○ Pending</span>')
    verification_status.short_description = 'Status'
    
    actions = ['verify_documents', 'reject_documents', 'reset_verification']
    
    @admin.action(description='Verify selected documents')
    def verify_documents(self, request, queryset):
        updated = queryset.update(
            is_verified=True, 
            is_rejected=False,
            verified_by=request.user, 
            verified_at=timezone.now()
        )
        self.message_user(request, f'{updated} documents verified.')
    
    @admin.action(description='Reject selected documents')
    def reject_documents(self, request, queryset):
        updated = queryset.update(
            is_rejected=True, 
            is_verified=False,
            rejected_by=request.user, 
            rejected_at=timezone.now()
        )
        self.message_user(request, f'{updated} documents rejected.')
    
    @admin.action(description='Reset verification status')
    def reset_verification(self, request, queryset):
        updated = queryset.update(
            is_verified=False, 
            is_rejected=False,
            verified_by=None,
            verified_at=None,
            rejected_by=None,
            rejected_at=None
        )
        self.message_user(request, f'{updated} documents reset.')


@admin.register(ClaimNote)
class ClaimNoteAdmin(admin.ModelAdmin):
    """Admin interface for ClaimNote model"""
    
    list_display = (
        'claim', 'note_type', 'content_preview', 'created_by', 
        'created_at', 'is_public'
    )
    list_filter = ('note_type', 'is_public', 'created_at')
    search_fields = ('claim__no', 'content')
    readonly_fields = ('created_at',)
    raw_id_fields = ('claim', 'created_by')
    list_select_related = ('claim', 'created_by')
    
    fieldsets = (
        (None, {
            'fields': ('claim', 'note_type', 'content', 'is_public')
        }),
        (_('Author Information'), {
            'fields': ('created_by', 'created_at')
        }),
    )
    
    def content_preview(self, obj):
        """Preview of note content"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('claim', 'created_by')


@admin.register(ClaimStatusHistory)
class ClaimStatusHistoryAdmin(admin.ModelAdmin):
    """Admin interface for ClaimStatusHistory model"""
    
    list_display = (
        'claim', 'previous_status', 'new_status', 'changed_by', 
        'changed_at', 'status_change_indicator'
    )
    list_filter = ('new_status', 'changed_at')
    search_fields = ('claim__no', 'reason')
    readonly_fields = ('changed_at',)
    raw_id_fields = ('claim', 'changed_by')
    list_select_related = ('claim', 'changed_by')
    date_hierarchy = 'changed_at'
    
    fieldsets = (
        (None, {
            'fields': ('claim', 'previous_status', 'new_status', 'reason')
        }),
        (_('Change Information'), {
            'fields': ('changed_by', 'changed_at')
        }),
    )
    
    def status_change_indicator(self, obj):
        """Display status change indicator arrow"""
        return format_html('{} → {}', obj.previous_status or 'New', obj.new_status)
    status_change_indicator.short_description = 'Change'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False