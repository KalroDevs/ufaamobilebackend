# apps/claims/admin.py

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.conf import settings
import os
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
    fields = ['document_links', 'document_type', 'document_name', 'is_verified', 'is_rejected']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'document_links']
    
    def document_links(self, obj):
        """Create a clickable link to view/download the document"""
        if obj and obj.id:
            if hasattr(obj, 'file') and obj.file:
                try:
                    view_url = f"/api/documents/{obj.id}/view/"
                    download_url = f"/api/documents/{obj.id}/download/"
                    
                    html = f'<div><a href="{view_url}" target="_blank">View</a> | <a href="{download_url}">Download</a></div>'
                    return mark_safe(html)
                except:
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
    fields = ['full_name', 'id_number', 'phone_number', 'email', 'ownership_percentage', 'has_consented']


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ['no', 'name', 'id_number', 'status', 'claim_type', 'amount', 'document_count', 'created_at']
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
    
    def document_count(self, obj):
        """Display the number of documents for the claim"""
        if obj:
            count = obj.documents.count()
            if count > 0:
                return mark_safe(f'<span style="color: green; font-weight: bold;">📄 {count}</span>')
            return mark_safe('<span style="color: gray;">0</span>')
        return "0"
    document_count.short_description = 'Documents'
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object being created
            if not obj.no:
                obj.no = obj.generate_fallback_claim_number()
        super().save_model(request, obj, form, change)


@admin.register(ClaimAsset)
class ClaimAssetAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'asset_no', 'holder_name', 'asset_type', 'value', 'added_at']
    list_filter = ['asset_type', 'source']
    search_fields = ['asset_no', 'holder_name', 'name', 'id_number', 'claim__no']
    readonly_fields = ['added_at']
    fields = ['claim', 'asset_no', 'is_selected', 'value', 'holder_name', 'asset_type', 
              'source', 'name', 'id_number', 'description', 'cds_account_no', 'added_at']
    
    def claim_link(self, obj):
        """Link to the claim admin page"""
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'document_type', 'document_name', 'is_verified', 'uploaded_at']
    list_filter = ['document_type', 'is_verified', 'is_rejected', 'uploaded_at']
    search_fields = ['document_name', 'claim__no', 'uploaded_by__username']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'document_links']  # document_links here
    fields = ['claim', 'document_type', 'document_name', 'document_links', 'file',
              'uploaded_by', 'uploaded_at', 'is_verified', 'verified_by', 'verified_at', 
              'verification_notes', 'is_rejected', 'rejection_reason', 'version', 'is_latest']
    
    def claim_link(self, obj):
        """Link to the claim admin page"""
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'
    
    def document_links(self, obj):
        """Create view and download links for the document"""
        if obj and obj.id:
            if hasattr(obj, 'file') and obj.file:
                try:
                    view_url = f"/api/documents/{obj.id}/view/"
                    download_url = f"/api/documents/{obj.id}/download/"
                    
                    html = f'''
                    <div>
                        <a href="{view_url}" target="_blank" style="background-color: #4CAF50; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; margin-right: 5px;">📄 View</a>
                        <a href="{download_url}" style="background-color: #008CBA; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">⬇️ Download</a>
                    </div>
                    '''
                    return mark_safe(html)
                except:
                    return "Error loading document"
        return "No file uploaded"
    document_links.short_description = 'Document Actions'
    
    def save_model(self, request, obj, form, change):
        if 'file' in form.changed_data and obj.file:
            obj.file_size = obj.file.size
            obj.file_extension = os.path.splitext(obj.file.name)[1].lower().lstrip('.')
        super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        if obj.file:
            try:
                obj.file.delete(save=False)
            except:
                pass
        super().delete_model(request, obj)


@admin.register(ClaimNote)
class ClaimNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'note_type', 'content_preview', 'created_by', 'created_at']
    list_filter = ['note_type', 'is_public', 'created_at']
    search_fields = ['content', 'claim__no', 'created_by__username']
    readonly_fields = ['created_at', 'created_by']
    fields = ['claim', 'note_type', 'content', 'is_public', 'created_by', 'created_at']
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'
    
    def content_preview(self, obj):
        if obj and obj.content:
            return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return ""
    content_preview.short_description = 'Content'


@admin.register(ClaimStatusHistory)
class ClaimStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'previous_status', 'new_status', 'changed_by', 'changed_at']
    list_filter = ['previous_status', 'new_status', 'changed_at']
    search_fields = ['claim__no', 'reason', 'changed_by__username']
    readonly_fields = ['changed_at', 'changed_by']
    fields = ['claim', 'previous_status', 'new_status', 'changed_by', 'reason', 'changed_at']
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'


@admin.register(JointOwner)
class JointOwnerAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'full_name', 'id_number', 'phone_number', 'has_consented']
    list_filter = ['nationality', 'gender', 'has_disability', 'has_consented']
    search_fields = ['full_name', 'id_number', 'email', 'phone_number', 'claim__no']
    fields = ['claim', 'surname', 'given_name', 'full_name', 'id_number', 'kra_pin',
              'birth_date', 'phone_number', 'email', 'nationality', 'gender',
              'physical_address', 'postal_address', 'county', 'has_disability',
              'disability_category', 'ownership_percentage', 'is_primary_claimant',
              'has_consented', 'consent_date', 'consent_form_uploaded']
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'


@admin.register(JointOwnerConsent)
class JointOwnerConsentAdmin(admin.ModelAdmin):
    list_display = ['id', 'joint_owner_link', 'claim_link', 'status', 'requested_at', 'responded_at']
    list_filter = ['status', 'notification_sent', 'reminder_sent']
    search_fields = ['joint_owner__full_name', 'claim__no', 'consent_token']
    readonly_fields = ['requested_at', 'consent_token']
    
    def joint_owner_link(self, obj):
        if obj and obj.joint_owner:
            url = reverse('admin:claims_jointowner_change', args=[obj.joint_owner.id])
            return mark_safe(f'<a href="{url}">{obj.joint_owner.full_name}</a>')
        return "-"
    joint_owner_link.short_description = 'Joint Owner'
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'


@admin.register(JointPaymentInstruction)
class JointPaymentInstructionAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'payment_method', 'created_at']
    list_filter = ['payment_method']
    search_fields = ['claim__no', 'joint_account_name', 'joint_account_number']
    fields = ['claim', 'payment_method', 'split_percentages', 'joint_account_name',
              'joint_account_number', 'joint_bank_name', 'joint_branch_name',
              'nominee_owner_id', 'nominee_consent_received', 'no_objection_letter_path',
              'joint_consent_form_path', 'additional_notes']
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return mark_safe(f'<a href="{url}">{obj.claim.no}</a>')
        return "-"
    claim_link.short_description = 'Claim'


# Custom admin site configuration
admin.site.site_header = 'Claims Management System'
admin.site.site_title = 'Claims Admin'
admin.site.index_title = 'Welcome to Claims Management System'
