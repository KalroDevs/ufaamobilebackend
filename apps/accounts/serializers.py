# apps/accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.db import models

from .models import User, StaffProfile, AccountDeletionRequest, Notification

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
            'date_of_birth', 'is_verified', 'created_at', 'updated_at',
            'is_deleted', 'deleted_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'is_verified',
            'is_deleted', 'deleted_at',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.name or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)

    surname = serializers.CharField(write_only=True, required=False, allow_blank=True)
    other_names = serializers.CharField(write_only=True, required=False, allow_blank=True)
    nationality = serializers.CharField(write_only=True, required=False, default='Kenyan')

    town = serializers.CharField(write_only=True, required=False, allow_blank=True)
    estate_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    physical_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    postal_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    county_of_residence = serializers.CharField(write_only=True, required=False, allow_blank=True)
    alternative_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
            'kra_pin', 'passport_no', 'has_disability', 'disability_category',
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        surname = attrs.pop('surname', '')
        other_names = attrs.pop('other_names', '')
        if surname:
            attrs['first_name'] = surname
        if other_names:
            attrs['last_name'] = other_names
            attrs['name'] = f"{surname} {other_names}".strip()

        nationality = attrs.pop('nationality', 'Kenyan')
        attrs['citizenship'] = nationality
        if nationality == 'Kenyan':
            attrs['residence'] = 'Kenyan'

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

        kra_pin = attrs.pop('kra_pin', None)
        if kra_pin:
            attrs['kra_pin'] = kra_pin.upper().strip()

        passport_no = attrs.pop('passport_no', None)
        if passport_no:
            attrs['passport_no'] = passport_no.upper().strip()

        has_disability = attrs.pop('has_disability', False)
        attrs['person_living_with_disability'] = has_disability

        disability_category = attrs.pop('disability_category', None)
        if has_disability and disability_category:
            attrs['disability_category'] = disability_category

        id_number = attrs.get('id_number')
        passport_no_final = attrs.get('passport_no')

        if not id_number and not passport_no_final:
            raise serializers.ValidationError({
                "id_number": "Either National ID Number or Passport Number is required"
            })

        #if nationality == 'Kenyan' and id_number:
        #    id_str = str(id_number)
        #    if not id_str.isdigit() or len(id_str) < 9:
        #        raise serializers.ValidationError({"id_number": "ID Number must be 7 or 8 digits"})


        if nationality == 'Kenyan' and id_number:
            id_str = str(id_number).strip()
            if not id_str.isdigit():
               raise serializers.ValidationError({
                   "id_number": "ID Number must contain digits only."
               })
            if len(id_str) not in (6, 7, 8):
               raise serializers.ValidationError({
                   "id_number": "ID Number must be 6, 7, or 8 digits."
                })


        if passport_no_final:
            passport_str = str(passport_no_final)
            if len(passport_str) < 6 or len(passport_str) > 9:
                raise serializers.ValidationError({"passport_no": "Passport number must be 6-9 characters"})

        if id_number and User.all_objects.filter(id_number=id_number).exists():
            raise serializers.ValidationError({"id_number": "User with this ID Number already exists."})

        if passport_no_final and User.all_objects.filter(passport_no=passport_no_final).exists():
            raise serializers.ValidationError({"passport_no": "User with this Passport Number already exists."})

        if User.all_objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})

        if User.all_objects.filter(phone_no=attrs.get('phone_no')).exists():
            raise serializers.ValidationError({"phone_no": "User with this phone number already exists."})

        if User.all_objects.filter(username=attrs.get('username')).exists():
            raise serializers.ValidationError({"username": "Username already taken."})

        return attrs

    def _generate_verification_code(self):
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])

    def _send_verification_email(self, user, token, code):
        try:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://mobile.ufaa.go.ke')
            verification_url = f"{frontend_url}/verify-email?token={token}&email={user.email}"

            subject = 'Verify Your UFAA Account'
            html_message = f"""
            <!DOCTYPE html>
            <html>
            <body>
                <h2>Welcome to UFAA Reunite</h2>
                <p>Dear {user.get_full_name() or user.username},</p>
                <p>Please verify your email address to activate your account.</p>
                <p><a href="{verification_url}">Verify Email Address</a></p>
                <p>Or enter this code: <b>{code}</b></p>
                <p>This link expires in 24 hours.</p>
            </body>
            </html>
            """
            plain_message = f"Verify your UFAA account: {verification_url} (code: {code})"

            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            print(f"Failed to send verification email to {user.email}: {e}")

    def create(self, validated_data):
        validated_data.pop('confirm_password')

        username = validated_data.get('username')
        if not username or len(username) < 3:
            email = validated_data.get('email', '')
            username = email.split('@')[0] if email else f"user_{validated_data.get('phone_no', '')[-6:]}"
            base_username = username
            counter = 1
            while User.all_objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            validated_data['username'] = username

        verification_token = get_random_string(length=64)
        verification_code = self._generate_verification_code()

        validated_data['verification_token'] = verification_token
        validated_data['temporary_verification_code'] = verification_code
        validated_data['is_verified'] = False

        user = User.objects.create_user(**validated_data)

        if validated_data.get('citizenship') == 'Kenyan':
            user.residence = 'Kenyan'

        user.save()

        try:
            self._send_verification_email(user, verification_token, verification_code)
        except Exception as e:
            print(f"Verification email sending failed but user created: {e}")

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
            raise serializers.ValidationError("Either verification token or code is required")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist"})

        if user.is_verified:
            raise serializers.ValidationError({"email": "Email already verified"})

        if token and user.verification_token == token:
            attrs['user'] = user
            return attrs

        if verification_code and hasattr(user, 'temporary_verification_code'):
            if user.temporary_verification_code == verification_code:
                attrs['user'] = user
                return attrs

        raise serializers.ValidationError("Invalid or expired verification token/code")

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
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])

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
        new_token = get_random_string(length=64)
        new_code = self._generate_verification_code()

        self.user.verification_token = new_token
        self.user.temporary_verification_code = new_code
        self.user.save(update_fields=['verification_token', 'temporary_verification_code'])
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
    identifier = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    device_fingerprint = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        identifier = attrs.get('identifier')
        password = attrs.get('password')

        user = None

        if '@' in identifier and '.' in identifier:
            user = User.objects.filter(email=identifier).first()
        elif identifier.isdigit() and len(identifier) == 8:
            user = User.objects.filter(id_number=identifier).first()
        elif identifier.startswith('0') or identifier.startswith('+') or identifier.startswith('07') or identifier.startswith('01'):
            clean_phone = identifier
            if clean_phone.startswith('+254'):
                clean_phone = '0' + clean_phone[4:]
            user = User.objects.filter(phone_no__icontains=clean_phone[-9:]).first()
        else:
            user = User.objects.filter(passport_no=identifier).first()

        # Deleted-account guard
        if user is None:
            lookup = models.Q()
            if '@' in identifier and '.' in identifier:
                lookup = models.Q(email=identifier)
            elif identifier.isdigit() and len(identifier) == 8:
                lookup = models.Q(id_number=identifier)
            elif identifier.startswith('0') or identifier.startswith('+'):
                clean_phone = identifier
                if clean_phone.startswith('+254'):
                    clean_phone = '0' + clean_phone[4:]
                lookup = models.Q(phone_no__icontains=clean_phone[-9:])
            else:
                lookup = models.Q(passport_no=identifier)

            soft_deleted = User.all_objects.filter(lookup, is_deleted=True).first()
            if soft_deleted is not None:
                raise serializers.ValidationError(
                    "This account has been deleted. If you believe this is a mistake, "
                    "please contact support."
                )

        if not user:
            raise serializers.ValidationError(
                "Invalid credentials. Please check your ID Number, Email, or Phone Number."
            )

        request = self.context.get('request')

        if request:
            auth_user = authenticate(request=request, username=user.username, password=password)
        else:
            auth_user = authenticate(username=user.username, password=password)

        if not auth_user:
            raise serializers.ValidationError("Invalid password.")

        if not auth_user.is_verified:
            raise serializers.ValidationError(
                "Please verify your email address before logging in. "
                "Check your inbox for the verification link."
            )

        if not auth_user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        attrs['user'] = auth_user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)

    def validate_identifier(self, value):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError

        user = None
        value = value.strip()

        if '@' in value and '.' in value:
            try:
                validate_email(value)
                user = User.objects.get(email=value)
            except (ValidationError, User.DoesNotExist):
                pass

        if not user and value.isdigit() and len(value) in [7, 8]:
            try:
                user = User.objects.get(id_number=value)
            except User.DoesNotExist:
                pass

        if not user:
            import re
            phone_clean = re.sub(r'[\s\-\(\)\+]', '', value)
            if phone_clean.startswith('0') and len(phone_clean) == 10:
                phone_clean = '254' + phone_clean[1:]
            elif phone_clean.startswith('7') and len(phone_clean) == 9:
                phone_clean = '254' + phone_clean
            elif phone_clean.startswith('+254') and len(phone_clean) == 13:
                phone_clean = phone_clean[1:]
            elif not phone_clean.startswith('254') and len(phone_clean) == 9:
                phone_clean = '254' + phone_clean

            try:
                user = User.objects.get(phone_no=phone_clean)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(secondary_phone_no=phone_clean)
                except User.DoesNotExist:
                    try:
                        user = User.objects.get(phone_no__endswith=phone_clean[-9:])
                    except User.DoesNotExist:
                        pass

        if not user:
            soft_deleted = None
            if '@' in value and '.' in value:
                soft_deleted = User.all_objects.filter(email=value, is_deleted=True).first()
            elif value.isdigit() and len(value) in [7, 8]:
                soft_deleted = User.all_objects.filter(id_number=value, is_deleted=True).first()

            if soft_deleted is not None:
                raise serializers.ValidationError(
                    "This account has been deleted. Password reset is not available."
                )

            raise serializers.ValidationError(
                "No user found with the provided identifier. Please check your email, ID number, or phone number."
            )

        self.context['user'] = user
        return value

    def save(self):
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        user = self.context['user']

        reset_token = get_random_string(length=64)
        user.reset_token = reset_token
        user.reset_token_created_at = timezone.now()
        user.save(update_fields=['reset_token', 'reset_token_created_at'])

        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://mobile.ufaa.go.ke').rstrip('/')
        reset_url = f"{frontend_url}/reset-password/?token={reset_token}"

        context = {
            'user': user,
            'reset_url': reset_url,
            'reset_token': reset_token,
            'expiry_hours': 1,
            'year': timezone.now().year,
        }

        subject = 'Reset Your UFAA Account Password'

        try:
            html_message = render_to_string('emails/password_reset_email.html', context)
            plain_message = strip_tags(html_message)

            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            print(f"Failed to send email to {user.email}: {e}")

        return {
            'email': user.email,
            'reset_token': reset_token,
            'message': 'Password reset instructions sent to your email.'
        }


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "New passwords don't match."})
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "Passwords don't match."})

        token = attrs.get('token')

        try:
            user = User.all_objects.get(reset_token=token)
        except User.DoesNotExist:
            raise serializers.ValidationError({"token": "Invalid reset token."})

        if user.is_deleted:
            raise serializers.ValidationError({
                "token": "This account has been deleted. Password reset is not available."
            })

        if user.reset_token_created_at:
            expiry_seconds = 3600
            seconds_passed = (timezone.now() - user.reset_token_created_at).seconds
            if seconds_passed > expiry_seconds:
                raise serializers.ValidationError(
                    {"token": "Reset token has expired. Please request a new one."}
                )
        else:
            raise serializers.ValidationError({"token": "Invalid reset token."})

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.reset_token = ''
        user.reset_token_created_at = None
        user.save(update_fields=['password', 'reset_token', 'reset_token_created_at'])
        return user


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


