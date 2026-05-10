from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Extended User model matching WSDL fields"""
    
    # Personal Information
    ROLE_CHOICES = [
        ('citizen', 'Citizen'),
        ('staff', 'UFAA Staff'),
        ('admin', 'Administrator'),
        ('agent', 'Agent'),
    ]
    
    RESIDENCE_CHOICES = [
        ('', 'Blank'),
        ('Kenyan', 'Kenyan'),
        ('Non_Kenyan', 'Non Kenyan'),
    ]
    
    GENDER_CHOICES = [
        ('', 'Blank'),
        ('Male', 'Male'),
        ('Female', 'Female'),
    ]
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in format: '+25412345678'"
    )
    
    # Core fields from WSDL
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    residence = models.CharField(max_length=20, choices=RESIDENCE_CHOICES, blank=True, default='')
    id_number = models.CharField(
        max_length=9, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name=_('National ID Number'),
        help_text=_('Kenyan National ID Card Number (8 digits)')
    )
    name = models.CharField(max_length=200, blank=True)
    iprs_name = models.CharField(max_length=200, blank=True)
    claimant_birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    person_living_with_disability = models.BooleanField(default=False)
    passport_no = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name=_('Passport Number'),
        help_text=_('For non-Kenyan residents')
    )
    kra_pin = models.CharField(max_length=20, null=True, blank=True)
    business_registration_no = models.CharField(max_length=50, blank=True)
    
    # Contact Information
    address = models.TextField(blank=True)
    address_2 = models.TextField(blank=True)
    phone_no = models.CharField(validators=[phone_regex], max_length=17, unique=True)
    secondary_phone_no = models.CharField(max_length=17, blank=True)
    post_code = models.CharField(max_length=20, blank=True)
    county = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100, blank=True)
    home_county = models.CharField(max_length=50, blank=True)
    e_mail = models.EmailField(blank=True)
    
    # Location fields from WSDL
    county_code = models.CharField(max_length=20, blank=True)
    county_name = models.CharField(max_length=100, blank=True)
    gps_location = models.JSONField(null=True, blank=True)

    citizenship = models.CharField(max_length=50, blank=True)
    organization_name = models.CharField(max_length=200, blank=True)
    estate_name = models.CharField(max_length=200, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    person_living_with_disability = models.BooleanField(default=False)
    disability_category = models.CharField(max_length=100, blank=True, 
        choices=[
            ('physical', 'Physical Disability'),
            ('visual', 'Visual Impairment'),
            ('hearing', 'Hearing Impairment'),
            ('speech', 'Speech Impairment'),
            ('intellectual', 'Intellectual Disability'),
            ('mental', 'Mental Health Condition'),
            ('learning', 'Learning Disability'),
            ('multiple', 'Multiple Disabilities'),
            ('albinism', 'Albinism'),
            ('other', 'Other'),
        ]
    )  
    disability_certificate_no = models.CharField(max_length=50, blank=True) 
    
    # Profile
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Security
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['id_number']),
            models.Index(fields=['phone_no']),
            models.Index(fields=['passport_no']),
            models.Index(fields=['no']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.name or self.username} - {self.id_number or self.passport_no}"
    
    @property
    def is_staff_member(self):
        return self.role in ['staff', 'admin']


class StaffProfile(models.Model):
    """Staff profile matching WSDL Location_Source enum"""
    
    STAFF_DEPARTMENTS = [
        ('initiator', 'Initiator'),
        ('document_verification', 'Document Verification'),
        ('examiner', 'Examiner'),
        ('authorizer', 'Authorizer'),
        ('publisher', 'Publisher'),
        ('executive_officer', 'Executive Officer'),
        ('finance', 'Finance'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=50, choices=STAFF_DEPARTMENTS)
    position = models.CharField(max_length=100)
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    hire_date = models.DateField()
    profile_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'staff_profiles'
    
    def __str__(self):
        return f"{self.user.name or self.user.username} - {self.employee_id}"


class LoginAttempt(models.Model):
    """Track login attempts for security monitoring"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='login_attempts')
    identifier = models.CharField(max_length=100, db_index=True)
    ip_address = models.GenericIPAddressField(db_index=True)
    success = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user_agent = models.TextField(blank=True)
    device_fingerprint = models.CharField(max_length=255, blank=True)
    
    class Meta:
        db_table = 'login_attempts'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['identifier', '-timestamp']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.identifier} - {status} at {self.timestamp}"
    
    @classmethod
    def get_recent_failures(cls, identifier, minutes=15):
        """Get recent failed login attempts for an identifier"""
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        return cls.objects.filter(
            identifier=identifier,
            success=False,
            timestamp__gte=time_threshold
        ).count()
    
    @classmethod
    def is_locked_out(cls, identifier, max_attempts=5, lockout_minutes=15):
        """Check if an identifier is locked out due to too many failed attempts"""
        recent_failures = cls.get_recent_failures(identifier, lockout_minutes)
        return recent_failures >= max_attempts


class PasswordResetToken(models.Model):
    """Store password reset tokens"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.is_used and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"Reset token for {self.user.username} - Expires: {self.expires_at}"


class UserActivityLog(models.Model):
    """Track user activities for audit purposes"""
    
    ACTIVITY_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('claim_submit', 'Claim Submitted'),
        ('claim_view', 'Claim Viewed'),
        ('document_upload', 'Document Uploaded'),
        ('document_view', 'Document Viewed'),
        ('profile_update', 'Profile Updated'),
        ('password_change', 'Password Changed'),
        ('asset_search', 'Asset Searched'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_activity_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['activity_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.activity_type} at {self.created_at}"