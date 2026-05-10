from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import models
from .models import User, StaffProfile


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
            'gps_location', 'profile_picture', 'date_of_birth', 'is_verified', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified']
    
    def get_full_name(self, obj):
        return obj.get_full_name()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'confirm_password',
            'first_name', 'last_name', 'id_number', 'phone_no',
            'date_of_birth', 'gender'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        id_number = attrs.get('id_number')
        if id_number:
            id_str = str(id_number)
            if not id_str.isdigit() or len(id_str) != 8:
                raise serializers.ValidationError({"id_number": "ID Number must be 8 digits"})
        
        if User.objects.filter(id_number=attrs.get('id_number')).exists():
            raise serializers.ValidationError({"id_number": "User with this ID Number already exists."})
        
        if User.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})
        
        if User.objects.filter(phone_no=attrs.get('phone_no')).exists():
            raise serializers.ValidationError({"phone_no": "User with this phone number already exists."})
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        return user


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
        
        # Get request from context
        request = self.context.get('request')
        
        # Authenticate using username with request for axes
        if request:
            auth_user = authenticate(request=request, username=user.username, password=password)
        else:
            auth_user = authenticate(username=user.username, password=password)
        
        if not auth_user:
            raise serializers.ValidationError("Invalid password.")
        
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