class DeleteAccountSerializer(serializers.Serializer):
    """
    Soft-delete the authenticated user's account.
    """

    TERMINAL_CLAIM_STATUSES = [
        'Rejected', 'Paid', 'Completed', 'Archived', 'Cancelled',
    ]

    password = serializers.CharField(write_only=True, required=True)
    confirm = serializers.BooleanField(required=True)
    reason = serializers.ChoiceField(
        choices=[
            'no_longer_needed',
            'privacy_concerns',
            'duplicate_account',
            'created_by_mistake',
            'too_many_emails',
            'switching_service',
            'other',
        ],
        required=False,
        allow_blank=True,
    )
    reason_details = serializers.CharField(
        required=False, allow_blank=True, max_length=1000
    )

    def validate(self, attrs):
        user = self.context.get('user')
        if user is None:
            raise serializers.ValidationError("User context is required.")

        if getattr(user, 'is_deleted', False):
            raise serializers.ValidationError(
                {"detail": "This account has already been deleted."}
            )

        if not attrs.get('confirm'):
            raise serializers.ValidationError({
                "confirm": "You must confirm that this action is permanent."
            })

        if not user.check_password(attrs.get('password', '')):
            raise serializers.ValidationError({
                "password": "Incorrect password."
            })

        if user.is_superuser or getattr(user, 'is_staff_member', False) or user.role == 'admin':
            raise serializers.ValidationError({
                "detail": (
                    "Staff and admin accounts cannot be deleted through "
                    "this endpoint. Contact a system administrator."
                )
            })

        from apps.claims.models import Claim
        open_claims = Claim.objects.filter(claimant=user).exclude(
            status__in=self.TERMINAL_CLAIM_STATUSES
        )
        if open_claims.exists():
            raise serializers.ValidationError({
                "detail": (
                    "You have open claims. Please close them or contact "
                    "support before deleting your account."
                )
            })

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        request = self.context.get('request')
        ip = self._get_client_ip(request)

        snapshot = {
            'user_id': user.id,
            'username': user.username,
            'email': user.email or '',
            'id_number': user.id_number or '',
            'phone_no': user.phone_no or '',
        }

        suffix = get_random_string(length=8)

        user.username = f"deleted_user_{user.id}_{suffix}"
        user.email = f"deleted_{user.id}_{suffix}@deleted.ufaa.local"
        user.e_mail = ''
        user.first_name = ''
        user.last_name = ''
        user.name = ''
        user.iprs_name = ''
        user.phone_no = f"deleted-{user.id}-{suffix}"[:17]
        user.secondary_phone_no = ''
        user.id_number = None
        user.passport_no = None
        user.kra_pin = ''
        user.business_registration_no = ''
        user.address = ''
        user.address_2 = ''
        user.postal_address = ''
        user.post_code = ''
        user.county = ''
        user.city = ''
        user.home_county = ''
        user.estate_name = ''
        user.gps_location = None
        user.profile_picture = None
        user.verification_token = ''
        user.temporary_verification_code = ''
        user.reset_token = ''
        user.reset_token_created_at = None
        user.device_fingerprint = ''
        user.is_active = False
        user.is_verified = False
        user.is_deleted = True
        user.deleted_at = timezone.now()
        user.deletion_reason = self.validated_data.get('reason', '')
        user.deletion_reason_details = self.validated_data.get('reason_details', '')
        user.deletion_requested_ip = ip

        user.save(update_fields=[
            'username', 'email', 'e_mail', 'first_name', 'last_name', 'name',
            'iprs_name', 'phone_no', 'secondary_phone_no', 'id_number',
            'passport_no', 'kra_pin', 'business_registration_no',
            'address', 'address_2', 'postal_address', 'post_code',
            'county', 'city', 'home_county', 'estate_name', 'gps_location',
            'profile_picture', 'verification_token',
            'temporary_verification_code', 'reset_token',
            'reset_token_created_at', 'device_fingerprint',
            'is_active', 'is_verified', 'is_deleted', 'deleted_at',
            'deletion_reason', 'deletion_reason_details',
            'deletion_requested_ip',
        ])

        AccountDeletionRequest.objects.create(
            **snapshot,
            reason=self.validated_data.get('reason', ''),
            reason_details=self.validated_data.get('reason_details', ''),
            ip_address=ip,
            user_agent=(request.META.get('HTTP_USER_AGENT', '') if request else ''),
        )

        return snapshot

    @staticmethod
    def _get_client_ip(request):
        if not request:
            return None
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return (
            request.META.get('HTTP_X_REAL_IP')
            or request.META.get('REMOTE_ADDR')
            or None
        )


# ==================== NOTIFICATIONS ====================

class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for the in-app Notification model.
    """

    class Meta:
        model = Notification
        fields = [
            'id',
            'category',
            'title',
            'body',
            'related_model',
            'related_object_id',
            'metadata',
            'is_read',
            'read_at',
            'created_at',
        ]
        read_only_fields = fields
