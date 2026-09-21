# apps/asset_tracking/admin.py
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import AssetLocationLog, AssetTrackingDocument, TrackedAsset


class StorageBackendFilter(SimpleListFilter):
    """Filter documents by which storage backend holds the bytes."""

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


class AssetLocationLogInline(admin.TabularInline):
    """
    Read-only inline display for audit trail logs attached to a TrackedAsset.
    """
    model = AssetLocationLog
    extra = 0
    can_delete = False
    ordering = ('-created_at',)
    readonly_fields = (
        'status',
        'notes',
        'staff_email',
        'staff_name',
        'staff_latitude',
        'staff_longitude',
        'distance_km',
        'created_at',
    )

    def has_add_permission(self, request, obj=None):
        return False


class AssetTrackingDocumentInline(admin.TabularInline):
    """
    Inline for attached documents on the TrackedAsset admin detail view.
    """
    model = AssetTrackingDocument
    extra = 1
    raw_id_fields = ('uploaded_by',)
    fields = (
        'document_type',
        'document_name',
        'file',
        'storage_backend',
        'file_size',
        'file_extension',
        'uploaded_by',
        'uploaded_at',
    )
    readonly_fields = ('storage_backend', 'file_size', 'file_extension', 'uploaded_at')


@admin.register(TrackedAsset)
class TrackedAssetAdmin(admin.ModelAdmin):
    list_display = (
        'asset_no',
        'asset_name',
        'asset_owner',
        'status_badge',
        'staff_email',
        'county',
        'last_tracked_at',
        'created_at',
    )
    list_filter = (
        'status',
        'asset_type',
        'source',
        'county',
        'created_at',
        'last_tracked_at',
    )
    search_fields = (
        'asset_no',
        'asset_name',
        'asset_owner',
        'holder_name',
        'holder_no',
        'id_number',
        'passport_no',
        'cds_account_no',
        'staff_email',
        'staff_name',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'last_tracked_at',
        'last_tracked_by',
        'last_staff_latitude',
        'last_staff_longitude',
    )
    raw_id_fields = ('staff_user',)
    date_hierarchy = 'created_at'
    inlines = [AssetLocationLogInline, AssetTrackingDocumentInline]

    fieldsets = (
        (_('Asset Identity'), {
            'fields': (
                'asset_no',
                'asset_name',
                'asset_owner',
                'holder_name',
                'holder_no',
                'asset_type',
                'source',
            )
        }),
        (_('Owner Search Identifiers'), {
            'classes': ('collapse',),
            'fields': ('id_number', 'passport_no', 'cds_account_no'),
        }),
        (_('Address & Location'), {
            'fields': (
                'postal_address',
                'city_town',
                'county',
                'physical_address',
                ('latitude', 'longitude'),
            )
        }),
        (_('Tracking State'), {
            'fields': ('status', 'last_notes'),
        }),
        (_('Assigned Staff'), {
            'fields': ('staff_email', 'staff_name', 'staff_user'),
        }),
        (_('Latest Tracking Metadata'), {
            'classes': ('collapse',),
            'fields': (
                'last_tracked_at',
                'last_tracked_by',
                ('last_staff_latitude', 'last_staff_longitude'),
            )
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description=_('Status'), ordering='status')
    def status_badge(self, obj):
        colors = {
            'pending': '#e6a100',      # Amber
            'found': '#28a745',        # Green
            'not_found': '#dc3545',    # Red
            'moved': '#17a2b8',        # Cyan
            'transferred': '#6c757d',  # Gray
        }
        color = colors.get(obj.status, '#333333')
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display()
        )


@admin.register(AssetLocationLog)
class AssetLocationLogAdmin(admin.ModelAdmin):
    list_display = (
        'tracked_asset',
        'status',
        'staff_email',
        'distance_km',
        'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'tracked_asset__asset_no',
        'staff_email',
        'staff_name',
        'notes',
    )
    readonly_fields = (
        'tracked_asset',
        'status',
        'notes',
        'staff_email',
        'staff_name',
        'staff_latitude',
        'staff_longitude',
        'distance_km',
        'created_at',
    )
    raw_id_fields = ('tracked_asset',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        # Logs are immutable audit entries generated by tracking actions
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AssetTrackingDocument)
class AssetTrackingDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'tracked_asset',
        'document_type',
        'document_name',
        'file',
        'storage_badge',                     # 👈 NEW
        'file_size',
        'uploaded_by',
        'uploaded_at',
    )
    list_filter = (
        'document_type',
        'file_extension',
        StorageBackendFilter,                # 👈 NEW
        'uploaded_at',
    )
    search_fields = (
        'tracked_asset__asset_no',
        'document_name',
        'uploaded_by_email',
        'notes',
    )
    readonly_fields = (
        'uploaded_at',
        'file_size',
        'file_extension',
        'storage_backend',                   # 👈 NEW
    )
    raw_id_fields = ('tracked_asset', 'uploaded_by')
    date_hierarchy = 'uploaded_at'

    # ---------------------------------------------------------------- #
    # Storage badge
    # ---------------------------------------------------------------- #

    @admin.display(description='Storage')
    def storage_badge(self, obj):
        backend = (obj.storage_backend or 'unknown').lower()
        if backend == 'sharepoint':
            return format_html(
                '<span style="color:#0d6efd; font-weight:600;">☁️ SharePoint</span>'
            )
        return format_html('<span style="color:#6c757d;">💾 Local</span>')

    # ---------------------------------------------------------------- #
    # Save / delete
    # ---------------------------------------------------------------- #

    def save_model(self, request, obj, form, change):
        if 'file' in form.changed_data and obj.file:
            obj.storage_backend = 'sharepoint'
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.file:
            try:
                obj.file.delete(save=False)
            except Exception:
                pass
        super().delete_model(request, obj)
