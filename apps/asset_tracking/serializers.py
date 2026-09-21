# apps/asset_tracking/serializers.py
import math

from rest_framework import serializers

from .models import TrackedAsset, AssetLocationLog, AssetTrackingDocument


# ==================== OUTPUT SERIALIZERS ====================

class AssetLocationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetLocationLog
        fields = [
            'id', 'status', 'notes',
            'staff_email', 'staff_name',
            'staff_latitude', 'staff_longitude',
            'distance_km', 'created_at',
        ]
        read_only_fields = fields


class AssetTrackingDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = AssetTrackingDocument
        fields = [
            'id', 'document_type', 'document_name',
            'file', 'file_url', 'file_size', 'file_extension',
            'uploaded_by_email', 'uploaded_at', 'notes',
        ]
        read_only_fields = [
            'id', 'file_size', 'file_extension',
            'uploaded_by_email', 'uploaded_at',
        ]

    def get_file_url(self, obj):
        try:
            return obj.file.url if obj.file else None
        except Exception:
            return None


class TrackedAssetSerializer(serializers.ModelSerializer):
    documents = AssetTrackingDocumentSerializer(many=True, read_only=True)
    location_logs = AssetLocationLogSerializer(many=True, read_only=True)

    class Meta:
        model = TrackedAsset
        fields = [
            'id',
            'asset_no', 'asset_name', 'asset_owner',
            'holder_name', 'holder_no', 'asset_type', 'source',
            'id_number', 'passport_no', 'cds_account_no',
            'postal_address', 'city_town', 'county', 'physical_address',
            'latitude', 'longitude',
            'status', 'last_notes',
            'staff_email', 'staff_name',
            'last_tracked_at', 'last_tracked_by',
            'last_staff_latitude', 'last_staff_longitude',
            'created_at', 'updated_at',
            'documents', 'location_logs',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'staff_email', 'staff_name',
            'last_tracked_at', 'last_tracked_by',
            'last_staff_latitude', 'last_staff_longitude',
        ]


# ==================== INPUT SERIALIZER ====================

class FlexibleDecimalField(serializers.DecimalField):
    """
    A DecimalField that silently normalises "no value" tokens to None
    instead of raising a validation error.

    Accepts:
      - numbers (int / float / Decimal)
      - numeric strings ("-1.234567")
      - empty strings ("")           -> None
      - the literal string "null"    -> None
      - the literal string "none"    -> None
      - the literal string "nil"     -> None
      - the literal string "nan"     -> None
      - the literal string "inf"
      - the literal string "-inf"
      - the literal string "infinity"/"+infinity"/"-infinity"
      - None                          -> None (when allow_null=True)
      - float('nan') / float('inf')   -> None
      - Decimal('NaN') / Decimal('Inf') -> None

    This matches the reality of mobile payloads, where a missing
    coordinate can arrive in any of those forms.
    """

    _NULL_STRINGS = {
        'null', 'none', 'nil',
        'nan', 'inf', '+inf', '-inf',
        'infinity', '+infinity', '-infinity',
    }

    def to_internal_value(self, data):
        # --- Normalise "no value" cases to None ---
        if data is None:
            return None

        # Raw float non-finite values
        if isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return None

        # Decimal non-finite values
        try:
            from decimal import Decimal as _Decimal
            if isinstance(data, _Decimal):
                if data.is_nan() or data.is_infinite():
                    return None
        except Exception:
            pass

        # Strings: normalise common "not a number" markers to None
        if isinstance(data, str):
            stripped = data.strip()
            if stripped == '':
                return None
            if stripped.lower() in self._NULL_STRINGS:
                return None

        # --- Fall through to DRF for real numeric values ---
        try:
            value = super().to_internal_value(data)
        except (TypeError, ValueError, serializers.ValidationError):
            raise serializers.ValidationError(
                'A valid number is required.'
            )

        # Post-parse guard against Decimal('NaN') / Decimal('Infinity')
        try:
            if value is not None and (value.is_nan() or value.is_infinite()):
                return None
        except AttributeError:
            pass

        return value


class TrackedAssetCreateSerializer(serializers.Serializer):
    """
    Used when a staff member starts tracking an asset.

    The client no longer sends the staff's position, so those two
    fields are not declared here. If an older build still sends them,
    DRF simply ignores unknown keys.
    """

    STATUS_CHOICES = ['pending', 'found', 'not_found', 'moved', 'transferred']

    # --- Identity of the tracked asset ---
    asset_no = serializers.CharField(max_length=100)
    asset_name = serializers.CharField(
        max_length=255, allow_blank=True, required=False, default=''
    )
    asset_owner = serializers.CharField(
        max_length=255, allow_blank=True, required=False, default=''
    )
    holder_name = serializers.CharField(
        max_length=255, allow_blank=True, required=False, default=''
    )
    holder_no = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=''
    )
    asset_type = serializers.CharField(
        max_length=50, allow_blank=True, required=False, default=''
    )
    source = serializers.CharField(
        max_length=50, allow_blank=True, required=False, default=''
    )

    # --- Owner identifiers ---
    id_number = serializers.CharField(
        max_length=50, allow_blank=True, required=False, default=''
    )
    passport_no = serializers.CharField(
        max_length=50, allow_blank=True, required=False, default=''
    )
    cds_account_no = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=''
    )

    # --- Address snapshot ---
    postal_address = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default=''
    )
    city_town = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=''
    )
    county = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=''
    )
    physical_address = serializers.CharField(
        allow_blank=True, required=False, default=''
    )

    # --- Asset coordinates (tolerant to empty strings, NaN, inf) ---
    latitude = FlexibleDecimalField(
        max_digits=10,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    longitude = FlexibleDecimalField(
        max_digits=10,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

    # --- Tracking state ---
    status = serializers.CharField(
        max_length=20,
        required=False,
        default='pending',
    )
    notes = serializers.CharField(
        allow_blank=True, required=False, default=''
    )

    # ---------------------------------------------------------------- #
    # Field-level validation
    # ---------------------------------------------------------------- #

    def validate_asset_no(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError(
                'asset_no cannot be blank.'
            )
        return value

    def validate_status(self, value):
        value = (value or '').strip().lower()
        if value not in self.STATUS_CHOICES:
            raise serializers.ValidationError(
                f'status must be one of: {", ".join(self.STATUS_CHOICES)}'
            )
        return value

    # ---------------------------------------------------------------- #
    # Normalise the whole payload
    # ---------------------------------------------------------------- #

    def to_internal_value(self, data):
        # Trim whitespace from every string before DRF validates it.
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned[key] = value.strip()
            else:
                cleaned[key] = value

        return super().to_internal_value(cleaned)
