from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """Extended User model for UFAA Kenya"""
    
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
    
    # Identification - Primary identifiers
    id_number = models.CharField(
        max_length=9, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name=_('National ID Number'),
        help_text=_('Kenyan National ID Card Number (8 digits)')
    )
    passport_no = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name=_('Passport Number'),
        help_text=_('For non-Kenyan residents')
    )
    
    # Name Information
    name = models.CharField(max_length=200, blank=True, help_text="Full name")
    iprs_name = models.CharField(max_length=200, blank=True, help_text="Name from IPRS verification")
    
    # Demographic Information
    claimant_birth_date = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True, help_text="Alias for birth date")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    
    # Disability Information
    person_living_with_disability = models.BooleanField(default=False)
    disability_category = models.CharField(
        max_length=100, 
        blank=True, 
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
    
    # Tax and Business Information
    kra_pin = models.CharField(max_length=20, null=True, blank=True)
    business_registration_no = models.CharField(max_length=50, blank=True)
    
    # Contact Information
    address = models.TextField(blank=True)
    address_2 = models.TextField(blank=True)
    phone_no = models.CharField(validators=[phone_regex], max_length=17, unique=True)
    secondary_phone_no = models.CharField(max_length=17, blank=True)
    e_mail = models.EmailField(blank=True)
    
    # Postal Information
    post_code = models.CharField(max_length=20, blank=True)
    postal_address = models.CharField(max_length=200, blank=True, help_text="P.O. Box address")
    
    # Address Information
    county = models.CharField(max_length=50, blank=True, help_text="County of residence")
    city = models.CharField(max_length=100, blank=True, help_text="Town/City of residence")
    home_county = models.CharField(max_length=50, blank=True)
    estate_name = models.CharField(max_length=200, blank=True)
    
    # Location fields from WSDL
    county_code = models.CharField(max_length=20, blank=True)
    county_name = models.CharField(max_length=100, blank=True)
    gps_location = models.JSONField(null=True, blank=True)
    
    # Additional Information
    citizenship = models.CharField(max_length=50, blank=True, default='Kenyan')
    organization_name = models.CharField(max_length=200, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    
    # Profile
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    
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
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['id_number']),
            models.Index(fields=['phone_no']),
            models.Index(fields=['passport_no']),
            models.Index(fields=['no']),
            models.Index(fields=['role']),
            models.Index(fields=['email']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save to set name and sync date fields"""
        if not self.name and self.first_name and self.last_name:
            self.name = f"{self.first_name} {self.last_name}".strip()
        if self.claimant_birth_date and not self.date_of_birth:
            self.date_of_birth = self.claimant_birth_date
        super().save(*args, **kwargs)
    
    def __str__(self):
        identifier = self.id_number or self.passport_no or self.username
        return f"{self.name or self.username} - {identifier}"
    
    @property
    def is_staff_member(self):
        return self.role in ['staff', 'admin']
    
    @property
    def get_full_name_display(self):
        """Return full name or fallback to username"""
        return self.name or self.get_full_name() or self.username
    
    @property
    def get_primary_phone(self):
        """Return primary phone number"""
        return self.phone_no
    
    @property
    def get_secondary_phone(self):
        """Return secondary phone number"""
        return self.secondary_phone_no or None
    
    @property
    def get_disability_status(self):
        """Return disability status as readable text"""
        if not self.person_living_with_disability:
            return "No Disability"
        return f"Disabled - {self.get_disability_category_display() or 'Not Specified'}"
    
    @property
    def formatted_address(self):
        """Return formatted full address"""
        parts = []
        if self.address:
            parts.append(self.address)
        if self.city:
            parts.append(self.city)
        if self.county:
            parts.append(self.county)
        return ", ".join(parts) if parts else "No address provided"
    
    @classmethod
    def get_by_identifier(cls, identifier):
        """Find user by any identifier (ID, email, phone, passport)"""
        if not identifier:
            return None
            
        
        # Try email
        if '@' in identifier:
            return cls.objects.filter(email=identifier).first()
        
        # Try ID number (8 digits)
        if identifier.isdigit() and len(identifier) == 8:
            return cls.objects.filter(id_number=identifier).first()
        
        # Try phone number
        if identifier.startswith('0') or identifier.startswith('+'):
            clean_phone = identifier
            if clean_phone.startswith('+254'):
                clean_phone = '0' + clean_phone[4:]
            return cls.objects.filter(phone_no__icontains=clean_phone[-9:]).first()
        
        # Try passport number
        return cls.objects.filter(passport_no=identifier).first()



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
        ('legal', 'Legal'),
        ('it', 'IT'),
        ('customer_service', 'Customer Service'),
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
        ('register', 'Registration'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('password_change', 'Password Change'),
        ('profile_update', 'Profile Update'),
        ('claim_submit', 'Claim Submitted'),
        ('document_upload', 'Document Uploaded'),
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



class LoginHistory(models.Model):
    """Track user login history"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    device_info = models.JSONField(default=dict, blank=True)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    session_key = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'login_history'
        ordering = ['-login_time']
        indexes = [
            models.Index(fields=['user', '-login_time']),
            models.Index(fields=['login_time']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"


class UserDevice(models.Model):
    """Track user devices for fingerprinting"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    device_fingerprint = models.CharField(max_length=255)
    device_name = models.CharField(max_length=200, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_trusted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'user_devices'
        unique_together = ['user', 'device_fingerprint']
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name or self.device_fingerprint[:20]}"
