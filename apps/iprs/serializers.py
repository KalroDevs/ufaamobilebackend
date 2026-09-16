# apps/iprs/serializers.py
from rest_framework import serializers
from .models import IprsSearchLog, IprsCache


class IprsLookupRequestSerializer(serializers.Serializer):
    """Serializer for IPRS lookup requests (public - no auth required)"""
    
    id_card = serializers.CharField(
        required=True,
        max_length=20,
        help_text="National ID number to look up (7-8 digits)"
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Whether to use cached results if available"
    )
    device_fingerprint = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Optional device fingerprint from the mobile app"
    )
    
    def validate_id_card(self, value):
        """Validate and normalize the ID card number"""
        # Convert to string and strip whitespace
        value = str(value).strip()
        
        # Remove any non-digit characters
        value = ''.join(c for c in value if c.isdigit())
        
        if not value:
            raise serializers.ValidationError("ID card number is required")
        
        if len(value) < 7 or len(value) > 8:
            raise serializers.ValidationError(
                f"Invalid ID card number. Kenyan National IDs must be 7-8 digits "
                f"(received {len(value)} digits)."
            )
        
        return value


class IprsPersonalDetailsSerializer(serializers.Serializer):
    """
    Serializer for IPRS personal details response.
    
    Name conventions (Kenyan):
        - surname: Family name
        - other_names: first_Name + other_Name combined
        - full_name: surname + other_names
    """
    
    id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="IPRS internal ID"
    )
    idCard = serializers.CharField(
        help_text="National ID number"
    )
    surname = serializers.CharField(
        help_text="Surname (family name)"
    )
    other_names = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Other names (first name + other name combined)"
    )
    gender = serializers.CharField(
        help_text="Gender (M/F)"
    )
    searchedAt = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Timestamp of IPRS search"
    )
    
    # Computed fields
    full_name = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    
    def get_full_name(self, obj):
        """Return the full name: Surname OtherNames"""
        surname = (obj.get('surname') or '').strip()
        other_names = (obj.get('other_names') or '').strip()
        return ' '.join(p for p in [surname, other_names] if p).strip()
    
    def get_gender_display(self, obj):
        """Return human-readable gender"""
        gender = obj.get('gender', '').upper()
        return {'M': 'Male', 'F': 'Female'}.get(gender, gender)


class IprsSearchLogSerializer(serializers.ModelSerializer):
    """Serializer for IPRS search logs (admin/staff view)"""
    
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = IprsSearchLog
        fields = [
            'id', 'id_card', 'requested_from_ip', 'user_agent',
            'device_fingerprint', 'status', 'surname', 'other_names',
            'full_name', 'gender', 'iprs_id', 'searched_at',
            'response_time_ms', 'created_at', 'error_message'
        ]
        read_only_fields = fields


class IprsCacheSerializer(serializers.ModelSerializer):
    """Serializer for IPRS cache entries"""
    
    full_name = serializers.CharField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = IprsCache
        fields = [
            'id', 'id_card', 'surname', 'other_names',
            'full_name', 'gender', 'iprs_id', 'is_valid', 'cached_at',
            'expires_at', 'is_expired'
        ]
        read_only_fields = fields


class IprsBulkLookupSerializer(serializers.Serializer):
    """Serializer for bulk IPRS lookups"""
    
    id_cards = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=True,
        min_length=1,
        max_length=50,
        help_text="List of ID numbers to look up (max 50)"
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True
    )
    device_fingerprint = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255
    )
    
    def validate_id_cards(self, value):
        """Validate and normalize all ID cards"""
        validated = []
        errors = []
        
        for i, id_card in enumerate(value):
            id_card = str(id_card).strip()
            id_card = ''.join(c for c in id_card if c.isdigit())
            
            if len(id_card) < 7 or len(id_card) > 8:
                errors.append(f"Invalid ID at position {i}: {id_card}")
            else:
                validated.append(id_card)
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return validated
