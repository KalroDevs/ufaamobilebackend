from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, StaffProfile, LoginAttempt, PasswordResetToken, UserActivityLog


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'name', 'id_number', 'phone_no', 'role', 'is_verified', 'is_active')
    list_filter = ('role', 'is_verified', 'is_active', 'gender', 'person_living_with_disability')
    search_fields = ('username', 'email', 'name', 'id_number', 'phone_no', 'passport_no')
    readonly_fields = ('created_at', 'updated_at', 'last_login')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal Information'), {
            'fields': (
                'first_name', 'last_name', 'name', 'email', 'phone_no', 
                'secondary_phone_no', 'id_number', 'passport_no', 'kra_pin',
                'date_of_birth', 'gender', 'residence'
            )
        }),
        (_('Address Information'), {
            'fields': (
                'address', 'address_2', 'post_code', 'city', 'county', 
                'home_county', 'county_code', 'county_name'
            )
        }),
        (_('Disability Information'), {
            'fields': ('person_living_with_disability', 'disability_category')
        }),
        (_('Business Information'), {
            'fields': ('business_registration_no',)
        }),
        (_('Location & Profile'), {
            'fields': ('gps_location', 'profile_picture', 'iprs_name')
        }),
        (_('Security'), {
            'fields': (
                'role', 'is_verified', 'verification_token', 
                'last_login_ip', 'device_fingerprint', 'is_active', 
                'is_staff', 'is_superuser', 'groups', 'user_permissions'
            )
        }),
        (_('Important Dates'), {
            'fields': (
                'last_login', 'date_joined', 'created_at', 'updated_at',
                'claimant_birth_date'
            )
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'role'),
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'department', 'position', 'hire_date')
    list_filter = ('department', 'position', 'hire_date')
    search_fields = ('employee_id', 'user__name', 'user__email', 'user__phone_no')
    raw_id_fields = ('user', 'supervisor')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'employee_id', 'department', 'position')
        }),
        (_('Supervision'), {
            'fields': ('supervisor',)
        }),
        (_('Employment Details'), {
            'fields': ('hire_date', 'profile_id')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'ip_address', 'success', 'timestamp', 'user')
    list_filter = ('success', 'timestamp')
    search_fields = ('identifier', 'ip_address', 'user__name')
    readonly_fields = ('timestamp',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at', 'is_used')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'token')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'description_preview', 'ip_address', 'created_at')
    list_filter = ('activity_type', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Description'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False