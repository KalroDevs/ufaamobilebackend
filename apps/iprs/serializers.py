# apps/iprs/serializers.py
from rest_framework import serializers
from .models import IprsCache, IprsSearchLog


class IprsLookupRequestSerializer(serializers.Serializer):
    """Serializer for IPRS lookup requests (public endpoint)."""

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
        default="",
        max_length=255,
        help_text="Optional device fingerprint from the mobile app"
    )

    def validate_id_card(self, value):
        """Validate and normalize the ID card number."""
        cleaned_value = ''.join(c for c in str(value).strip() if c.isdigit())

        if not cleaned_value:
            raise serializers.ValidationError("ID card number must contain digits.")

        if not (7 <= len(cleaned_value) <= 8):
            raise serializers.ValidationError(
                f"Invalid ID card number. Kenyan National IDs must be 7-8 digits "
                f"(received {len(cleaned_value)} digits)."
            )

        return cleaned_value


class IprsPersonalDetailsSerializer(serializers.Serializer):
    """
    Serializer for IPRS personal details output.
    Handles both Python dictionaries (raw API responses) and Model instances safely.
    """

    id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="IPRS internal ID"
    )
    idCard = serializers.CharField(
        source='id_card',
        required=False,
        help_text="National ID number"
    )
    surname = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Surname (family name)"
    )
    other_names = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Other names (first name + middle name)"
    )
    gender = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Gender (M/F)"
    )
    searchedAt = serializers.DateTimeField(
        source='searched_at',
        required=False,
        allow_null=True,
        help_text="Timestamp of IPRS search"
    )

    full_name = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()

    def _get_val(self, obj, key_snake, key_camel=None):
        """Helper to retrieve attribute value whether obj is a dict or Model instance."""
        if isinstance(obj, dict):
            return obj.get(key_snake) or (obj.get(key_camel) if key_camel else None)
        return getattr(obj, key_snake, None)

    def get_full_name(self, obj):
        """Return full name: Surname OtherNames."""
        surname = (self._get_val(obj, 'surname') or '').strip()
        other_names = (self._get_val(obj, 'other_names') or '').strip()
        full_name = ' '.join(p for p in [surname, other_names] if p).strip()
        return full_name or None

    def get_gender_display(self, obj):
        """Return human-readable gender."""
        gender = (self._get_val(obj, 'gender') or '').upper()
        mapping = {'M': 'Male', 'F': 'Female', 'MALE': 'Male', 'FEMALE': 'Female'}
        return mapping.get(gender, gender if gender else None)

    def to_representation(self, instance):
        """Ensure camelCase keys fallback correctly if dictionary input has camelCase directly."""
        ret = super().to_representation(instance)
        if isinstance(instance, dict):
            if not ret.get('idCard') and 'idCard' in instance:
                ret['idCard'] = instance['idCard']
            if not ret.get('searchedAt') and 'searchedAt' in instance:
                ret['searchedAt'] = instance['searchedAt']
        return ret


class IprsSearchLogSerializer(serializers.ModelSerializer):
    """Serializer for IPRS search logs (audit view)."""

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
    """Serializer for IPRS cache entries."""

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
    """Serializer for bulk IPRS lookups."""

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
        default="",
        max_length=255
    )

    def validate_id_cards(self, value):
        """Validate, normalize, and deduplicate all ID cards."""
        validated = []
        errors = []

        for i, raw_id in enumerate(value):
            cleaned_id = ''.join(c for c in str(raw_id).strip() if c.isdigit())

            if not (7 <= len(cleaned_id) <= 8):
                errors.append(f"Position {i}: '{raw_id}' is invalid. Kenyan IDs must be 7-8 digits.")
            else:
                validated.append(cleaned_id)

        if errors:
            raise serializers.ValidationError(errors)

        # Deduplicate while preserving order
        return list(dict.fromkeys(validated))
