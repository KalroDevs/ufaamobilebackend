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
    fields = ['document_link', 'document_type', 'document_name', 'is_verified', 'is_rejected']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'document_link']
    
    def document_link(self, obj):
        """Create a clickable link to view/download the document"""
        if obj and obj.id:
            # Use the standalone document endpoints (not under claims/)
            view_url = f"/api/documents/{obj.id}/view/"
            download_url = f"/api/documents/{obj.id}/download/"
            
            # Get file extension for icon
            ext = os.path.splitext(obj.file_path)[1].lower() if obj.file_path else ''
            icon = '📄'
            if ext == '.pdf':
                icon = '📑'
            elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
                icon = '🖼️'
            elif ext in ['.doc', '.docx']:
                icon = '📝'
            elif ext in ['.xls', '.xlsx']:
                icon = '📊'
            
            return format_html(
                '<a href="{}" target="_blank" style="font-weight: bold; margin-right: 10px;">{} View</a>'
                '<a href="{}" style="font-weight: bold;">⬇️ Download</a>',
                view_url, icon, download_url
            )
        return "No file"
    document_link.short_description = 'Document'
    
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
                return format_html('<span style="color: green; font-weight: bold;">📄 {}</span>', str(count))
            return format_html('<span style="color: gray;">0</span>')
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
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"
    claim_link.short_description = 'Claim'


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'claim_link', 'document_type', 'document_name', 'document_preview', 'is_verified', 'uploaded_at']
    list_filter = ['document_type', 'is_verified', 'is_rejected', 'uploaded_at']
    search_fields = ['document_name', 'claim__no', 'uploaded_by__username']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'file_size_display']
    fields = ['claim', 'document_type', 'document_name', 'document_view', 'file_path', 'file_size_display',
              'uploaded_by', 'is_verified', 'verified_by', 'verified_at', 'verification_notes',
              'is_rejected', 'rejection_reason', 'version', 'is_latest']
    
    def claim_link(self, obj):
        """Link to the claim admin page"""
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"
    claim_link.short_description = 'Claim'
    
    def document_view(self, obj):
        """Create a viewable/downloadable link for the document"""
        if obj and obj.id:
            # Use the standalone document endpoints (not under claims/)
            full_view_url = f"/api/documents/{obj.id}/view/"
            full_download_url = f"/api/documents/{obj.id}/download/"
            
            # Get file extension for appropriate icon and viewer
            ext = os.path.splitext(obj.file_path)[1].lower() if obj.file_path else ''
            
            # Choose icon based on file type
            icon = '📄'
            if ext == '.pdf':
                icon = '📑'
                button_text = 'Open PDF'
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                icon = '🖼️'
                button_text = 'View Image'
            elif ext in ['.doc', '.docx']:
                icon = '📝'
                button_text = 'Open Document'
            elif ext in ['.xls', '.xlsx']:
                icon = '📊'
                button_text = 'Open Spreadsheet'
            elif ext == '.txt':
                icon = '📃'
                button_text = 'View Text'
            else:
                button_text = 'Download File'
            
            # Create buttons for view and download
            view_button = mark_safe(
                f'<a href="{full_view_url}" target="_blank" style="background-color: #4CAF50; color: white; '
                f'padding: 6px 12px; text-decoration: none; border-radius: 4px; margin-right: 8px;">'
                f'{icon} {button_text}</a>'
            )
            
            download_button = mark_safe(
                f'<a href="{full_download_url}" style="background-color: #008CBA; color: white; '
                f'padding: 6px 12px; text-decoration: none; border-radius: 4px;">'
                f'⬇️ Download</a>'
            )
            
            # If it's an image, show a thumbnail preview
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                preview = mark_safe(
                    f'<div style="margin-top: 10px;">'
                    f'<a href="{full_view_url}" target="_blank">'
                    f'<img src="{full_view_url}" style="max-width: 200px; max-height: 150px; border: 1px solid #ddd; '
                    f'border-radius: 4px; padding: 5px;" />'
                    f'</a></div>'
                )
                return mark_safe(f'<div>{view_button}{download_button}</div>{preview}')
            
            return mark_safe(f'<div>{view_button}{download_button}</div>')
        return "No file uploaded"
    document_view.short_description = 'Document'
    
    def document_preview(self, obj):
        """Quick preview in list view"""
        if obj and obj.id:
            # Use the standalone document view endpoint
            full_view_url = f"/api/documents/{obj.id}/view/"
            
            ext = os.path.splitext(obj.file_path)[1].lower() if obj.file_path else ''
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                return mark_safe(
                    f'<a href="{full_view_url}" target="_blank">'
                    f'<img src="{full_view_url}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;" />'
                    f'</a>'
                )
            elif ext == '.pdf':
                return mark_safe(f'<a href="{full_view_url}" target="_blank"><span style="font-size: 20px;">📑</span></a>')
            else:
                return mark_safe(f'<a href="{full_view_url}" target="_blank"><span style="font-size: 20px;">📄</span></a>')
        return "-"
    document_preview.short_description = 'Preview'
    
    def file_size_display(self, obj):
        """Display file size in human readable format"""
        if obj and obj.file_size:
            size = obj.file_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        return "-"
    file_size_display.short_description = 'File Size'


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
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
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
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
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
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
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
            return format_html('<a href="{}">{}</a>', url, obj.joint_owner.full_name)
        return "-"
    joint_owner_link.short_description = 'Joint Owner'
    
    def claim_link(self, obj):
        if obj and obj.claim:
            url = reverse('admin:claims_claim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
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
            return format_html('<a href="{}">{}</a>', url, obj.claim.no)
        return "-"
    claim_link.short_description = 'Claim'
