# apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    User,
    StaffProfile,
    LoginAttempt,
    PasswordResetToken,
    UserActivityLog,
    AccountDeletionRequest,          # 👈 NEW
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'username', 'email', 'name', 'id_number', 'phone_no', 'role',
        'is_verified', 'is_active',
        'is_deleted', 'deleted_at',                       # 👈 NEW
    )
    list_filter = (
        'role', 'is_verified', 'is_active',
        'is_deleted', 'deleted_at',                       # 👈 NEW
        'gender', 'person_living_with_disability',
    )
    search_fields = ('username', 'email', 'name', 'id_number', 'phone_no', 'passport_no')
    readonly_fields = (
        'created_at', 'updated_at', 'last_login',
        'is_deleted', 'deleted_at',                       # 👈 NEW
        'deletion_reason', 'deletion_reason_details',     # 👈 NEW
        'deletion_requested_ip',                          # 👈 NEW
    )
    actions = [                                            # 👈 NEW
        'restore_selected',
        'deactivate_selected',
        'purge_selected_soft_deleted',
    ]

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
        (_('Soft Delete'), {                               # 👈 NEW
            'fields': (                                    # 👈 NEW
                'is_deleted', 'deleted_at',                # 👈 NEW
                'deletion_reason',                         # 👈 NEW
                'deletion_reason_details',                 # 👈 NEW
                'deletion_requested_ip',                   # 👈 NEW
            ),                                             # 👈 NEW
            'classes': ('collapse',),                      # 👈 NEW
        }),                                                # 👈 NEW
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
        """
        Show ALL users, including soft-deleted ones, in the admin.
        Uses all_objects because the default manager hides deleted users.
        """
        qs = User.all_objects.all()                        # 👈 CHANGED
        return qs.select_related()

    # ---------------------------------------------------------------- #
    # Admin actions
    # ---------------------------------------------------------------- #
    @admin.action(description="Restore selected soft-deleted accounts")  # 👈 NEW
    def restore_selected(self, request, queryset):                       # 👈 NEW
        """                                                              # 👈 NEW
        Reactivate soft-deleted accounts.                                # 👈 NEW
                                                                         # 👈 NEW
        NOTE: PII was anonymized at deletion time, so the original       # 👈 NEW
        name, email, phone, ID, and passport cannot be recovered.        # 👈 NEW
        Only the account shell (username, is_active, is_deleted) is      # 👈 NEW
        restored. The audit trail in AccountDeletionRequest keeps the    # 👈 NEW
        original identifiers if you need to reconstruct manually.        # 👈 NEW
        """                                                              # 👈 NEW
        restored = 0                                                     # 👈 NEW
        for user in queryset.filter(is_deleted=True):                    # 👈 NEW
            user.is_deleted = False                                      # 👈 NEW
            user.deleted_at = None                                       # 👈 NEW
            user.deletion_reason = ''                                    # 👈 NEW
            user.deletion_reason_details = ''                            # 👈 NEW
            user.deletion_requested_ip = None                            # 👈 NEW
            user.is_active = True                                        # 👈 NEW
            user.save(update_fields=[                                    # 👈 NEW
                'is_deleted', 'deleted_at', 'deletion_reason',           # 👈 NEW
                'deletion_reason_details', 'deletion_requested_ip',      # 👈 NEW
                'is_active',                                             # 👈 NEW
            ])                                                           # 👈 NEW
            restored += 1                                                # 👈 NEW

        self.message_user(                                               # 👈 NEW
            request,                                                     # 👈 NEW
            (                                                            # 👈 NEW
                f"Restored {restored} account(s). Note: original PII was "  # 👈 NEW
                f"anonymized at deletion time and cannot be recovered."  # 👈 NEW
            ),                                                           # 👈 NEW
        )                                                                # 👈 NEW

    @admin.action(description="Deactivate selected users (keep data)")   # 👈 NEW
    def deactivate_selected(self, request, queryset):                    # 👈 NEW
        """                                                              # 👈 NEW
        Block logins without anonymizing data.                           # 👈 NEW
        Use when you want the account to remain identifiable.            # 👈 NEW
        """                                                              # 👈 NEW
        count = queryset.update(is_active=False)                         # 👈 NEW
        self.message_user(request, f"Deactivated {count} user(s).")      # 👈 NEW

    @admin.action(description="Permanently purge selected soft-deleted accounts")  # 👈 NEW
    def purge_selected_soft_deleted(self, request, queryset):                      # 👈 NEW
        """                                                              # 👈 NEW
        Hard-delete the selected soft-deleted User rows.                 # 👈 NEW
        Only rows with is_deleted=True are eligible. Cascades to         # 👈 NEW
        related models (StaffProfile, LoginAttempt, UserActivityLog,     # 👈 NEW
        LoginHistory, UserDevice, PasswordResetToken, etc.).             # 👈 NEW
                                                                         # 👈 NEW
        The AccountDeletionRequest audit rows are NOT deleted — they     # 👈 NEW
        have no ForeignKey and survive independently.                    # 👈 NEW
        """                                                              # 👈 NEW
        eligible = queryset.filter(is_deleted=True)                      # 👈 NEW
        count = eligible.count()                                         # 👈 NEW

        if count == 0:                                                   # 👈 NEW
            self.message_user(                                           # 👈 NEW
                request,                                                 # 👈 NEW
                "No soft-deleted users in the selection. Nothing purged.",  # 👈 NEW
                level='warning',                                         # 👈 NEW
            )                                                            # 👈 NEW
            return                                                       # 👈 NEW

        # Snapshot identifiers before deletion for the log message
        identifiers = list(                                              # 👈 NEW
            eligible.values_list('id', 'username')[:50]                  # 👈 NEW
        )                                                                # 👈 NEW

        eligible.delete()                                                # 👈 NEW

        self.message_user(                                               # 👈 NEW
            request,                                                     # 👈 NEW
            (                                                            # 👈 NEW
                f"Permanently purged {count} user(s) and related rows. "  # 👈 NEW
                f"Audit records in AccountDeletionRequest were preserved."  # 👈 NEW
            ),                                                           # 👈 NEW
        )                                                                # 👈 NEW


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
    list_display = (
        'user', 'activity_type', 'description_preview',
        'ip_address', 'created_at',
    )
    list_filter = ('activity_type', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)

    def description_preview(self, obj):
        return (
            obj.description[:50] + '...'
            if len(obj.description) > 50
            else obj.description
        )
    description_preview.short_description = 'Description'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ============================================================                # 👈 NEW
