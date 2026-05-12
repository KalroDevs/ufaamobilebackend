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
    town = serializers.CharField(write_only=True, required=False, allow_blank=True)
    estate_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    physical_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    postal_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    county_of_residence = serializers.CharField(write_only=True, required=False, allow_blank=True)
    alternative_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'confirm_password',
            'first_name', 'last_name', 'surname', 'other_names',
            'id_number', 'phone_no', 'alternative_phone',
            'date_of_birth', 'gender', 'nationality',
            'town', 'estate_name', 'physical_address', 'postal_address',
            'county_of_residence', 'citizenship'
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
        
        # Validate ID number format for Kenyans
        id_number = attrs.get('id_number')
        if nationality == 'Kenyan' and id_number:
            id_str = str(id_number)
            if not id_str.isdigit() or len(id_str) != 8:
                raise serializers.ValidationError({"id_number": "ID Number must be 8 digits"})
        
        # Check for duplicates
        if User.objects.filter(id_number=attrs.get('id_number')).exists():
            raise serializers.ValidationError({"id_number": "User with this ID Number already exists."})
        
        if User.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})
        
        if User.objects.filter(phone_no=attrs.get('phone_no')).exists():
            raise serializers.ValidationError({"phone_no": "User with this phone number already exists."})
        
        if User.objects.filter(username=attrs.get('username')).exists():
            raise serializers.ValidationError({"username": "Username already taken."})
        
        return attrs
    
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
        
        # Create user
        user = User.objects.create_user(**validated_data)
        
        # Set additional fields
        if validated_data.get('citizenship') == 'Kenyan':
            user.residence = 'Kenyan'
        
        user.save()
        
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
        
        # Get request from context for axes
        request = self.context.get('request')
        
        # Authenticate
        if request:
            from django.contrib.auth import authenticate
            auth_user = authenticate(request=request, username=user.username, password=password)
        else:
            from django.contrib.auth import authenticate
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