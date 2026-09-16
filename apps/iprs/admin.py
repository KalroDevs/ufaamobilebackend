# apps/iprs/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import IprsSearchLog, IprsCache


@admin.register(IprsSearchLog)
class IprsSearchLogAdmin(admin.ModelAdmin):
    list_display = (
        'id_card', 'surname', 'other_names', 'status',
        'requested_from_ip', 'response_time_ms', 'created_at'
    )
    list_filter = ('status', 'gender', 'created_at')
    search_fields = ('id_card', 'surname', 'other_names', 'requested_from_ip')
    readonly_fields = (
        'id_card', 'requested_from_ip', 'user_agent', 'device_fingerprint',
        'status', 'response_data', 'error_message', 'surname', 'other_names',
        'gender', 'iprs_id', 'searched_at', 'response_time_ms', 'created_at'
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(IprsCache)
class IprsCacheAdmin(admin.ModelAdmin):
    list_display = (
        'id_card', 'surname', 'other_names', 'is_valid',
        'cached_at', 'expires_at', 'is_expired_display'
    )
    list_filter = ('is_valid', 'cached_at', 'expires_at')
    search_fields = ('id_card', 'surname', 'other_names')
    readonly_fields = ('cached_at', 'is_expired_display')
    date_hierarchy = 'cached_at'
    ordering = ('-cached_at',)
    
    def is_expired_display(self, obj):
        if not obj.expires_at:
           return format_html('<span style="color: gray;">—</span>')
        if obj.is_expired:
           return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Valid</span>')

    is_expired_display.short_description = 'Status'
    
    actions = ['cleanup_expired']
    
    @admin.action(description='Delete expired cache entries')
    def cleanup_expired(self, request, queryset):
        count = IprsCache.cleanup_expired()
        self.message_user(request, f'Cleaned up {count} expired cache entries.')
