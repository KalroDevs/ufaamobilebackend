# apps/claims/serializers.py
from rest_framework import serializers
from decimal import Decimal
from .models import (
    Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
)
from django.contrib.auth import get_user_model

User = get_user_model()


class ClaimAssetSerializer(serializers.ModelSerializer):
    asset_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ClaimAsset
        fields = [
            'id', 'claim', 'asset_no', 'is_selected', 'asset_details',
            'asset_snapshot', 'value', 'holder_name', 'asset_type', 'source',
            'key', 'rejected', 'class_code', 'class_field',
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
    
    def get_asset_details(self, obj):
        """Get asset details from the live database using asset_no"""
        if obj.asset_no:
            try:
                from apps.live_operations.models import LiveUnclaimedAsset
                asset = LiveUnclaimedAsset.objects.using('ereunify').get(no=obj.asset_no)
                return {
                    'id': asset.no,
                    'asset_no': asset.no,
                    'holder_name': asset.holder_name,
                    'asset_type': asset.get_asset_type_display_name(),
                    'source': asset.get_source_display_name(),
                    'amount': float(asset.amount_due_to_owner) if asset.amount_due_to_owner else 0,
                    'status': asset.get_status_display_name(),
                    'is_claimable': asset.is_claimable(),
                    'owner_name': asset.get_full_name(),
                }
            except LiveUnclaimedAsset.DoesNotExist:
                pass
        return None


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


class ClaimSerializer(serializers.ModelSerializer):
    assets = ClaimAssetSerializer(source='claim_assets', many=True, read_only=True)
    documents = ClaimDocumentSerializer(many=True, read_only=True)
    notes = ClaimNoteSerializer(many=True, read_only=True)
    status_history = ClaimStatusHistorySerializer(many=True, read_only=True)
    asset_ids = serializers.ListField(write_only=True, required=False)
    status_display = serializers.CharField(read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    
    user_id = serializers.IntegerField(source='claimant.id', read_only=True)
    user_name = serializers.CharField(source='claimant.get_full_name', read_only=True)
    user_email = serializers.EmailField(source='claimant.email', read_only=True)
    
    class Meta:
        model = Claim
        fields = '__all__'
        read_only_fields = [
            'id', 'no', 'claimant', 'created_at', 'updated_at', 'submitted_at', 
            'approved_at', 'paid_at', 'status_display', 'progress_percentage',
            'user_id', 'user_name', 'user_email'
        ]
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation.get('amount') is not None:
            try:
                representation['amount'] = float(representation['amount'])
            except (ValueError, TypeError):
                representation['amount'] = 0.0
        return representation
    
    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if self.instance and self.instance.claimant != request.user:
                if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                    raise serializers.ValidationError(
                        "You do not have permission to modify this claim."
                    )
        return attrs
    
    def create(self, validated_data):
        asset_ids = validated_data.pop('asset_ids', [])
        request = self.context.get('request')
        
        if 'amount' in validated_data and validated_data['amount'] is not None:
            validated_data['amount'] = Decimal(str(validated_data['amount']))
        
        if request and request.user.is_authenticated:
            validated_data['claimant'] = request.user
        
        claim = Claim.objects.create(**validated_data)
        
        for asset_id in asset_ids:
            try:
                from apps.live_operations.models import LiveUnclaimedAsset
                asset = LiveUnclaimedAsset.objects.using('ereunify').get(no=str(asset_id))
                ClaimAsset.objects.create(
                    claim=claim,
                    asset_no=asset.no,
                    value=asset.amount_due_to_owner,
                    holder_name=asset.holder_name,
                    asset_type=asset.get_asset_type_display_name(),
                    source=asset.get_source_display_name(),
                    name=asset.get_full_name(),
                    id_number=asset.id_number,
                    description=asset.description,
                    cds_account_no=asset.cds_account_no,
                )
            except Exception as e:
                continue
        
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
        
        if request and request.user.is_authenticated:
            if instance.claimant != request.user:
                if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                    raise serializers.ValidationError(
                        "You do not have permission to modify this claim."
                    )
        
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
                    from apps.live_operations.models import LiveUnclaimedAsset
                    asset = LiveUnclaimedAsset.objects.using('ereunify').get(no=str(asset_id))
                    ClaimAsset.objects.create(
                        claim=instance,
                        asset_no=asset.no,
                        value=asset.amount_due_to_owner,
                        holder_name=asset.holder_name,
                        asset_type=asset.get_asset_type_display_name(),
                        source=asset.get_source_display_name(),
                        name=asset.get_full_name(),
                        id_number=asset.id_number,
                        description=asset.description,
                        cds_account_no=asset.cds_account_no,
                    )
                except Exception as e:
                    continue
        
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
        read_only_fields = ['no']
    
    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required to create a claim.")
        
        asset_ids = attrs.get('asset_ids', [])
        if not asset_ids:
            raise serializers.ValidationError({"asset_ids": "At least one asset is required to create a claim."})
        
        # Validate that all asset_ids exist in the live MSSQL database
        for asset_id in asset_ids:
            try:
                from apps.live_operations.models import LiveUnclaimedAsset
                if not LiveUnclaimedAsset.objects.using('ereunify').filter(no=str(asset_id)).exists():
                    raise serializers.ValidationError({"asset_ids": f"Asset with id {asset_id} does not exist."})
            except Exception as e:
                raise serializers.ValidationError({"asset_ids": f"Error validating asset {asset_id}: {e}"})
        
        attrs['claimant'] = request.user
        return attrs
    
    def create(self, validated_data):
        asset_ids = validated_data.pop('asset_ids', [])
        request = self.context.get('request')
        
        if 'amount' in validated_data and validated_data['amount'] is not None:
            validated_data['amount'] = Decimal(str(validated_data['amount']))
        
        claim = Claim.objects.create(**validated_data)
        
        linked_count = 0
        for asset_id in asset_ids:
            try:
                from apps.live_operations.models import LiveUnclaimedAsset
                asset = LiveUnclaimedAsset.objects.using('ereunify').get(no=str(asset_id))
                ClaimAsset.objects.create(
                    claim=claim,
                    asset_no=asset.no,
                    value=asset.amount_due_to_owner,
                    holder_name=asset.holder_name,
                    asset_type=asset.get_asset_type_display_name(),
                    source=asset.get_source_display_name(),
                    name=asset.get_full_name(),
                    id_number=asset.id_number,
                    description=asset.description,
                    cds_account_no=asset.cds_account_no,
                )
                linked_count += 1
            except Exception as e:
                continue
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status='',
            new_status=claim.status,
            changed_by=request.user if request else None,
            reason='Claim created'
        )
        
        return claim


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
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                identifier = attrs.get('identifier')
                search_type = attrs.get('search_type')
                user_claims = Claim.objects.filter(claimant=request.user)
                
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
        request = self.context.get('request')
        claim_id = self.context.get('claim_id')
        
        if claim_id:
            try:
                claim = Claim.objects.get(id=claim_id)
                if request and request.user.is_authenticated:
                    if claim.claimant != request.user:
                        if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                            raise serializers.ValidationError(
                                "You do not have permission to upload documents for this claim."
                            )
            except Claim.DoesNotExist:
                raise serializers.ValidationError("Claim does not exist.")
        
        return attrs
