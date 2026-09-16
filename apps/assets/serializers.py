from rest_framework import serializers
from .models import Asset, AssetLocation, AssetTrackingHistory


class AssetLocationSerializer(serializers.ModelSerializer):
    asset_no = serializers.CharField(source='asset.asset_no', read_only=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)
    
    class Meta:
        model = AssetLocation
        fields = [
            'id', 'asset', 'asset_no', 'asset_name', 'latitude', 'longitude',
            'address', 'building_name', 'floor', 'room_number',
            'additional_instructions', 'landmark', 'status', 'location_source',
            'notes', 'verified_by', 'verified_by_name', 'verified_at',
            'verification_photos', 'created_at', 'updated_at', 'last_verified'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AssetSerializer(serializers.ModelSerializer):
    location = AssetLocationSerializer(read_only=True)
    
    class Meta:
        model = Asset
        fields = [
            'id', 'asset_no', 'asset_type', 'source', 'class_code', 'class_field',
            'asset_code', 'description', 'description_field', 'first_name',
            'middle_name', 'last_name', 'holder_no', 'holder_name', 'name',
            'value', 'date_of_birth', 'id_number', 'passport_no', 'currency',
            'quantity', 'owners_postal_address', 'owners_city_town',
            'owners_telephone_no', 'interest_bearing_account', 'more_than_one_owner',
            'item_no', 'description_of_the_content', 'value_of_the_content',
            'safe_deposit_no', 'no_of_remitted_shares', 'cds_account_no',
            'cheque_no', 'amount_due_to_owner', 'account_no', 'currency_code',
            'drawee', 'cheque_date', 'drawee_id_number', 'physical_address',
            'latitude', 'longitude', 'is_claimed', 'status', 'synchronized',
            'batch_no', 'line_no', 'asset_appl_no', 'document_line_no',
            'base_unit_of_measure', 'value_lcy', 'posted', 'location_source',
            'reported_date', 'last_updated', 'location'
        ]
        read_only_fields = ['id', 'last_updated']


class AssetSearchSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    search_type = serializers.ChoiceField(
        choices=['id', 'passport', 'cds', 'bank', 'asset_no'],
        required=True
    )


class AssetLocationUpdateSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(required=True)
    status = serializers.ChoiceField(choices=['pending', 'found', 'not_found', 'transferred', 'verified'])
    notes = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True)
    building_name = serializers.CharField(required=False, allow_blank=True)
    floor = serializers.CharField(required=False, allow_blank=True)
    room_number = serializers.CharField(required=False, allow_blank=True)


class AssetTrackingHistorySerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    asset_no = serializers.CharField(source='asset.asset_no', read_only=True)
    
    class Meta:
        model = AssetTrackingHistory
        fields = [
            'id', 'asset', 'asset_no', 'previous_status', 'new_status',
            'notes', 'updated_by', 'updated_by_name', 'location',
            'latitude', 'longitude', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AssetBulkUploadSerializer(serializers.Serializer):
    assets = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )
    
    def validate_assets(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError("Cannot upload more than 1000 assets at once")
        return value