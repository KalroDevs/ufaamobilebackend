from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models as django_models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from axes.decorators import axes_dispatch
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.models import User, LoginAttempt, UserActivityLog
from apps.accounts.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, 
    StaffProfileSerializer, ChangePasswordSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer
)
from apps.assets.models import Asset, AssetLocation, AssetTrackingHistory
from apps.assets.serializers import (
    AssetSerializer, AssetSearchSerializer, AssetLocationSerializer,
    AssetLocationUpdateSerializer, AssetTrackingHistorySerializer
)
from apps.claims.models import Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
from apps.claims.serializers import (
    ClaimSerializer, ClaimCreateSerializer, ClaimStatusSerializer,
    ClaimActionSerializer, ClaimSearchSerializer, ClaimDocumentSerializer,
    ClaimNoteSerializer, ClaimStatusHistorySerializer
)


class AuthViewSet(viewsets.GenericViewSet):
    """Authentication ViewSet for user registration, login, and password management"""
    
    permission_classes = [AllowAny]
    serializer_class = None
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            # Log the registration
            UserActivityLog.objects.create(
                user=user,
                activity_type='register',
                description=f'User registered with ID: {user.id_number}',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': 'Registration successful!'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """Login user with ID Number, Email, or Phone Number"""
        # Pass the request to the serializer context for axes
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Update device fingerprint if provided
            if request.data.get('device_fingerprint'):
                user.device_fingerprint = request.data['device_fingerprint']
                user.save()
            
            # Log successful login
            LoginAttempt.objects.create(
                user=user,
                identifier=request.data.get('identifier', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=request.data.get('device_fingerprint', '')
            )
            
            UserActivityLog.objects.create(
                user=user,
                activity_type='login',
                description=f'User logged in with ID: {user.id_number}',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': f'Welcome back, {user.get_full_name() or user.username}!'
            })
        
        # Log failed login attempt
        LoginAttempt.objects.create(
            user=None,
            identifier=request.data.get('identifier', ''),
            ip_address=request.META.get('REMOTE_ADDR'),
            success=False,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user by blacklisting refresh token"""
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Log the logout
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='logout',
                description='User logged out',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'old_password': 'Wrong password.'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            UserActivityLog.objects.create(
                user=user,
                activity_type='password_change',
                description='User changed password',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'message': 'Password changed successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Request password reset"""
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            id_number = serializer.validated_data['id_number']
            user = User.objects.get(id_number=id_number)
            
            # Generate reset token (simplified - in production use proper token)
            import hashlib
            import time
            token_string = f"{user.id}{time.time()}{user.id_number}"
            reset_token = hashlib.sha256(token_string.encode()).hexdigest()
            
            # In production, send token via email/SMS
            return Response({
                'message': f'Password reset instructions sent to {user.email or user.phone_no}',
                'reset_token': reset_token
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = User.objects.get(id_number=serializer.validated_data['id_number'])
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            return Response({'message': 'Password reset successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get current user profile"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user profile"""
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='profile_update',
                description='User updated profile',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AssetViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing and searching assets"""
    
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name', 'holder_name', 'id_number', 'asset_no']
    filterset_fields = ['asset_type', 'source', 'status']
    ordering_fields = ['value', 'reported_date']
    ordering = ['-reported_date']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff_member or user.role == 'admin':
            return Asset.objects.all()
        return Asset.objects.filter(
            django_models.Q(id_number=user.id_number) |
            django_models.Q(passport_no=user.passport_no)
        )
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search for assets by identifier"""
        serializer = AssetSearchSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['identifier']
            search_type = serializer.validated_data['search_type']
            
            if search_type == 'id':
                assets = Asset.objects.filter(id_number=identifier)
            elif search_type == 'passport':
                assets = Asset.objects.filter(passport_no=identifier)
            elif search_type == 'cds':
                assets = Asset.objects.filter(cds_account_no=identifier)
            elif search_type == 'bank':
                assets = Asset.objects.filter(account_no=identifier)
            elif search_type == 'asset_no':
                assets = Asset.objects.filter(asset_no=identifier)
            else:
                assets = Asset.objects.none()
            
            result_serializer = AssetSerializer(assets, many=True)
            return Response({
                'count': assets.count(),
                'results': result_serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def location(self, request, pk=None):
        """Get asset location"""
        asset = self.get_object()
        location = AssetLocation.objects.filter(asset=asset).first()
        if location:
            serializer = AssetLocationSerializer(location)
            return Response(serializer.data)
        return Response({'message': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get asset tracking history"""
        asset = self.get_object()
        history = AssetTrackingHistory.objects.filter(asset=asset)
        serializer = AssetTrackingHistorySerializer(history, many=True)
        return Response(serializer.data)


class ClaimViewSet(viewsets.ModelViewSet):
    """ViewSet for managing claims"""
    
    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['no', 'name', 'id_number', 'phone_no', 'e_mail']
    filterset_fields = ['status', 'category', 'claim_type', 'payment_category']
    ordering_fields = ['created_at', 'amount', 'no']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff_member or user.role == 'admin':
            return Claim.objects.all()
        return Claim.objects.filter(
            django_models.Q(id_number=user.id_number) |
            django_models.Q(phone_no=user.phone_no) |
            django_models.Q(e_mail=user.email) |
            django_models.Q(claimant=user)
        )
    
    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            created_by=user.get_full_name() or user.username,
            id_number=user.id_number,
            phone_no=user.phone_no,
            name=user.get_full_name() or user.name
        )
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search claims by various criteria"""
        serializer = ClaimSearchSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['identifier']
            search_type = serializer.validated_data['search_type']
            
            if search_type == 'claim_no':
                claims = Claim.objects.filter(no__icontains=identifier)
            elif search_type == 'id_number':
                claims = Claim.objects.filter(id_number=identifier)
            elif search_type == 'phone_no':
                claims = Claim.objects.filter(phone_no__icontains=identifier)
            elif search_type == 'name':
                claims = Claim.objects.filter(name__icontains=identifier)
            else:
                claims = Claim.objects.none()
            
            result_serializer = ClaimSerializer(claims, many=True)
            return Response({
                'count': claims.count(),
                'results': result_serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def create_claim(self, request):
        """Create a new claim with assets"""
        serializer = ClaimCreateSerializer(data=request.data)
        if serializer.is_valid():
            claim = serializer.save()
            return Response(
                ClaimSerializer(claim).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit claim for review"""
        claim = self.get_object()
        
        if claim.status != 'Draft':
            return Response(
                {'error': f'Cannot submit claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = claim.status
        claim.status = 'Pending'
        claim.submitted_at = timezone.now()
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Pending',
            changed_by=request.user,
            reason='Claim submitted for review'
        )
        
        return Response({
            'message': 'Claim submitted successfully',
            'claim_no': claim.no,
            'status': claim.status
        })
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a claim"""
        claim = self.get_object()
        
        if claim.status not in ['Pending', 'Under_Review']:
            return Response(
                {'error': f'Cannot approve claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = claim.status
        claim.status = 'Approved'
        claim.approved_at = timezone.now()
        claim.approved_by = request.user
        claim.approval_notes = request.data.get('notes', '')
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Approved',
            changed_by=request.user,
            reason=request.data.get('reason', 'Claim approved')
        )
        
        return Response({
            'message': 'Claim approved successfully',
            'claim_no': claim.no,
            'status': claim.status
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a claim"""
        claim = self.get_object()
        
        old_status = claim.status
        claim.status = 'Rejected'
        claim.rejected = True
        claim.rejection_reason = request.data.get('reason', '')
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Rejected',
            changed_by=request.user,
            reason=request.data.get('reason', 'Claim rejected')
        )
        
        return Response({
            'message': 'Claim rejected',
            'claim_no': claim.no,
            'reason': claim.rejection_reason
        })
    
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Move claim to under review"""
        claim = self.get_object()
        
        if claim.status != 'Pending':
            return Response(
                {'error': f'Cannot review claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = claim.status
        claim.status = 'Under_Review'
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Under_Review',
            changed_by=request.user,
            reason='Claim moved to under review'
        )
        
        return Response({
            'message': 'Claim is now under review',
            'claim_no': claim.no,
            'status': claim.status
        })
    
    @action(detail=True, methods=['post'])
    def process_payment(self, request, pk=None):
        """Mark claim payment as processed"""
        claim = self.get_object()
        
        if claim.status != 'Approved':
            return Response(
                {'error': f'Cannot process payment for claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = claim.status
        claim.status = 'Paid'
        claim.paid_at = timezone.now()
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Paid',
            changed_by=request.user,
            reason='Payment processed'
        )
        
        return Response({
            'message': 'Payment processed successfully',
            'claim_no': claim.no,
            'status': claim.status
        })
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete a claim"""
        claim = self.get_object()
        
        if claim.status != 'Paid':
            return Response(
                {'error': f'Cannot complete claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = claim.status
        claim.status = 'Completed'
        claim.save()
        
        ClaimStatusHistory.objects.create(
            claim=claim,
            previous_status=old_status,
            new_status='Completed',
            changed_by=request.user,
            reason='Claim completed'
        )
        
        return Response({
            'message': 'Claim marked as completed',
            'claim_no': claim.no,
            'status': claim.status
        })
    
    @action(detail=False, methods=['get'])
    def track(self, request):
        """Track claim status by claim number"""
        claim_number = request.query_params.get('claim_number')
        if not claim_number:
            return Response(
                {'error': 'claim_number parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            claim = Claim.objects.get(no=claim_number)
            serializer = ClaimStatusSerializer(claim)
            return Response(serializer.data)
        except Claim.DoesNotExist:
            return Response(
                {'error': 'Claim not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get detailed claim status"""
        claim = self.get_object()
        serializer = ClaimStatusSerializer(claim)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        """Get claim timeline"""
        claim = self.get_object()
        history = claim.status_history.all()
        serializer = ClaimStatusHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add a note to a claim"""
        claim = self.get_object()
        serializer = ClaimNoteSerializer(data={
            'claim': claim.id,
            'note_type': request.data.get('note_type', 'internal'),
            'content': request.data.get('content', ''),
            'is_public': request.data.get('is_public', False)
        })
        
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def notes(self, request, pk=None):
        """Get all notes for a claim"""
        claim = self.get_object()
        notes = claim.notes.all()
        serializer = ClaimNoteSerializer(notes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        """Upload a document for a claim"""
        claim = self.get_object()
        
        file = request.FILES.get('file')
        document_type = request.data.get('document_type')
        document_name = request.data.get('document_name', file.name if file else '')
        
        if not file or not document_type:
            return Response(
                {'error': 'file and document_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        document = ClaimDocument.objects.create(
            claim=claim,
            document_type=document_type,
            document_name=document_name,
            file_path=f"documents/{claim.no}/{file.name}",
            file_size=file.size,
            file_extension=file.name.split('.')[-1] if '.' in file.name else '',
            uploaded_by=request.user
        )
        
        serializer = ClaimDocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Get all documents for a claim"""
        claim = self.get_object()
        documents = claim.documents.all()
        serializer = ClaimDocumentSerializer(documents, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def verify_document(self, request, pk=None):
        """Verify a claim document"""
        claim = self.get_object()
        document_id = request.data.get('document_id')
        
        try:
            document = claim.documents.get(id=document_id)
            document.is_verified = True
            document.verified_by = request.user
            document.verified_at = timezone.now()
            document.verification_notes = request.data.get('notes', '')
            document.save()
            
            serializer = ClaimDocumentSerializer(document)
            return Response(serializer.data)
        except ClaimDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get claim summary statistics"""
        claim = self.get_object()
        
        summary = {
            'claim_no': claim.no,
            'status': claim.status,
            'total_assets': claim.claim_assets.count(),
            'total_value': float(claim.get_total_assets_value() or 0),
            'documents_uploaded': claim.get_uploaded_documents_count(),
            'documents_verified': claim.get_verified_documents_count(),
            'created_at': claim.created_at,
            'submitted_at': claim.submitted_at,
            'approved_at': claim.approved_at,
            'paid_at': claim.paid_at
        }
        
        return Response(summary)


class StaffClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for staff claim management"""
    
    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if not self.request.user.is_staff_member:
            return Claim.objects.none()
        return Claim.objects.filter(
            status__in=['Pending', 'Under_Review', 'Approved']
        ).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def assign_to_me(self, request, pk=None):
        """Assign claim to current staff member"""
        claim = self.get_object()
        claim.assigned_to = request.user
        claim.save()
        
        ClaimNote.objects.create(
            claim=claim,
            note_type='internal',
            content=f"Claim assigned to {request.user.get_full_name()}",
            created_by=request.user,
            is_public=False
        )
        
        return Response({'message': f'Claim {claim.no} assigned to you'})
    
    @action(detail=False, methods=['get'])
    def my_assigned(self, request):
        """Get claims assigned to current staff"""
        claims = Claim.objects.filter(assigned_to=request.user)
        serializer = ClaimSerializer(claims, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_review(self, request):
        """Get claims pending review"""
        claims = Claim.objects.filter(status='Pending')
        serializer = ClaimSerializer(claims, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get claim statistics for staff dashboard"""
        stats = {
            'total_claims': Claim.objects.count(),
            'pending_review': Claim.objects.filter(status='Pending').count(),
            'under_review': Claim.objects.filter(status='Under_Review').count(),
            'approved': Claim.objects.filter(status='Approved').count(),
            'rejected': Claim.objects.filter(status='Rejected').count(),
            'completed': Claim.objects.filter(status='Completed').count(),
            'total_value': Claim.objects.aggregate(total=django_models.Sum('amount'))['total'] or 0,
        }
        return Response(stats)


class StaffAssetTrackerViewSet(viewsets.GenericViewSet):
    """ViewSet for staff asset tracking"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()
    
    def get_queryset(self):
        if not self.request.user.is_staff_member:
            return Asset.objects.none()
        return Asset.objects.all()
    
    @action(detail=False, methods=['post'])
    def search_assets(self, request):
        """Search for assets by staff"""
        search_term = request.data.get('search_term', '')
        assets = Asset.objects.filter(
            django_models.Q(name__icontains=search_term) |
            django_models.Q(holder_name__icontains=search_term) |
            django_models.Q(asset_no__icontains=search_term) |
            django_models.Q(id_number__icontains=search_term)
        )
        serializer = AssetSerializer(assets, many=True)
        return Response({
            'count': assets.count(),
            'results': serializer.data
        })
    
    @action(detail=True, methods=['patch'])
    def update_location(self, request, pk=None):
        """Update asset location"""
        asset = self.get_object()
        serializer = AssetLocationUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            asset.location_source = request.data.get('location_source', asset.location_source)
            asset.physical_address = request.data.get('address', asset.physical_address)
            asset.latitude = request.data.get('latitude', asset.latitude)
            asset.longitude = request.data.get('longitude', asset.longitude)
            asset.status = request.data.get('status', asset.status)
            asset.save()
            
            # Update or create location record
            location, created = AssetLocation.objects.update_or_create(
                asset=asset,
                defaults={
                    'latitude': request.data.get('latitude'),
                    'longitude': request.data.get('longitude'),
                    'address': request.data.get('address', ''),
                    'building_name': request.data.get('building_name', ''),
                    'floor': request.data.get('floor', ''),
                    'room_number': request.data.get('room_number', ''),
                    'status': request.data.get('status', 'pending'),
                    'location_source': request.data.get('location_source', ''),
                    'notes': request.data.get('notes', ''),
                    'last_verified': timezone.now(),
                    'verified_by': request.user,
                }
            )
            
            # Create tracking history
            AssetTrackingHistory.objects.create(
                asset=asset,
                previous_status=asset.status,
                new_status=request.data.get('status', asset.status),
                notes=request.data.get('notes', ''),
                updated_by=request.user,
                location=request.data.get('address', ''),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude')
            )
            
            return Response({
                'message': 'Asset location updated successfully',
                'asset_no': asset.asset_no,
                'status': asset.status,
                'location': {
                    'latitude': str(asset.latitude) if asset.latitude else None,
                    'longitude': str(asset.longitude) if asset.longitude else None,
                    'address': asset.physical_address,
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending_assets(self, request):
        """Get assets pending location verification"""
        assets = Asset.objects.filter(status='pending')
        serializer = AssetSerializer(assets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get asset tracking statistics"""
        stats = {
            'total_assets': Asset.objects.count(),
            'pending_verification': Asset.objects.filter(status='pending').count(),
            'verified_found': Asset.objects.filter(status='found').count(),
            'verified_not_found': Asset.objects.filter(status='not_found').count(),
            'transferred': Asset.objects.filter(status='transferred').count(),
        }
        return Response(stats)