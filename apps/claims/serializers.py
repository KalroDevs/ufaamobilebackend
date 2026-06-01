# apps/claims/serializers.py
from rest_framework import serializers
from decimal import Decimal
from .models import (
    Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
)
from apps.assets.models import Asset
from apps.assets.serializers import AssetSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class ClaimAssetSerializer(serializers.ModelSerializer):
    asset_details = AssetSerializer(source='asset', read_only=True)
    asset_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = ClaimAsset
        fields = [
            'id', 'claim', 'asset', 'asset_id', 'asset_details', 'is_selected',
            'asset_snapshot', 'value', 'holder_name', 'asset_type', 'source',
            'key', 'rejected', 'asset_no', 'class_code', 'class_field',
            'asset_code', 'description', 'name', 'id_number',
            'cds_account_no', 'broker_name', 'broker_code', 'stock_exchange',
            'added_at'
        ]
        read_only_fields = ['id', 'added_at']
        extra_kwargs = {
            'cds_account_no': {'required': False, 'allow_null': True},
            'broker_name': {'required': False, 'allow_null': True},
            'broker_code': {'required': False, 'allow_null': True},
            'stock_exchange': {'required': False, 'allow_null': True},
        }


class ClaimDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    
    class Meta:
        model = ClaimDocument
        fields = [
            'id', 'claim', 'document_type', 'document_type_display',
            'document_name', 'file_path', 'file_size', 'file_extension',
            'uploaded_by', 'uploaded_by_name', 'uploaded_at',
            'is_verified', 'verified_by', 'verified_by_name', 'verified_at',
            'verification_notes', 'is_rejected', 'rejection_reason',
            'rejected_at', 'rejected_by', 'version', 'is_latest'
        ]
        read_only_fields = ['id', 'uploaded_at']


class ClaimNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    note_type_display = serializers.CharField(source='get_note_type_display', read_only=True)
    
    class Meta:
        model = ClaimNote
        fields = [
            'id', 'claim', 'note_type', 'note_type_display', 'content',
            'created_by', 'created_by_name', 'created_at', 'is_public'
        ]
        read_only_fields = ['id', 'created_at']


class ClaimStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    
    class Meta:
        model = ClaimStatusHistory
        fields = [
            'id', 'claim', 'previous_status', 'new_status',
            'changed_by', 'changed_by_name', 'reason', 'changed_at'
        ]
        read_only_fields = ['id', 'changed_at']


