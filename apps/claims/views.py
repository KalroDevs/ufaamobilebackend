from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models as django_models
from django.utils import timezone
from django.shortcuts import get_object_or_404
import logging

from .models import Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
from .serializers import (
    ClaimSerializer, ClaimCreateSerializer, ClaimStatusSerializer,
    ClaimActionSerializer, ClaimSearchSerializer, ClaimDocumentSerializer,
    ClaimNoteSerializer, ClaimStatusHistorySerializer
)
from apps.accounts.models import User

logger = logging.getLogger(__name__)

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
        """Filter claims to only show those belonging to the logged-in user"""
        user = self.request.user
        
        # Staff users can see all claims
        if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
            return Claim.objects.all()
        
        # Regular citizens: only show their own claims using 'claimant' field
        # Also match by id_number, phone_no, email for backward compatibility
        return Claim.objects.filter(
            django_models.Q(claimant=user) |
            django_models.Q(id_number=user.id_number) |
            django_models.Q(phone_no=user.phone_no) |
            django_models.Q(e_mail=user.email)
        )
    
    def perform_create(self, serializer):
        """Automatically set the claimant when creating a claim"""
        user = self.request.user
        serializer.save(
            claimant=user,
            created_by=user.get_full_name() or user.username,
            id_number=user.id_number,
            phone_no=user.phone_no,
            name=user.get_full_name() or user.name
        )
    
    @action(detail=False, methods=['get'], url_path='my-claims')
    def my_claims(self, request):
        """Endpoint to get only current user's claims"""
        claims = self.get_queryset()
        page = self.paginate_queryset(claims)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(claims, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='statistics')
    def claim_statistics(self, request):
        """Get claim statistics for the logged-in user"""
        claims = self.get_queryset()
        stats = {
            'total': claims.count(),
            'draft': claims.filter(status='Draft').count(),
            'pending': claims.filter(status='Pending').count(),
            'under_review': claims.filter(status='Under_Review').count(),
            'approved': claims.filter(status='Approved').count(),
            'rejected': claims.filter(status='Rejected').count(),
            'paid': claims.filter(status='Paid').count(),
            'completed': claims.filter(status='Completed').count(),
            'archived': claims.filter(status='Archived').count(),
        }
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search claims by various criteria (limited to user's claims)"""
        serializer = ClaimSearchSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['identifier']
            search_type = serializer.validated_data['search_type']
            
            # Base queryset (user's claims only)
            claims = self.get_queryset()
            
            if search_type == 'claim_no':
                claims = claims.filter(no__icontains=identifier)
            elif search_type == 'id_number':
                claims = claims.filter(id_number=identifier)
            elif search_type == 'phone_no':
                claims = claims.filter(phone_no__icontains=identifier)
            elif search_type == 'name':
                claims = claims.filter(name__icontains=identifier)
            else:
                claims = claims.none()
            
            result_serializer = ClaimSerializer(claims, many=True)
            return Response({
                'count': claims.count(),
                'results': result_serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def create_claim(self, request):
        """Create a new claim with assets"""
        serializer = ClaimCreateSerializer(data=request.data, context={'request': request})
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
        claim.completed_at = timezone.now()
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
        """Track claim status by claim number (limited to user's claims)"""
        claim_number = request.query_params.get('claim_number')
        if not claim_number:
            return Response(
                {'error': 'claim_number parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Only allow tracking of claims belonging to the user
            claim = self.get_queryset().get(no=claim_number)
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
            'paid_at': claim.paid_at,
            'completed_at': getattr(claim, 'completed_at', None),
        }
        
        return Response(summary)



class ClaimViewSetDeleteView(viewsets.ModelViewSet):
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
        logger.info(f"Creating claim for user: {user.username}")
        serializer.save(
            created_by=user.get_full_name() or user.username,
            id_number=user.id_number,
            phone_no=user.phone_no,
            name=user.get_full_name() or user.name,
            claimant=user
        )
    
    def update(self, request, *args, **kwargs):
        """Update a claim - partial updates allowed"""
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        
        logger.info(f"Updating claim {instance.id} with data: {request.data}")
        
        # Check if user has permission to update this claim
        user = request.user
        if not (user.is_staff_member or user.role == 'admin' or instance.claimant == user):
            return Response(
                {'error': 'You do not have permission to update this claim'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(serializer.data)
    
    def perform_update(self, serializer):
        serializer.save()
    
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
        logger.info(f"Create claim request data: {request.data}")
        
        # Add default values for required fields
        data = request.data.copy()
        user = request.user
        
        # Set default values if not provided
        if 'id_number' not in data or not data['id_number']:
            data['id_number'] = user.id_number
        if 'phone_no' not in data or not data['phone_no']:
            data['phone_no'] = user.phone_no
        if 'name' not in data or not data['name']:
            data['name'] = user.get_full_name() or user.username
        
        serializer = ClaimCreateSerializer(data=data)
        if serializer.is_valid():
            claim = serializer.save()
            logger.info(f"Claim created successfully with ID: {claim.id}, Number: {claim.no}")
            
            # Return the full claim data with ID
            return Response(
                ClaimSerializer(claim).data,
                status=status.HTTP_201_CREATED
            )
        logger.error(f"Claim creation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit claim for review"""
        claim = self.get_object()
        
        logger.info(f"Submitting claim {claim.id} - Current status: {claim.status}")
        
        # Check if user has permission to submit this claim
        user = request.user
        if not (user.is_staff_member or user.role == 'admin' or claim.claimant == user):
            return Response(
                {'error': 'You do not have permission to submit this claim'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if claim.status != 'Draft':
            return Response(
                {'error': f'Cannot submit claim with status: {claim.status}. Only Draft claims can be submitted.'},
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
        
        logger.info(f"Claim {claim.id} submitted successfully. New status: {claim.status}")
        
        return Response({
            'message': 'Claim submitted successfully',
            'claim_no': claim.no,
            'status': claim.status,
            'claim': ClaimSerializer(claim).data
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