# ACCOUNT DELETION AUDIT ADMIN                                                # 👈 NEW
# ============================================================                # 👈 NEW
@admin.register(AccountDeletionRequest)                                       # 👈 NEW
class AccountDeletionRequestAdmin(admin.ModelAdmin):                          # 👈 NEW
    """                                                                       # 👈 NEW
    Immutable audit log for soft-deleted accounts.                            # 👈 NEW
                                                                              # 👈 NEW
    Rows are created only by the API (via DeleteAccountSerializer).           # 👈 NEW
    No add, change, or delete is allowed from the admin, so the audit         # 👈 NEW
    trail stays trustworthy.                                                  # 👈 NEW
    """                                                                       # 👈 NEW

    list_display = (                                                          # 👈 NEW
        'username', 'email', 'id_number', 'phone_no',                         # 👈 NEW
        'reason', 'requested_at',                                             # 👈 NEW
    )                                                                         # 👈 NEW
    list_filter = ('reason', 'requested_at')                                  # 👈 NEW
    search_fields = ('username', 'email', 'id_number', 'phone_no')            # 👈 NEW
    readonly_fields = (                                                       # 👈 NEW
        'user_id', 'username', 'email', 'id_number', 'phone_no',              # 👈 NEW
        'reason', 'reason_details',                                           # 👈 NEW
        'ip_address', 'user_agent', 'requested_at',                           # 👈 NEW
    )                                                                         # 👈 NEW
    date_hierarchy = 'requested_at'                                           # 👈 NEW
    ordering = ('-requested_at',)                                             # 👈 NEW

    fieldsets = (                                                             # 👈 NEW
        (_('Deleted User (snapshot)'), {                                      # 👈 NEW
            'fields': (                                                       # 👈 NEW
                'user_id', 'username', 'email', 'id_number', 'phone_no',      # 👈 NEW
            ),                                                                # 👈 NEW
        }),                                                                   # 👈 NEW
        (_('Deletion Details'), {                                             # 👈 NEW
            'fields': ('reason', 'reason_details', 'requested_at'),           # 👈 NEW
        }),                                                                   # 👈 NEW
        (_('Request Metadata'), {                                             # 👈 NEW
            'fields': ('ip_address', 'user_agent'),                           # 👈 NEW
        }),                                                                   # 👈 NEW
    )                                                                         # 👈 NEW

    def has_add_permission(self, request):                                    # 👈 NEW
        return False                                                          # 👈 NEW

    def has_change_permission(self, request, obj=None):                       # 👈 NEW
        return False                                                          # 👈 NEW

    def has_delete_permission(self, request, obj=None):                       # 👈 NEW
        return False                                                          # 👈 NEW
