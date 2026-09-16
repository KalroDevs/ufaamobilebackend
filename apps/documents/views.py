from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from apps.claims.models import Claim
from .upload_service import DocumentUploadService

upload_service = DocumentUploadService()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_claim_document(request, claim_id):
    """Upload a document for a claim"""
    
    # Get claim from PostgreSQL
    claim = get_object_or_404(Claim, id=claim_id)
    
    # Get file from request
    file = request.FILES.get('file')
    document_type = request.data.get('document_type')
    
    if not file or not document_type:
        return Response({
            'error': 'file and document_type are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get claim number for MSSQL reference
    claim_number = request.data.get('claim_number')
    
    # Upload document
    result = upload_service.upload_claim_document(
        file=file,
        document_type=document_type,
        claim=claim,
        user=request.user,
        claim_number=claim_number
    )
    
    if result['success']:
        return Response(result, status=status.HTTP_201_CREATED)
    else:
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_documents(request, claim_id):
    """Get all documents for a claim"""
    
    claim = get_object_or_404(Claim, id=claim_id)
    claim_number = request.query_params.get('claim_number')
    
    documents = upload_service.get_claim_documents(claim_id, claim_number)
    
    return Response(documents)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_document(request, document_id):
    """Verify a document (staff only)"""
    
    if not request.user.is_staff_member:
        return Response({
            'error': 'Only staff can verify documents'
        }, status=status.HTTP_403_FORBIDDEN)
    
    doc = upload_service.verify_document(document_id, request.user)
    
    return Response({
        'message': 'Document verified successfully',
        'document_id': doc.id,
        'verified_at': doc.verified_at
    })