class ClaimSerializer(serializers.ModelSerializer):
    assets = ClaimAssetSerializer(source='claim_assets', many=True, read_only=True)
    documents = ClaimDocumentSerializer(many=True, read_only=True)
    notes = ClaimNoteSerializer(many=True, read_only=True)
    status_history = ClaimStatusHistorySerializer(many=True, read_only=True)
    asset_ids = serializers.ListField(write_only=True, required=False)
    status_display = serializers.CharField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    
    # User information fields
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Claim
        fields = '__all__'
        read_only_fields = [
            'id', 'no', 'user', 'created_at', 'updated_at', 'submitted_at', 
            'approved_at', 'paid_at', 'status_display', 'progress_percentage',
            'user_id', 'user_name', 'user_email'
        ]
    
    def to_representation(self, instance):
        """Ensure amount is returned as a float/number, not string"""
        representation = super().to_representation(instance)
        # Convert amount to float for JSON response
        if representation.get('amount') is not None:
            try:
                representation['amount'] = float(representation['amount'])
            except (ValueError, TypeError):
                representation['amount'] = 0.0
        return representation
    
    def validate(self, attrs):
        """Validate that the claim belongs to the authenticated user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # For update operations, ensure user owns the claim
            if self.instance and self.instance.user != request.user:
                # Staff users can modify claims if they have permission
                if not (request.user.is_staff or request.user.role in ['staff', 'admin']):
                    raise serializers.ValidationError(
                        "You do not have permission to modify this claim."
                    )
        return attrs
    
    def create(self, validated_data):
        asset_ids = validated_data.pop('asset_ids', [])
        request = self.context.get('request')
        
        # Ensure amount is properly set as Decimal
        if 'amount' in validated_data and validated_data['amount'] is not None:
            validated_data['amount'] = Decimal(str(validated_data['amount']))
        
        # Automatically set the user to the authenticated user
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user
        
        claim = Claim.objects.create(**validated_data)
        
        for asset_id in asset_ids:
            try:
                asset = Asset.objects.get(id=asset_id)
                ClaimAsset.objects.create(
                    claim=claim,
                    asset=asset,
                    value=asset.value,
                    holder_name=asset.holder_name,
                    asset_type=asset.asset_type,
                    source=asset.source,
                    asset_no=asset.asset_no,
                    cds_account_no=getattr(asset, 'cds_account_no', None),
                    broker_name=getattr(asset, 'broker_name', None),
                    broker_code=getattr(asset, 'broker_code', None),
                    stock_exchange=getattr(asset, 'stock_exchange', None)
                )
            except Asset.DoesNotExist:
                pass
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status='',
            new_status=claim.status,
            changed_by=request.user if request else None,
            reason='Claim created'
        )
        
        return claim
    
    def update(self, instance, validated_data):
        asset_ids = validated_data.pop('asset_ids', None)
        old_status = instance.status
        request = self.context.get('request')
        
        # Check if user owns the claim before updating
        if request and request.user.is_authenticated:
            if instance.user != request.user:
                if not (request.user.is_staff or request.user.role in ['staff', 'admin']):
                    raise serializers.ValidationError(
                        "You do not have permission to modify this claim."
                    )
        
        # Handle amount update
        if 'amount' in validated_data and validated_data['amount'] is not None:
            validated_data['amount'] = Decimal(str(validated_data['amount']))
        
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        
        if old_status != instance.status:
            ClaimStatusHistory.objects.create(
                claim=instance,
                previous_status=old_status,
                new_status=instance.status,
                changed_by=request.user if request else None,
                reason=f'Status changed from {old_status} to {instance.status}'
            )
        
        if asset_ids is not None:
            instance.claim_assets.all().delete()
            for asset_id in asset_ids:
                try:
                    asset = Asset.objects.get(id=asset_id)
                    ClaimAsset.objects.create(
                        claim=instance,
                        asset=asset,
                        value=asset.value,
                        holder_name=asset.holder_name,
                        asset_type=asset.asset_type,
                        source=asset.source,
                        asset_no=asset.asset_no,
                        cds_account_no=getattr(asset, 'cds_account_no', None),
                        broker_name=getattr(asset, 'broker_name', None),
                        broker_code=getattr(asset, 'broker_code', None),
                        stock_exchange=getattr(asset, 'stock_exchange', None)
                    )
                except Asset.DoesNotExist:
                    pass
        
        return instance


class ClaimCreateSerializer(serializers.ModelSerializer):
    asset_ids = serializers.ListField(write_only=True, required=True)
    
    class Meta:
        model = Claim
        fields = [
            'document_date', 'category', 'sub_category', 'agent_name',
            'claim_type', 'currency', 'asset_no', 'residence', 'id_number',
            'name', 'iprs_name', 'claimant_birth_date', 'gender',
            'person_living_with_disability', 'passport_no', 'claim_origin',
            'county_code', 'county_name', 'kra_pin', 'business_registration_no',
            'address', 'address_2', 'phone_no', 'secondary_phone_no',
            'post_code', 'county', 'city', 'home_county', 'e_mail',
            'posting_date', 'amount', 'amount_lcy', 'shares', 'safe_deposit',
            'location', 'location_sent_to', 'location_sent_to_name',
            'location_source', 'profile_id', 'submit', 'claimant_action_required',
            'payment_category', 'bank_code', 'bank_account_no', 'bank_account_name',
            'bank_name', 'branch_code', 'branch_name', 'account_currency',
            'swift_code', 'international_payment', 'international_bank_name',
            'international_branch_name', 'sort_code', 'country_region_code',
            'mpesa_mobile_no', 'asset_ids'
        ]
        read_only_fields = ['no']  # Make 'no' read-only since it's auto-generated
    
    def validate(self, attrs):
        """Validate and set the user from request"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required to create a claim.")
        return attrs
    
    def create(self, validated_data):
        asset_ids = validated_data.pop('asset_ids', [])
        request = self.context.get('request')
        
        # Automatically set the user to the authenticated user
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user
        
        # Handle amount if present
        if 'amount' in validated_data and validated_data['amount'] is not None:
            validated_data['amount'] = Decimal(str(validated_data['amount']))
        
        claim = Claim.objects.create(**validated_data)  # 'no' will be auto-generated
        
        for asset_id in asset_ids:
            try:
                asset = Asset.objects.get(id=asset_id)
                ClaimAsset.objects.create(
                    claim=claim,
                    asset=asset,
                    value=asset.value,
                    holder_name=asset.holder_name,
                    asset_type=asset.asset_type,
                    source=asset.source,
                    asset_no=asset.asset_no
                )
            except Asset.DoesNotExist:
                pass
        
        return claim


class ClaimStatusSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    current_step = serializers.SerializerMethodField()
    next_step = serializers.SerializerMethodField()
    total_assets_value = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    documents_uploaded = serializers.IntegerField(read_only=True)
    documents_verified = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Claim
        fields = [
            'no', 'status', 'status_display', 'progress_percentage',
            'current_step', 'next_step', 'total_assets_value',
            'documents_uploaded', 'documents_verified',
            'created_at', 'updated_at', 'submitted_at', 'approved_at', 'paid_at',
            'amount', 'internal_remarks', 'portal_comments', 'rejection_reason'
        ]
    
    def to_representation(self, instance):
        """Ensure amount is returned as a number"""
        representation = super().to_representation(instance)
        if representation.get('amount') is not None:
            try:
                representation['amount'] = float(representation['amount'])
            except (ValueError, TypeError):
                representation['amount'] = 0.0
        return representation
    
    def get_current_step(self, obj):
        step_map = {
            'Draft': 'Claim Created',
            'Pending': 'Document Verification',
            'Under_Review': 'Claim Review',
            'Approved': 'Approval Complete',
            'Paid': 'Payment Processing',
            'Completed': 'Claim Closed',
            'Rejected': 'Claim Rejected',
            'Archived': 'Claim Archived'
        }
        return step_map.get(obj.status, 'Unknown')
    
    def get_next_step(self, obj):
        next_map = {
            'Draft': 'Submit for Review',
            'Pending': 'Awaiting Document Verification',
            'Under_Review': 'Under Active Review',
            'Approved': 'Payment Initiation',
            'Paid': 'Payment Confirmation',
            'Completed': 'Claim Closed',
            'Rejected': 'Review Rejection Reason',
            'Archived': 'Claim Archived'
        }
        return next_map.get(obj.status, 'Contact Support')


class ClaimActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[
        'approve', 'reject', 'submit', 'archive', 'review', 
        'process_payment', 'complete'
    ])
    reason = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ClaimSearchSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    search_type = serializers.ChoiceField(
        choices=['claim_no', 'id_number', 'phone_no', 'name'],
        required=True
    )
    
    def validate(self, attrs):
        """Ensure the search is for the authenticated user's claims"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # For non-staff users, restrict search to their own claims
            if not (request.user.is_staff or request.user.role in ['staff', 'admin']):
                identifier = attrs.get('identifier')
                search_type = attrs.get('search_type')
                
                # Build queryset for user's claims
                user_claims = Claim.objects.filter(user=request.user)
                
                # Perform search within user's claims only
                if search_type == 'claim_no':
                    if not user_claims.filter(no=identifier).exists():
                        raise serializers.ValidationError(
                            "No claim found with this number for your account."
                        )
                elif search_type == 'id_number':
                    if not user_claims.filter(id_number=identifier).exists():
                        raise serializers.ValidationError(
                            "No claim found with this ID number for your account."
                        )
                elif search_type == 'phone_no':
                    if not user_claims.filter(phone_no=identifier).exists():
                        raise serializers.ValidationError(
                            "No claim found with this phone number for your account."
                        )
                elif search_type == 'name':
                    if not user_claims.filter(name__icontains=identifier).exists():
                        raise serializers.ValidationError(
                            "No claim found with this name for your account."
                        )
        return attrs


class ClaimDocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=[choice[0] for choice in ClaimDocument.DOCUMENT_TYPES])
    file = serializers.FileField()
    document_name = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        """Ensure the claim exists and belongs to the user"""
        request = self.context.get('request')
        claim_id = self.context.get('claim_id')
        
        if claim_id:
            try:
                claim = Claim.objects.get(id=claim_id)
                # Check if user owns the claim
                if request and request.user.is_authenticated:
                    if claim.user != request.user:
                        if not (request.user.is_staff or request.user.role in ['staff', 'admin']):
                            raise serializers.ValidationError(
                                "You do not have permission to upload documents for this claim."
                            )
            except Claim.DoesNotExist:
                raise serializers.ValidationError("Claim does not exist.")
        
        return attrs
