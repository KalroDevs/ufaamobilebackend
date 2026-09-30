# apps/claims/views.py
import os
import mimetypes
import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models as django_models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404, FileResponse, HttpResponseRedirect
from django.conf import settings
from django.utils.encoding import escape_uri_path

from .models import Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
from .serializers import (
    ClaimSerializer, ClaimCreateSerializer, ClaimStatusSerializer,
    ClaimActionSerializer, ClaimSearchSerializer, ClaimDocumentSerializer,
    ClaimNoteSerializer, ClaimStatusHistorySerializer, ClaimDocumentUploadSerializer
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
        user = self.request.user
        if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
            return Claim.objects.all()
        return Claim.objects.filter(
            django_models.Q(claimant=user) |
            django_models.Q(id_number=user.id_number) |
            django_models.Q(phone_no=user.phone_no) |
            django_models.Q(e_mail=user.email)
        )

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            claimant=user,
            created_by=user.get_full_name() or user.username,
            id_number=user.id_number,
            phone_no=user.phone_no,
            name=user.get_full_name() or user.name,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _check_document_permission(self, document, user):
        """Return True if user can access the document."""
        if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
            return True
        return document.claim.claimant == user

    def _resolve_file_url(self, document):
        """
        Resolve a downloadable URL for a stored document.

        Delegates to FileField.url → storage.url(). For SharePoint this
        returns a short-lived Graph download link. Never touches .path.
        """
        if not document.file:
            return None
        try:
            return document.file.url
        except NotImplementedError:
            logger.warning(
                "Storage backend cannot produce a URL for document %s",
                document.pk,
            )
            return None
        except Exception as exc:
            logger.exception(
                "Error resolving URL for document %s: %s", document.pk, exc
            )
            return None

    # ------------------------------------------------------------------ #
    # Listing / status / stats
    # ------------------------------------------------------------------ #

    @action(detail=False, methods=['get'], url_path='my-claims')
    def my_claims(self, request):
        claims = self.get_queryset()
        page = self.paginate_queryset(claims)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(self.get_serializer(claims, many=True).data)

    @action(detail=False, methods=['get'], url_path='statistics')
    def claim_statistics(self, request):
        claims = self.get_queryset()
        return Response({
            'total': claims.count(),
            'draft': claims.filter(status='Draft').count(),
            'pending': claims.filter(status='Pending').count(),
            'under_review': claims.filter(status='Under_Review').count(),
            'approved': claims.filter(status='Approved').count(),
            'rejected': claims.filter(status='Rejected').count(),
            'paid': claims.filter(status='Paid').count(),
            'completed': claims.filter(status='Completed').count(),
            'archived': claims.filter(status='Archived').count(),
        })

    @action(detail=False, methods=['post'])
    def search(self, request):
        serializer = ClaimSearchSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['identifier']
            search_type = serializer.validated_data['search_type']
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
            return Response({
                'count': claims.count(),
                'results': ClaimSerializer(claims, many=True).data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def create_claim(self, request):
        serializer = ClaimCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            claim = serializer.save()
            return Response(
                ClaimSerializer(claim).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------ #
    # Status transitions
    # ------------------------------------------------------------------ #

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        claim = self.get_object()
        if claim.status != 'Draft':
            return Response(
                {'error': f'Cannot submit claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = claim.status
        claim.status = 'Pending'
        claim.submitted_at = timezone.now()
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Pending',
            changed_by=request.user, reason='Claim submitted for review',
        )
        return Response({
            'message': 'Claim submitted successfully',
            'claim_no': claim.no, 'status': claim.status,
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        claim = self.get_object()
        if claim.status not in ['Pending', 'Under_Review']:
            return Response(
                {'error': f'Cannot approve claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = claim.status
        claim.status = 'Approved'
        claim.approved_at = timezone.now()
        claim.approved_by = request.user
        claim.approval_notes = request.data.get('notes', '')
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Approved',
            changed_by=request.user,
            reason=request.data.get('reason', 'Claim approved'),
        )
        return Response({
            'message': 'Claim approved successfully',
            'claim_no': claim.no, 'status': claim.status,
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        claim = self.get_object()
        old_status = claim.status
        claim.status = 'Rejected'
        claim.rejected = True
        claim.rejection_reason = request.data.get('reason', '')
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Rejected',
            changed_by=request.user,
            reason=request.data.get('reason', 'Claim rejected'),
        )
        return Response({
            'message': 'Claim rejected',
            'claim_no': claim.no, 'reason': claim.rejection_reason,
        })

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        claim = self.get_object()
        if claim.status != 'Pending':
            return Response(
                {'error': f'Cannot review claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = claim.status
        claim.status = 'Under_Review'
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Under_Review',
            changed_by=request.user, reason='Claim moved to under review',
        )
        return Response({
            'message': 'Claim is now under review',
            'claim_no': claim.no, 'status': claim.status,
        })

    @action(detail=True, methods=['post'])
    def process_payment(self, request, pk=None):
        claim = self.get_object()
        if claim.status != 'Approved':
            return Response(
                {'error': f'Cannot process payment for status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = claim.status
        claim.status = 'Paid'
        claim.paid_at = timezone.now()
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Paid',
            changed_by=request.user, reason='Payment processed',
        )
        return Response({
            'message': 'Payment processed successfully',
            'claim_no': claim.no, 'status': claim.status,
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        claim = self.get_object()
        if claim.status != 'Paid':
            return Response(
                {'error': f'Cannot complete claim with status: {claim.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = claim.status
        claim.status = 'Completed'
        claim.completed_at = timezone.now()
        claim.save()
        ClaimStatusHistory.objects.create(
            claim=claim, previous_status=old_status, new_status='Completed',
            changed_by=request.user, reason='Claim completed',
        )
        return Response({
            'message': 'Claim marked as completed',
            'claim_no': claim.no, 'status': claim.status,
        })

    # ------------------------------------------------------------------ #
    # Read-only info
    # ------------------------------------------------------------------ #

    @action(detail=False, methods=['get'])
    def track(self, request):
        claim_number = request.query_params.get('claim_number')
        if not claim_number:
            return Response(
                {'error': 'claim_number parameter is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            claim = self.get_queryset().get(no=claim_number)
            return Response(ClaimStatusSerializer(claim).data)
        except Claim.DoesNotExist:
            return Response(
                {'error': 'Claim not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        return Response(ClaimStatusSerializer(self.get_object()).data)

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        claim = self.get_object()
        return Response(
            ClaimStatusHistorySerializer(claim.status_history.all(), many=True).data
        )

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        claim = self.get_object()
        return Response({
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
        })

    # ------------------------------------------------------------------ #
    # Notes
    # ------------------------------------------------------------------ #

    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        claim = self.get_object()
        serializer = ClaimNoteSerializer(data={
            'claim': claim.id,
            'note_type': request.data.get('note_type', 'internal'),
            'content': request.data.get('content', ''),
            'is_public': request.data.get('is_public', False),
        })
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def notes(self, request, pk=None):
        claim = self.get_object()
        return Response(ClaimNoteSerializer(claim.notes.all(), many=True).data)

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        """
        Upload a document for a claim.

        Bytes go straight to SharePoint via ClaimDocument.file.
        Only metadata is stored in Postgres. This view never touches .path.
        """
        claim = self.get_object()

        upload_serializer = ClaimDocumentUploadSerializer(
            data=request.data,
            context={'request': request, 'claim_id': claim.id},
        )
        if not upload_serializer.is_valid():
            return Response(
                upload_serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        file = upload_serializer.validated_data['file']
        document_type = upload_serializer.validated_data['document_type']
        document_name = upload_serializer.validated_data.get(
            'document_name', file.name
        )

        try:
            document = ClaimDocument.objects.create(
                claim=claim,
                document_type=document_type,
                document_name=document_name,
                file=file,   # ← storage backend handles SharePoint PUT
                uploaded_by=request.user,
            )
            document.file_size = file.size
            document.file_extension = (
                file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
            )
            document.save(update_fields=['file_size', 'file_extension'])

            return Response(
                ClaimDocumentSerializer(document).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            logger.exception("Error uploading document for claim %s", claim.id)
            return Response(
                {'error': f'Failed to upload document: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        claim = self.get_object()
        return Response(
            ClaimDocumentSerializer(claim.documents.all(), many=True).data
        )

    @action(
        detail=True, methods=['get'],
        url_path='documents/(?P<document_id>[0-9]+)/download',
    )
    def download_claim_document(self, request, pk=None, document_id=None):
        """
        Redirect the client to the SharePoint download link.

        Never calls .path — SharePointStorage raises NotImplementedError
        for cloud files. .url resolves through the storage backend and
        returns a short-lived, pre-authenticated Graph download link.
        """
        claim = self.get_object()
        try:
            document = claim.documents.get(id=document_id)

            if not self._check_document_permission(document, request.user):
                return Response(
                    {'error': 'You do not have permission to download this document.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            file_url = self._resolve_file_url(document)
            if not file_url:
                return Response(
                    {'error': 'File not found on storage backend.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # 302 sends the browser straight to SharePoint.
            return HttpResponseRedirect(file_url)

        except ClaimDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception(
                "Error downloading document %s", document_id,
            )
            return Response(
                {'error': f'Error downloading file: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=True, methods=['get'],
        url_path='documents/(?P<document_id>[0-9]+)/view',
    )
    def view_claim_document(self, request, pk=None, document_id=None):
        """
        Same as download — redirects to SharePoint. SharePoint already
        serves PDFs/images inline, so the browser behaves correctly.
        """
        return self.download_claim_document(
            request, pk=pk, document_id=document_id
        )

    @action(
        detail=True, methods=['delete'],
        url_path='documents/(?P<document_id>[0-9]+)/delete',
    )
    def delete_document(self, request, pk=None, document_id=None):
        claim = self.get_object()
        try:
            document = claim.documents.get(id=document_id)

            if not self._check_document_permission(document, request.user):
                return Response(
                    {'error': 'You do not have permission to delete this document.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            document.delete()   # model.delete() also removes the SharePoint file
            return Response(
                {'message': 'Document deleted successfully'},
                status=status.HTTP_200_OK,
            )
        except ClaimDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=['post'])
    def verify_document(self, request, pk=None):
        claim = self.get_object()
        document_id = request.data.get('document_id')
        try:
            document = claim.documents.get(id=document_id)
            document.is_verified = True
            document.verified_by = request.user
            document.verified_at = timezone.now()
            document.verification_notes = request.data.get('notes', '')
            document.save()
            return Response(ClaimDocumentSerializer(document).data)
        except ClaimDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )


class ClaimViewSetDeleteView(ClaimViewSet):
    """
    Same behaviour as ClaimViewSet (kept as a separate registration for
    the ``/claims-delete/`` route). Reuses every action above.
    """
    pass


class StaffClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for staff claim management"""

    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_staff:
            return Claim.objects.none()
        return Claim.objects.filter(
            status__in=['Pending', 'Under_Review', 'Approved']
        ).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def assign_to_me(self, request, pk=None):
        claim = self.get_object()
        claim.assigned_to = request.user
        claim.save()
        ClaimNote.objects.create(
            claim=claim, note_type='internal',
            content=f"Claim assigned to {request.user.get_full_name()}",
            created_by=request.user, is_public=False,
        )
        return Response({'message': f'Claim {claim.no} assigned to you'})

    @action(detail=False, methods=['get'])
    def my_assigned(self, request):
        claims = Claim.objects.filter(assigned_to=request.user)
        return Response(ClaimSerializer(claims, many=True).data)

    @action(detail=False, methods=['get'])
    def pending_review(self, request):
        claims = Claim.objects.filter(status='Pending')
        return Response(ClaimSerializer(claims, many=True).data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        return Response({
            'total_claims': Claim.objects.count(),
            'pending_review': Claim.objects.filter(status='Pending').count(),
            'under_review': Claim.objects.filter(status='Under_Review').count(),
            'approved': Claim.objects.filter(status='Approved').count(),
            'rejected': Claim.objects.filter(status='Rejected').count(),
            'completed': Claim.objects.filter(status='Completed').count(),
            'total_value': Claim.objects.aggregate(
                total=django_models.Sum('amount')
            )['total'] or 0,
        })


# ==================================================================== #
# STANDALONE DOCUMENT VIEWS
# ==================================================================== #

def _resolve_claim_document_url(document):
    """Shared helper — returns the storage URL or None."""
    if not document.file:
        return None
    try:
        return document.file.url
    except NotImplementedError:
        logger.warning(
            "Storage backend cannot produce a URL for document %s",
            document.pk,
        )
        return None
    except Exception as exc:
        logger.exception(
            "Error resolving URL for document %s: %s", document.pk, exc
        )
        return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_document_by_id(request, document_id):
    """
    Redirect to SharePoint download link.
    URL: /api/documents/<int:document_id>/download/
    """
    try:
        document = get_object_or_404(ClaimDocument, id=document_id)

        user = request.user
        if not (user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']):
            if document.claim.claimant != user:
                return Response(
                    {'error': 'You do not have permission to download this document.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        file_url = _resolve_claim_document_url(document)
        if not file_url:
            return Response(
                {'error': 'File not found on storage backend.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return HttpResponseRedirect(file_url)

    except ClaimDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as exc:
        logger.exception("Error downloading document %s", document_id)
        return Response(
            {'error': f'Error downloading file: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_document_by_id(request, document_id):
    """
    Redirect to SharePoint view link (same as download; SharePoint
    serves PDFs/images inline in the browser).
    URL: /api/documents/<int:document_id>/view/
    """
    return download_document_by_id(request, document_id)
