# apps/live_operations/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import LiveOnlineClaim, LiveOnlineClaimLine


@admin.register(LiveOnlineClaim)
class LiveOnlineClaimAdmin(admin.ModelAdmin):
    """Admin configuration for LiveOnlineClaim model"""
    
    list_display = [
        'claim_no_display',
        'claimant_name_display',
        'id_number_display',
        'status_display',
        'amount_display',
        'created_at_display',
        'location_source_display'
    ]
    
    list_filter = [
        'status',
        'category',
        'claim_type',
        'location_source',
    ]
    
    search_fields = [
        'claim_no',
        'claimant_name',
        'id_number',
        'claimant_phone',
        'claimant_email',
    ]
    
    readonly_fields = [
        'claim_no',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('Claim Information', {
            'fields': (
                'claim_no',
                'status',
                'category',
                'sub_category',
                'claim_type',
                'location_source',
                'location',
            )
        }),
        ('Claimant Information', {
            'fields': (
                'claimant_name',
                'first_name',
                'middle_name',
                'last_name',
                'id_number',
                'passport_no',
                'claimant_phone',
                'claimant_email',
                'gender',
                'date_of_birth',
            )
        }),
        ('Financial Information', {
            'fields': (
                'amount',
                'payment_category',
                'bank_name',
                'bank_account_no',
                'mpesa_mobile_no',
            )
        }),
        ('Address Information', {
            'fields': (
                'residence',
                'address',
                'post_code',
                'county',
                'city',
                'estate_name',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def get_actions(self, request):
        """Remove delete action from the actions dropdown."""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    def has_delete_permission(self, request, obj=None):
        """Disable delete permission."""
        return False
    
    def claim_no_display(self, obj):
        return obj.claim_no or '-'
    claim_no_display.short_description = 'Claim No'
    claim_no_display.admin_order_field = 'claim_no'
    
    def claimant_name_display(self, obj):
        return obj.claimant_name or '-'
    claimant_name_display.short_description = 'Claimant Name'
    claimant_name_display.admin_order_field = 'claimant_name'
    
    def id_number_display(self, obj):
        return obj.id_number or '-'
    id_number_display.short_description = 'ID Number'
    id_number_display.admin_order_field = 'id_number'
    
    def amount_display(self, obj):
        if obj.amount:
            try:
                return f"KES {float(obj.amount):,.2f}"
            except (ValueError, TypeError):
                return str(obj.amount)
        return '0.00'
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def status_display(self, obj):
        status_colors = {
            'Draft': 'gray',
            'Pending': 'orange',
            'Under_Review': 'blue',
            'In_Progress': 'purple',
            'Processing': 'teal',
            'Approved': 'green',
            'Rejected': 'red',
            'Paid': 'gold',
            'Completed': 'darkgreen',
            'Archived': 'darkgray',
            'Cancelled': 'darkred',
        }
        color = status_colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status or 'Unknown'
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def created_at_display(self, obj):
        if obj.created_at:
            return obj.created_at.strftime('%Y-%m-%d %H:%M')
        return '-'
    created_at_display.short_description = 'Created At'
    created_at_display.admin_order_field = 'created_at'
    
    def location_source_display(self, obj):
        location_source_map = {
            '0': 'Unknown',
            '1': 'Online Portal',
            '2': 'Mobile App',
            '3': 'Reception',
            '4': 'Other',
        }
        value = obj.location_source or '0'
        label = location_source_map.get(str(value), f'Source {value}')
        color = 'green' if str(value) == '1' else 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            label
        )
    location_source_display.short_description = 'Location Source'
    location_source_display.admin_order_field = 'location_source'


@admin.register(LiveOnlineClaimLine)
class LiveOnlineClaimLineAdmin(admin.ModelAdmin):
    """Admin configuration for LiveOnlineClaimLine model"""
    
    list_display = [
        'id',
        'claim_link',
        'line_no',
        'asset_no',
        'asset_type',
        'asset_value_display',
        'holder_name'
    ]
    list_filter = ['asset_type']
    search_fields = [
        'claim__claim_no',
        'asset_no',
        'holder_name',
        'description'
    ]
    readonly_fields = ['id', 'claim', 'line_no']
    
    def get_actions(self, request):
        """Remove delete action from the actions dropdown."""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    def has_delete_permission(self, request, obj=None):
        """Disable delete permission."""
        return False
    
    def claim_link(self, obj):
        if obj.claim:
            url = reverse('admin:live_operations_liveonlineclaim_change', args=[obj.claim.pk])
            return format_html('<a href="{}">{}</a>', url, obj.claim.claim_no)
        return '-'
    claim_link.short_description = 'Claim No'
    
    def asset_value_display(self, obj):
        if obj.asset_value:
            return f"KES {float(obj.asset_value):,.2f}"
        return '0.00'
    asset_value_display.short_description = 'Asset Value'
