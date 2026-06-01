# apps/accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.db import models
from .models import User, StaffProfile
import random
from datetime import timedelta


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'residence', 'id_number', 'name', 'iprs_name',
            'claimant_birth_date', 'gender', 'person_living_with_disability',
            'passport_no', 'kra_pin', 'business_registration_no',
            'address', 'address_2', 'phone_no', 'secondary_phone_no',
            'post_code', 'county', 'city', 'home_county', 'e_mail',
            'county_code', 'county_name', 'citizenship', 'organization_name',
            'estate_name', 'institution', 'disability_category',
            'disability_certificate_no', 'gps_location', 'profile_picture', 
            'date_of_birth', 'is_verified', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.name or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)
    
    # Additional registration fields
    surname = serializers.CharField(write_only=True, required=False, allow_blank=True)
    other_names = serializers.CharField(write_only=True, required=False, allow_blank=True)
    nationality = serializers.CharField(write_only=True, required=False, default='Kenyan')
    
    # Address fields
    town = serializers.CharField(write_only=True, required=False, allow_blank=True)
    estate_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    physical_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    postal_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    county_of_residence = serializers.CharField(write_only=True, required=False, allow_blank=True)
    alternative_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    # New fields
    kra_pin = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    passport_no = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    has_disability = serializers.BooleanField(write_only=True, required=False, default=False)
    disability_category = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'confirm_password',
            'first_name', 'last_name', 'surname', 'other_names',
            'id_number', 'phone_no', 'alternative_phone',
            'date_of_birth', 'gender', 'nationality',
            'town', 'estate_name', 'physical_address', 'postal_address',
            'county_of_residence', 'citizenship',
            'kra_pin', 'passport_no', 'has_disability', 'disability_category'
        ]
    
    def validate(self, attrs):
        # Check passwords match
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        # Handle name fields
        surname = attrs.pop('surname', '')
        other_names = attrs.pop('other_names', '')
        if surname:
            attrs['first_name'] = surname
        if other_names:
            attrs['last_name'] = other_names
            attrs['name'] = f"{surname} {other_names}".strip()
        
        # Handle nationality and citizenship
        nationality = attrs.pop('nationality', 'Kenyan')
        attrs['citizenship'] = nationality
        if nationality == 'Kenyan':
            attrs['residence'] = 'Kenyan'
        
        # Handle address fields
        town = attrs.pop('town', '')
        estate_name = attrs.pop('estate_name', '')
        physical_address = attrs.pop('physical_address', '')
        postal_address = attrs.pop('postal_address', '')
        county_of_residence = attrs.pop('county_of_residence', '')
        alternative_phone = attrs.pop('alternative_phone', '')
        
        if town:
            attrs['city'] = town
        if estate_name:
            attrs['estate_name'] = estate_name
        if physical_address:
            attrs['address'] = physical_address
        if postal_address:
            attrs['postal_address'] = postal_address
        if county_of_residence:
            attrs['county'] = county_of_residence
        if alternative_phone:
            attrs['secondary_phone_no'] = alternative_phone
        
        # Handle KRA PIN
        kra_pin = attrs.pop('kra_pin', None)
        if kra_pin:
            attrs['kra_pin'] = kra_pin.upper().strip()
        
        # Handle Passport Number
        passport_no = attrs.pop('passport_no', None)
        if passport_no:
            attrs['passport_no'] = passport_no.upper().strip()
        
        # Handle Disability
        has_disability = attrs.pop('has_disability', False)
        attrs['person_living_with_disability'] = has_disability
        
        disability_category = attrs.pop('disability_category', None)
        if has_disability and disability_category:
            attrs['disability_category'] = disability_category
        
        # Validate identification - either ID number or Passport number must be provided
        id_number = attrs.get('id_number')
        passport_no_final = attrs.get('passport_no')
        
        if not id_number and not passport_no_final:
            raise serializers.ValidationError({
                "id_number": "Either National ID Number or Passport Number is required"
            })
        
        # Validate ID number format for Kenyans
        if nationality == 'Kenyan' and id_number:
            id_str = str(id_number)
            if not id_str.isdigit() or len(id_str) != 8:
                raise serializers.ValidationError({"id_number": "ID Number must be 8 digits"})
        
        # Validate passport number format
        if passport_no_final:
            passport_str = str(passport_no_final)
            if len(passport_str) < 6 or len(passport_str) > 9:
                raise serializers.ValidationError({"passport_no": "Passport number must be 6-9 characters"})
        
        # Check for duplicates
        if id_number and User.objects.filter(id_number=id_number).exists():
            raise serializers.ValidationError({"id_number": "User with this ID Number already exists."})
        
        if passport_no_final and User.objects.filter(passport_no=passport_no_final).exists():
            raise serializers.ValidationError({"passport_no": "User with this Passport Number already exists."})
        
        if User.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})
        
        if User.objects.filter(phone_no=attrs.get('phone_no')).exists():
            raise serializers.ValidationError({"phone_no": "User with this phone number already exists."})
        
        if User.objects.filter(username=attrs.get('username')).exists():
            raise serializers.ValidationError({"username": "Username already taken."})
        
        return attrs
    
    def _generate_verification_code(self):
        """Generate 6-digit verification code"""
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    def _send_verification_email(self, user, token, code):
        """Send verification email to user"""
        try:
            # Build verification URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://mobile.ufaa.go.ke')
            verification_url = f"{frontend_url}/verify-email?token={token}&email={user.email}"
            
            # Send email
            subject = 'Verify Your UFAA Account'
            html_message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify Your UFAA Account</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        margin: 0;
                        padding: 0;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background-color: #262561;
                        padding: 20px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .header h1 {{
                        color: #E4B355;
                        margin: 0;
                        font-size: 24px;
                    }}
                    .content {{
                        background-color: #ffffff;
                        padding: 30px;
                        border: 1px solid #e0e0e0;
                        border-top: none;
                        border-radius: 0 0 10px 10px;
                    }}
                    .verification-link {{
                        background-color: #E4B355;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 5px;
                        display: inline-block;
                        margin: 20px 0;
                    }}
                    .code-box {{
                        background-color: #f5f5f5;
                        padding: 20px;
                        border-radius: 8px;
                        text-align: center;
                        margin: 20px 0;
                        border: 1px dashed #262561;
                    }}
                    .code {{
                        font-size: 28px;
                        font-weight: bold;
                        letter-spacing: 5px;
                        color: #262561;
                        font-family: monospace;
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        font-size: 12px;
                        color: #666;
                        border-top: 1px solid #e0e0e0;
                        margin-top: 20px;
                    }}
                    .warning {{
                        background-color: #fff3cd;
                        border: 1px solid #ffecb5;
                        color: #856404;
                        padding: 12px;
                        border-radius: 5px;
                        margin: 20px 0;
                        font-size: 12px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to UFAA Reunite</h1>
                    </div>
                    <div class="content">
                        <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                        <p>Thank you for registering with the Unclaimed Financial Assets Authority (UFAA). Please verify your email address to activate your account.</p>
                        
                        <div style="text-align: center;">
                            <a href="{verification_url}" class="verification-link">Verify Email Address</a>
                        </div>
                        
                        <div class="code-box">
                            <p><strong>Or enter this verification code:</strong></p>
                            <div class="code">{code}</div>
                            <p style="margin-top: 10px; font-size: 12px;">Enter this code in the UFAA app to verify your email</p>
                        </div>
                        
                        <div class="warning">
                            <strong>⚠️ Important:</strong> This verification link and code will expire in 24 hours.
                        </div>
                        
                        <p>If you did not create an account with UFAA, please ignore this email.</p>
                        
                        <p><strong>Need help?</strong> Contact our support team:<br>
                        Email: info@ufaa.go.ke<br>
                        Phone: +254 20 1234567</p>
                    </div>
                    <div class="footer">
                        <p>© {timezone.now().year} Unclaimed Financial Assets Authority. All rights reserved.</p>
                        <p>This is an automated message, please do not reply.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text fallback
            plain_message = f"""
            Welcome to UFAA Reunite!
            
            Dear {user.get_full_name() or user.username},
            
            Thank you for registering. Please verify your email address to activate your account.
            
            Click the link below to verify your email:
            {verification_url}
            
            Or enter this verification code: {code}
            
            This verification link and code will expire in 24 hours.
            
            If you did not create an account with UFAA, please ignore this email.
            
            Need help? Contact our support team:
            Email: info@ufaa.go.ke
            Phone: +254 20 1234567
            
            © 2024 Unclaimed Financial Assets Authority. All rights reserved.
            """
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            print(f"✅ Verification email sent to {user.email}")
        except Exception as e:
            # Log error but don't fail registration
            print(f"❌ Failed to send verification email to {user.email}: {e}")
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        
        # Set username from email if not provided or invalid
        username = validated_data.get('username')
        if not username or len(username) < 3:
            email = validated_data.get('email', '')
            username = email.split('@')[0] if email else f"user_{validated_data.get('phone_no', '')[-6:]}"
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            validated_data['username'] = username
        
        # Generate verification token and code
        verification_token = get_random_string(length=64)
        verification_code = self._generate_verification_code()
        
        validated_data['verification_token'] = verification_token
        validated_data['temporary_verification_code'] = verification_code
        validated_data['is_verified'] = False  # Email not verified yet
        
        # Create user
        user = User.objects.create_user(**validated_data)
        
        # Set additional fields
        if validated_data.get('citizenship') == 'Kenyan':
            user.residence = 'Kenyan'
        
        user.save()
        
        # Send verification email (don't fail registration if email fails)
        try:
            self._send_verification_email(user, verification_token, verification_code)
        except Exception as e:
            print(f"⚠️ Verification email sending failed but user created: {e}")
        
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=False, allow_blank=True)
    verification_code = serializers.CharField(required=False, allow_blank=True, max_length=6, min_length=6)
    
    def validate(self, attrs):
        email = attrs.get('email')
        token = attrs.get('token', '')
        verification_code = attrs.get('verification_code', '')
        
        if not token and not verification_code:
            raise serializers.ValidationError(
                "Either verification token or code is required"
            )
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist"})
        
        if user.is_verified:
            raise serializers.ValidationError({"email": "Email already verified"})
        
        # Check token or code
        if token and user.verification_token == token:
            attrs['user'] = user
            return attrs
        
        if verification_code and hasattr(user, 'temporary_verification_code'):
            if user.temporary_verification_code == verification_code:
                attrs['user'] = user
                return attrs
        
        raise serializers.ValidationError(
            "Invalid or expired verification token/code"
        )
    
    def save(self):
        user = self.validated_data['user']
        user.is_verified = True
        user.verification_token = ''
        user.temporary_verification_code = ''
        user.save(update_fields=['is_verified', 'verification_token', 'temporary_verification_code'])
        
        return user


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    
    def _generate_verification_code(self):
        """Generate 6-digit verification code"""
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    def _send_verification_email(self, user, token, code):
        """Send verification email to user"""
        try:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://mobile.ufaa.go.ke')
            verification_url = f"{frontend_url}/verify-email?token={token}&email={user.email}"
            
            subject = 'Verify Your UFAA Account - New Verification Link'
            html_message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Verify Your UFAA Account</title>
            </head>
            <body style="font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #262561;">Email Verification</h2>
                    <p>We received a request to resend the verification email.</p>
                    
                    <div style="margin: 30px 0;">
                        <a href="{verification_url}" 
                           style="background-color: #E4B355; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 5px; display: inline-block;">
                            Verify Email Address
                        </a>
                    </div>
                    
                    <div style="margin: 30px 0; padding: 20px; background-color: #f5f5f5; border-radius: 5px;">
                        <h3>Verification Code</h3>
                        <p style="font-size: 24px; font-weight: bold; letter-spacing: 5px; color: #262561;">
                            {code}
                        </p>
                        <p>Enter this code in the UFAA app to verify your email.</p>
                    </div>
                    
                    <p>This verification link and code will expire in 24 hours.</p>
                    
                    <hr>
                    <p style="color: #666; font-size: 12px;">
                        If you didn't request this, please ignore this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            plain_message = f"""
            Email Verification
            
            We received a request to resend the verification email.
            
            Click the link below to verify your email:
            {verification_url}
            
            Or enter this verification code: {code}
            
            This verification link and code will expire in 24 hours.
            
            If you didn't request this, please ignore this email.
            """
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            print(f"✅ Resent verification email to {user.email}")
        except Exception as e:
            print(f"❌ Failed to resend verification email to {user.email}: {e}")
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if user.is_verified:
                raise serializers.ValidationError("Email already verified")
            self.user = user
        except User.DoesNotExist:
            raise serializers.ValidationError("No user found with this email")
        return value
    
    def save(self):
        # Generate new verification token and code
        new_token = get_random_string(length=64)
        new_code = self._generate_verification_code()
        
        self.user.verification_token = new_token
        self.user.temporary_verification_code = new_code
        self.user.save(update_fields=['verification_token', 'temporary_verification_code'])
        
        # Send new verification email
        self._send_verification_email(self.user, new_token, new_code)
        
        return self.user


class CheckVerificationStatusSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            self.user = user
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")
        return value
    
    def to_representation(self, instance):
        return {
            'email': self.user.email,
            'is_verified': self.user.is_verified,
            'username': self.user.username,
            'full_name': self.user.get_full_name() or self.user.name or self.user.username,
        }


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True, help_text="ID Number, Email, or Phone Number")
    password = serializers.CharField(required=True, write_only=True)
    device_fingerprint = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        identifier = attrs.get('identifier')
        password = attrs.get('password')
        
        user = None
        
        # Check if identifier is email
        if '@' in identifier and '.' in identifier:
            user = User.objects.filter(email=identifier).first()
        
        # Check if identifier is id_number (8 digits)
        elif identifier.isdigit() and len(identifier) == 8:
            user = User.objects.filter(id_number=identifier).first()
        
        # Check if identifier is phone number
        elif identifier.startswith('0') or identifier.startswith('+') or identifier.startswith('07') or identifier.startswith('01'):
            clean_phone = identifier
            if clean_phone.startswith('+254'):
                clean_phone = '0' + clean_phone[4:]
            user = User.objects.filter(phone_no__icontains=clean_phone[-9:]).first()
        
        # Try as passport number
        else:
            user = User.objects.filter(passport_no=identifier).first()
        
        if not user:
            raise serializers.ValidationError("Invalid credentials. Please check your ID Number, Email, or Phone Number.")
        
        # Get request from context for axes
        request = self.context.get('request')
        
        # Authenticate
        if request:
            auth_user = authenticate(request=request, username=user.username, password=password)
        else:
            auth_user = authenticate(username=user.username, password=password)
        
        if not auth_user:
            raise serializers.ValidationError("Invalid password.")
        
        # Check if email is verified
        if not auth_user.is_verified:
            raise serializers.ValidationError(
                "Please verify your email address before logging in. "
                "Check your inbox for the verification link."
            )
        
        if not auth_user.is_active:
            raise serializers.ValidationError("User account is disabled.")
        
        attrs['user'] = auth_user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "New passwords don't match."})
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    id_number = serializers.CharField(required=True, help_text="ID Number")
    
    def validate_id_number(self, value):
        if not User.objects.filter(id_number=value).exists():
            raise serializers.ValidationError("No user found with this ID Number.")
        return value


class ResetPasswordSerializer(serializers.Serializer):
    id_number = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "Passwords don't match."})
        
        if not User.objects.filter(id_number=attrs['id_number']).exists():
            raise serializers.ValidationError({"id_number": "User with this ID Number not found."})
        
        return attrs


class StaffProfileSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    id_number = serializers.SerializerMethodField()
    
    class Meta:
        model = StaffProfile
        fields = [
            'id', 'user', 'user_details', 'employee_id', 'department',
            'position', 'supervisor', 'hire_date', 'profile_id',
            'full_name', 'email', 'id_number', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()
    
    def get_email(self, obj):
        return obj.user.email
    
    def get_id_number(self, obj):
        return obj.user.id_number
