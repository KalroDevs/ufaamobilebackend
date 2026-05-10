from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from .services import LiveDatabaseService

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_unclaimed_assets(request):
    """Search for unclaimed assets by ID, Passport, or CDS Account"""
    
    identifier = request.data.get('identifier')
    search_type = request.data.get('search_type')  # id, passport, cds
    
    if not identifier or not search_type:
        return Response({
            'error': 'identifier and search_type are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    assets = LiveDatabaseService.search_unclaimed_assets(identifier, search_type)
    
    return Response({
        'count': len(assets),
        'results': assets
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_existing_claims(request):
    """Search for existing claims by ID, Passport, or CDS Account"""
    
    identifier = request.data.get('identifier')
    search_type = request.data.get('search_type')  # id, passport, cds
    
    if not identifier or not search_type:
        return Response({
            'error': 'identifier and search_type are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    claims = LiveDatabaseService.search_existing_claims(identifier, search_type)
    
    return Response({
        'count': len(claims),
        'results': claims
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_claim(request):
    """Create a new claim in the live database"""
    
    claim_data = {
        'claim_no': request.data.get('claim_no'),
        'document_date': request.data.get('document_date'),
        'processing_date': request.data.get('processing_date'),
        'category': request.data.get('category', 'Original_Owner'),
        'sub_category': request.data.get('sub_category', ''),
        'agent_name': request.data.get('agent_name', ''),
        'claim_type': request.data.get('claim_type', 'Cash'),
        'claimant_name': request.data.get('claimant_name'),
        'claimant_id': request.data.get('claimant_id'),
        'claimant_phone': request.data.get('claimant_phone', ''),
        'claimant_email': request.data.get('claimant_email', ''),
        'amount': request.data.get('amount', 0),
        'payment_category': request.data.get('payment_category', ''),
        'bank_name': request.data.get('bank_name', ''),
        'bank_account_no': request.data.get('bank_account_no', ''),
        'mpesa_mobile_no': request.data.get('mpesa_mobile_no', ''),
        'cds_account_no': request.data.get('cds_account_no', ''),
        'claimant_passport': request.data.get('claimant_passport', ''),
    }
    
    claim_lines = request.data.get('claim_lines', [])
    
    if not claim_data.get('claimant_name') or not claim_data.get('claimant_id'):
        return Response({
            'error': 'claimant_name and claimant_id are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    result = LiveDatabaseService.create_new_claim(claim_data, claim_lines)
    
    if result['success']:
        return Response(result, status=status.HTTP_201_CREATED)
    else:
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_claim_status(request, claim_no):
    """Update claim status"""
    
    status_value = request.data.get('status')
    remarks = request.data.get('remarks', '')
    
    if not status_value:
        return Response({
            'error': 'status is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    result = LiveDatabaseService.update_claim_status(claim_no, status_value, remarks)
    
    if result['success']:
        return Response(result)
    else:
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)