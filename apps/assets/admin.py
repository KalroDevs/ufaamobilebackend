from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Asset, AssetLocation, AssetTrackingHistory


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_no', 'name', 'holder_name', 'asset_type', 'value', 'status', 'is_claimed')
    list_filter = ('asset_type', 'source', 'status', 'is_claimed', 'synchronized')
    search_fields = ('asset_no', 'name', 'holder_name', 'id_number', 'account_no')
    readonly_fields = ('last_updated',)
    
    fieldsets = (
        (None, {
            'fields': ('asset_no', 'asset_type', 'source', 'status', 'is_claimed')
        }),
        (_('Owner Information'), {
            'fields': (
                'name', 'first_name', 'middle_name', 'last_name', 
                'id_number', 'passport_no', 'date_of_birth'
            )
        }),
        (_('Holder Information'), {
            'fields': ('holder_no', 'holder_name')
        }),
        (_('Asset Details'), {
            'fields': (
                'value', 'currency', 'quantity', 'description', 
                'class_code', 'class_field', 'asset_code'
            )
        }),
        (_('Banking Information'), {
            'fields': (
                'account_no', 'cheque_no', 'cheque_date', 'drawee',
                'drawee_id_number', 'amount_due_to_owner', 'interest_bearing_account'
            )
        }),
        (_('Shares & Securities'), {
            'fields': (
                'cds_account_no', 'no_of_remitted_shares', 'safe_deposit_no',
                'description_of_the_content', 'value_of_the_content'
            )
        }),
        (_('Location Information'), {
            'fields': ('physical_address', 'latitude', 'longitude', 'location_source')
        }),
        (_('Address'), {
            'fields': ('owners_postal_address', 'owners_city_town', 'owners_telephone_no')
        }),
        (_('Tracking'), {
            'fields': ('reported_date', 'last_updated', 'created_by', 
                      'synchronized', 'batch_no', 'line_no')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')
    
    actions = ['mark_as_claimed', 'mark_as_pending']
    
    @admin.action(description='Mark selected assets as claimed')
    def mark_as_claimed(self, request, queryset):
        updated = queryset.update(is_claimed=True, status='claimed')
        self.message_user(request, f'{updated} assets marked as claimed.')
    
    @admin.action(description='Mark selected assets as pending')
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(is_claimed=False, status='pending')
        self.message_user(request, f'{updated} assets marked as pending.')


@admin.register(AssetLocation)
class AssetLocationAdmin(admin.ModelAdmin):
    list_display = ('asset', 'status', 'address_preview', 'latitude', 'longitude', 'last_verified')
    list_filter = ('status', 'location_source', 'verified_at')
    search_fields = ('asset__asset_no', 'asset__name', 'address', 'building_name')
    raw_id_fields = ('asset', 'verified_by')
    readonly_fields = ('created_at', 'updated_at')
    
    def address_preview(self, obj):
        return obj.address[:50] + '...' if len(obj.address) > 50 else obj.address
    address_preview.short_description = 'Address'
    
    def location_map(self, obj):
        if obj.latitude and obj.longitude:
            return format_html(
                '<a href="https://www.google.com/maps?q={},{}" target="_blank">View on Map</a>',
                obj.latitude, obj.longitude
            )
        return 'No coordinates'
    location_map.short_description = 'Map'


@admin.register(AssetTrackingHistory)
class AssetTrackingHistoryAdmin(admin.ModelAdmin):
    list_display = ('asset', 'previous_status', 'new_status', 'updated_by', 'created_at')
    list_filter = ('new_status', 'created_at')
    search_fields = ('asset__asset_no', 'notes')
    raw_id_fields = ('asset', 'updated_by')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False