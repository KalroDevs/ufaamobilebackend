# apps/claims/admin.py
from django.contrib import admin
from .models import (
    Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory,
    JointOwner, JointOwnerConsent, JointPaymentInstruction
)


class ClaimAssetInline(admin.TabularInline):
    model = ClaimAsset
    extra = 1
    fields = ['asset_no', 'holder_name', 'asset_type', 'value', 'source', 'name', 'id_number']
    readonly_fields = ['added_at']


class ClaimDocumentInline(admin.TabularInline):
    model = ClaimDocument
    extra = 1
    fields = ['document_type', 'document_name', 'file_path', 'is_verified', 'is_rejected']
    readonly_fields = ['uploaded_at', 'uploaded_by']


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
    fields = ['full_name', 'id_number', 'phone_number', 'email', 'ownership_percentage', 'has_consented']


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ['no', 'name', 'id_number', 'status', 'claim_type', 'amount', 'created_at']
    list_filter = ['status', 'claim_type', 'category', 'payment_category', 'created_at']
    search_fields = ['no', 'name', 'id_number', 'phone_no', 'e_mail', 'claimant__username']
    readonly_fields = ['no', 'created_at', 'updated_at', 'submitted_at', 'approved_at', 'paid_at', 'completed_at']
    fieldsets = (
        ('Claim Information', {
            'fields': ('no', 'status', 'claim_type', 'category', 'sub_category', 'agent_name', 'claim_origin')
        }),
        ('Claimant Information', {
            'fields': ('name', 'id_number', 'phone_no', 'e_mail', 'address', 'city', 'county', 
                      'gender', 'passport_no', 'kra_pin', 'claimant_birth_date')
        }),
        ('Asset Details', {
            'fields': ('asset_no', 'amount', 'currency', 'shares', 'safe_deposit')
        }),
        ('Payment Information', {
            'fields': ('payment_category', 'bank_name', 'bank_account_no', 'mpesa_mobile_no',
                      'bank_code', 'branch_code', 'swift_code', 'international_payment')
        }),
        ('Status & Tracking', {
            'fields': ('submitted_at', 'approved_at', 'paid_at', 'completed_at', 
                      'rejection_reason', 'internal_remarks', 'portal_comments')
        }),
        ('Staff Information', {
            'fields': ('claimant', 'assigned_to', 'approved_by', 'created_by', 'customer_care_id'),
            'classes': ('collapse',)
        }),
    )
    inlines = [ClaimAssetInline, ClaimDocumentInline, ClaimNoteInline, ClaimStatusHistoryInline, JointOwnerInline]
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object being created
            if not obj.no:
                obj.no = obj.generate_fallback_claim_number()
        super().save_model(request, obj, form, change)


@admin.register(ClaimAsset)
class ClaimAssetAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'asset_no', 'holder_name', 'asset_type', 'value', 'added_at']
    list_filter = ['asset_type', 'source']
    search_fields = ['asset_no', 'holder_name', 'name', 'id_number', 'claim__no']
    readonly_fields = ['added_at']
    fields = ['claim', 'asset_no', 'is_selected', 'value', 'holder_name', 'asset_type', 
              'source', 'name', 'id_number', 'description', 'cds_account_no', 'added_at']


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'document_type', 'document_name', 'is_verified', 'uploaded_at']
    list_filter = ['document_type', 'is_verified', 'is_rejected', 'uploaded_at']
    search_fields = ['document_name', 'claim__no', 'uploaded_by__username']
    readonly_fields = ['uploaded_at', 'uploaded_by']
    fields = ['claim', 'document_type', 'document_name', 'file_path', 'file_size', 
              'uploaded_by', 'is_verified', 'verified_by', 'verified_at', 'verification_notes',
              'is_rejected', 'rejection_reason', 'version', 'is_latest']


@admin.register(ClaimNote)
class ClaimNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'note_type', 'content_preview', 'created_by', 'created_at']
    list_filter = ['note_type', 'is_public', 'created_at']
    search_fields = ['content', 'claim__no', 'created_by__username']
    readonly_fields = ['created_at', 'created_by']
    fields = ['claim', 'note_type', 'content', 'is_public', 'created_by', 'created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(ClaimStatusHistory)
class ClaimStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'previous_status', 'new_status', 'changed_by', 'changed_at']
    list_filter = ['previous_status', 'new_status', 'changed_at']
    search_fields = ['claim__no', 'reason', 'changed_by__username']
    readonly_fields = ['changed_at', 'changed_by']
    fields = ['claim', 'previous_status', 'new_status', 'changed_by', 'reason', 'changed_at']


@admin.register(JointOwner)
class JointOwnerAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'full_name', 'id_number', 'phone_number', 'has_consented']
    list_filter = ['nationality', 'gender', 'has_disability', 'has_consented']
    search_fields = ['full_name', 'id_number', 'email', 'phone_number', 'claim__no']
    fields = ['claim', 'surname', 'given_name', 'full_name', 'id_number', 'kra_pin',
              'birth_date', 'phone_number', 'email', 'nationality', 'gender',
              'physical_address', 'postal_address', 'county', 'has_disability',
              'disability_category', 'ownership_percentage', 'is_primary_claimant',
              'has_consented', 'consent_date', 'consent_form_uploaded']


@admin.register(JointOwnerConsent)
class JointOwnerConsentAdmin(admin.ModelAdmin):
    list_display = ['id', 'joint_owner', 'claim', 'status', 'requested_at', 'responded_at']
    list_filter = ['status', 'notification_sent', 'reminder_sent']
    search_fields = ['joint_owner__full_name', 'claim__no', 'consent_token']
    readonly_fields = ['requested_at', 'consent_token']


@admin.register(JointPaymentInstruction)
class JointPaymentInstructionAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim', 'payment_method', 'created_at']
    list_filter = ['payment_method']
    search_fields = ['claim__no', 'joint_account_name', 'joint_account_number']
    fields = ['claim', 'payment_method', 'split_percentages', 'joint_account_name',
              'joint_account_number', 'joint_bank_name', 'joint_branch_name',
              'nominee_owner_id', 'nominee_consent_received', 'no_objection_letter_path',
              'joint_consent_form_path', 'additional_notes']
