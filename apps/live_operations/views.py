# apps/live_operations/views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from .services import LiveDatabaseService
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_unclaimed_assets(request):
    """Search for unclaimed assets by ID, Passport, CDS, or Name"""
    
    identifier = request.data.get('identifier')
    search_type = request.data.get('search_type')  # id, passport, cds, name
    
    if not identifier or not search_type:
        return Response({
            'error': 'identifier and search_type are required',
            'valid_search_types': ['id', 'passport', 'cds', 'name']
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate search_type
    valid_types = ['id', 'passport', 'cds', 'name']
    if search_type not in valid_types:
        return Response({
            'error': f'Invalid search_type. Must be one of: {valid_types}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    print(f"🔍 Search request - Identifier: {identifier}, Type: {search_type}")
    
    try:
        assets = LiveDatabaseService.search_unclaimed_assets(identifier, search_type)
        
        return Response({
            'count': len(assets),
            'results': assets,
            'search_type': search_type,
            'identifier': identifier
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error searching assets: {str(e)}")
        print(f"❌ Error in search_unclaimed_assets: {str(e)}")
        return Response({
            'error': 'An error occurred while searching for assets',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_existing_claims(request):
    """Search for existing claims by ID, Passport, or CDS Account"""
    
    identifier = request.data.get('identifier')
    search_type = request.data.get('search_type')  # id, passport, cds
    
    if not identifier or not search_type:
        return Response({
            'error': 'identifier and search_type are required',
            'valid_search_types': ['id', 'passport', 'cds']
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate search_type
    valid_types = ['id', 'passport', 'cds']
    if search_type not in valid_types:
        return Response({
            'error': f'Invalid search_type. Must be one of: {valid_types}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        claims = LiveDatabaseService.search_existing_claims(identifier, search_type)
        
        return Response({
            'count': len(claims),
            'results': claims,
            'search_type': search_type,
            'identifier': identifier
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error searching claims: {str(e)}")
        return Response({
            'error': 'An error occurred while searching for claims',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_claim_delete(request):
    """Create a new claim in the live database"""
    
    # Extract and validate required fields
    claimant_name = request.data.get('claimant_name')
    claimant_id = request.data.get('claimant_id')
    
    if not claimant_name or not claimant_id:
        return Response({
            'error': 'claimant_name and claimant_id are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Prepare claim data with defaults
    claim_data = {
        'claim_no': request.data.get('claim_no'),
        'document_date': request.data.get('document_date'),
        'processing_date': request.data.get('processing_date'),
        'category': request.data.get('category', 'Original_Owner'),
        'sub_category': request.data.get('sub_category', ''),
        'agent_name': request.data.get('agent_name', ''),
        'claim_type': request.data.get('claim_type', 'Cash'),
        'claimant_name': claimant_name,
        'claimant_id': claimant_id,
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
    
    print(f"📝 Create claim request - Claimant: {claimant_name}, ID: {claimant_id}")
    print(f"📝 Number of claim lines: {len(claim_lines)}")
    
    try:
        result = LiveDatabaseService.create_new_claim(claim_data, claim_lines)
        
        if result['success']:
            print(f"✅ Claim created successfully: {result['claim_no']}")
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            print(f"❌ Claim creation failed: {result['message']}")
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Error creating claim: {str(e)}")
        print(f"❌ Exception in create_claim: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while creating the claim',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        'claimant_passport': request.data.get('claimant_passport', ''),
        # DO NOT include 'cds_account_no' here
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
            'error': 'status is required',
            'valid_statuses': ['Pending', 'Under_Review', 'Approved', 'Rejected', 'Paid', 'Completed']
        }, status=status.HTTP_400_BAD_REQUEST)
    
    print(f"📝 Update claim status - Claim No: {claim_no}, Status: {status_value}")
    
    try:
        result = LiveDatabaseService.update_claim_status(claim_no, status_value, remarks)
        
        if result['success']:
            print(f"✅ Claim status updated successfully: {claim_no}")
            return Response(result, status=status.HTTP_200_OK)
        else:
            print(f"❌ Claim status update failed: {result['message']}")
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Error updating claim status: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while updating claim status',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_details(request, claim_no):
    """Get claim details by claim number"""
    
    print(f"📝 Get claim details - Claim No: {claim_no}")
    
    try:
        claim = LiveDatabaseService.get_claim_by_no(claim_no)
        
        if claim:
            return Response({
                'success': True,
                'claim': claim
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Claim not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.error(f"Error getting claim details: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while fetching claim details',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_asset_details(request, asset_no):
    """Get asset details by asset number"""
    
    print(f"📝 Get asset details - Asset No: {asset_no}")
    
    try:
        asset = LiveDatabaseService.get_asset_by_no(asset_no)
        
        if asset:
            return Response({
                'success': True,
                'asset': asset
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Asset not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.error(f"Error getting asset details: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while fetching asset details',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_assets(request):
    """Get all unclaimed assets for the authenticated user"""
    
    user = request.user
    identifier = None
    
    # Try to get identifier from user profile
    if user.id_number:
        identifier = user.id_number
        search_type = 'id'
    elif user.passport_no:
        identifier = user.passport_no
        search_type = 'passport'
    else:
        return Response({
            'error': 'User has no ID number or passport number on file'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    print(f"📝 Get user assets - User: {user.username}, Identifier: {identifier}")
    
    try:
        assets = LiveDatabaseService.search_unclaimed_assets(identifier, search_type)
        
        return Response({
            'count': len(assets),
            'results': assets
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting user assets: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching user assets',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_summary(request, claim_no):
    """Get claim summary with statistics"""
    
    print(f"📝 Get claim summary - Claim No: {claim_no}")
    
    try:
        claim = LiveDatabaseService.get_claim_by_no(claim_no)
        
        if not claim:
            return Response({
                'success': False,
                'message': 'Claim not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate summary statistics
        total_amount = claim['amount']
        num_assets = len(claim.get('lines', []))
        
        # Determine current step
        status = claim['status']
        current_step = {
            'Pending': 'Document Verification',
            'Under_Review': 'Claim Review',
            'Approved': 'Approval Complete',
            'Paid': 'Payment Processing',
            'Completed': 'Claim Closed',
            'Rejected': 'Claim Rejected'
        }.get(status, 'Unknown')
        
        return Response({
            'success': True,
            'claim_no': claim['claim_no'],
            'status': status,
            'current_step': current_step,
            'total_amount': total_amount,
            'num_assets': num_assets,
            'created_at': claim['created_at'],
            'claimant_name': claim['claimant_name']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting claim summary: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while fetching claim summary',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_claim_for_review(request, claim_no):
    """Submit a claim for review (change status to Pending)"""
    
    print(f"📝 Submit claim for review - Claim No: {claim_no}")
    
    try:
        result = LiveDatabaseService.update_claim_status(claim_no, 'Pending', 'Claim submitted for review')
        
        if result['success']:
            return Response({
                'success': True,
                'message': 'Claim submitted for review successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Error submitting claim: {str(e)}")
        return Response({
            'success': False,
            'message': 'An error occurred while submitting the claim',
            'detail': str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
