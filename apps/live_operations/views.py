# apps/live_operations/views.py
import logging
import traceback
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q
from django.db import connections
from celery.result import AsyncResult

from .models import LiveOnlineClaim, LiveUnclaimedAsset
from .services import LiveDatabaseService
from .tasks import push_pending_claims_to_live, push_single_claim_to_live, push_claims_by_ids

logger = logging.getLogger(__name__)


# ==================== SEARCH ENDPOINTS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_existing_claims(request):
    """
    Search for existing claims by:
    - National ID Number
    - Passport Number
    - Claim Number
    """
    identifier = request.data.get('identifier', '').strip()
    search_type = request.data.get('search_type', '').strip()
    
    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)
    
    valid_types = ['id', 'claim_no', 'passport']
    if search_type not in valid_types:
        return Response({
            'error': f'Invalid search_type. Must be one of: {", ".join(valid_types)}',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)
    
    logger.info(f"Searching claims - Identifier: {identifier}, Type: {search_type}")
    
    try:
        if search_type == 'id':
            claims = LiveOnlineClaim.objects.filter(
                Q(id_number=identifier) |
                Q(id_number_alt=identifier)
            ).distinct()
            
            if claims.count() == 0:
                stripped_id = identifier.lstrip('0')
                if stripped_id != identifier:
                    claims = LiveOnlineClaim.objects.filter(
                        Q(id_number=stripped_id) |
                        Q(id_number_alt=stripped_id)
                    ).distinct()
            
            if claims.count() == 0:
                claims = LiveOnlineClaim.objects.filter(
                    Q(id_number__contains=identifier) |
                    Q(id_number_alt__contains=identifier)
                ).distinct()
            
        elif search_type == 'claim_no':
            claims = LiveOnlineClaim.objects.filter(
                Q(claim_no=identifier) |
                Q(claim_no__icontains=identifier)
            )
            
        elif search_type == 'passport':
            claims = LiveOnlineClaim.objects.filter(
                Q(passport_no=identifier) |
                Q(passport_no__icontains=identifier)
            )
        
        else:
            claims = LiveOnlineClaim.objects.none()
        
        logger.info(f"Found {claims.count()} claims for identifier: {identifier}")
        
        results = []
        for claim in claims:
            results.append({
                'claim_no': claim.claim_no,
                'claimant_name': claim.claimant_name,
                'id_number': claim.id_number,
                'id_number_alt': claim.id_number_alt,
                'passport_no': claim.passport_no,
                'claimant_phone': claim.claimant_phone,
                'claimant_email': claim.claimant_email,
                'amount': float(claim.amount) if claim.amount else None,
                'status': claim.status,
                'payment_category': claim.payment_category,
                'bank_name': claim.bank_name,
                'bank_account_no': claim.bank_account_no,
                'mpesa_mobile_no': claim.mpesa_mobile_no,
                'category': claim.category,
                'sub_category': claim.sub_category,
                'claim_type': claim.claim_type,
                'agent_name': claim.agent_name,
                'asset_no': claim.asset_no,
                'asset_type': claim.asset_type,
                'created_at': claim.created_at.isoformat() if claim.created_at else None,
                'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
            })
        
        return Response({
            'count': len(results),
            'results': results,
            'search_type': search_type,
            'identifier': identifier
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error searching claims: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'error': 'An error occurred while searching for claims',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_claims_universal(request):
    """
    Universal search for claims by:
    - National ID Number
    - Passport Number
    - Claim Number
    """
    identifier = request.data.get('identifier', '').strip()
    
    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)
    
    logger.info(f"Universal search for: {identifier}")
    
    try:
        claims = LiveOnlineClaim.objects.filter(
            Q(id_number=identifier) |
            Q(id_number_alt=identifier) |
            Q(id_number__contains=identifier) |
            Q(id_number_alt__contains=identifier) |
            Q(claim_no=identifier) |
            Q(claim_no__icontains=identifier) |
            Q(passport_no=identifier) |
            Q(passport_no__icontains=identifier)
        ).distinct()
        
        if claims.count() == 0:
            stripped_id = identifier.lstrip('0')
            if stripped_id != identifier:
                claims = LiveOnlineClaim.objects.filter(
                    Q(id_number=stripped_id) |
                    Q(id_number_alt=stripped_id)
                ).distinct()
        
        logger.info(f"Universal search found {claims.count()} claims for: {identifier}")
        
        results = []
        for claim in claims:
            results.append({
                'claim_no': claim.claim_no,
                'claimant_name': claim.claimant_name,
                'id_number': claim.id_number,
                'id_number_alt': claim.id_number_alt,
                'passport_no': claim.passport_no,
                'claimant_phone': claim.claimant_phone,
                'claimant_email': claim.claimant_email,
                'amount': float(claim.amount) if claim.amount else None,
                'status': claim.status,
                'payment_category': claim.payment_category,
                'bank_name': claim.bank_name,
                'bank_account_no': claim.bank_account_no,
                'mpesa_mobile_no': claim.mpesa_mobile_no,
                'category': claim.category,
                'sub_category': claim.sub_category,
                'claim_type': claim.claim_type,
                'agent_name': claim.agent_name,
                'asset_no': claim.asset_no,
                'asset_type': claim.asset_type,
                'description': claim.description,
                'created_at': claim.created_at.isoformat() if claim.created_at else None,
                'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
            })
        
        return Response({
            'count': len(results),
            'results': results,
            'identifier': identifier,
            'search_fields': [
                'National ID Number',
                'Passport Number',
                'Claim Number'
            ]
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error in universal search: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'error': 'An error occurred while searching',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_unclaimed_assets(request):
    """Search for unclaimed assets by ID, Passport, CDS, or Name"""
    identifier = request.data.get('identifier', '').strip()
    search_type = request.data.get('search_type', 'id').strip()
    
    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)
    
    logger.info(f"Searching assets - Identifier: {identifier}, Type: {search_type}")
    
    try:
        assets = LiveDatabaseService.search_unclaimed_assets(identifier, search_type)
        
        return Response({
            'count': len(assets),
            'results': assets,
            'search_type': search_type,
            'identifier': identifier
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error searching assets: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'error': 'An error occurred while searching for assets',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== CLAIM DETAILS ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_details(request, claim_no):
    """Get claim details by claim number"""
    
    logger.info(f"Getting claim details for: {claim_no}")
    
    try:
        claim = LiveOnlineClaim.objects.filter(claim_no=claim_no).first()
        
        if not claim:
            return Response({
                'success': False,
                'message': 'Claim not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': True,
            'claim': {
                'claim_no': claim.claim_no,
                'claimant_name': claim.claimant_name,
                'id_number': claim.id_number,
                'id_number_alt': claim.id_number_alt,
                'passport_no': claim.passport_no,
                'claimant_phone': claim.claimant_phone,
                'claimant_email': claim.claimant_email,
                'amount': float(claim.amount) if claim.amount else None,
                'status': claim.status,
                'payment_category': claim.payment_category,
                'bank_name': claim.bank_name,
                'bank_account_no': claim.bank_account_no,
                'mpesa_mobile_no': claim.mpesa_mobile_no,
                'category': claim.category,
                'sub_category': claim.sub_category,
                'claim_type': claim.claim_type,
                'agent_name': claim.agent_name,
                'asset_no': claim.asset_no,
                'asset_type': claim.asset_type,
                'description': claim.description,
                'created_at': claim.created_at.isoformat() if claim.created_at else None,
                'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error getting claim details: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'error': 'An error occurred while fetching claim details',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_summary(request, claim_no):
    """Get claim summary with statistics"""
    
    logger.info(f"Getting claim summary for: {claim_no}")
    
    try:
        claim = LiveOnlineClaim.objects.filter(claim_no=claim_no).first()
        
        if not claim:
            return Response({
                'success': False,
                'message': 'Claim not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': True,
            'claim_no': claim.claim_no,
            'status': claim.status,
            'amount': float(claim.amount) if claim.amount else None,
            'created_at': claim.created_at.isoformat() if claim.created_at else None,
            'claimant_name': claim.claimant_name,
            'claimant_id': claim.id_number,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error getting claim summary: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'error': 'An error occurred while fetching claim summary',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_claim_status(request, claim_no):
    """Update claim status"""
    
    status_value = request.data.get('status', '').strip()
    remarks = request.data.get('remarks', '')
    
    if not status_value:
        return Response({
            'error': 'status is required',
            'valid_statuses': ['Pending', 'Under_Review', 'Approved', 'Rejected', 'Paid', 'Completed']
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user has permission
    if status_value in ['Approved', 'Paid'] and not request.user.is_staff:
        return Response({
            'success': False,
            'message': 'Only staff members can approve or process payments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    logger.info(f"Updating claim status - Claim: {claim_no}, Status: {status_value}")
    
    try:
        result = LiveDatabaseService.update_claim_status(claim_no, status_value, remarks)
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error updating claim status: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': 'An error occurred while updating claim status',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_claim_for_review(request, claim_no):
    """Submit a claim for review (change status to Pending)"""
    
    logger.info(f"Submitting claim for review - Claim: {claim_no}")
    
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
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error submitting claim: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': 'An error occurred while submitting the claim',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== ASSET ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_asset_details(request, asset_no):
    """Get asset details by asset number"""
    
    logger.info(f"Getting asset details for: {asset_no}")
    
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
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error getting asset details: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': 'An error occurred while fetching asset details',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_assets(request):
    """Get all unclaimed assets for the authenticated user"""
    
    user = request.user
    identifier = None
    search_type = None
    
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
    
    logger.info(f"Getting user assets - User: {user.username}, Identifier: {identifier}")
    
    try:
        assets = LiveDatabaseService.search_unclaimed_assets(identifier, search_type)
        
        return Response({
            'count': len(assets),
            'results': assets
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error getting user assets: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'error': 'An error occurred while fetching user assets',
            'detail': error_msg if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== TEST ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_live_connection(request):
    """Simple test endpoint to check database connectivity"""
    try:
        with connections['ereunify'].cursor() as cursor:
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()
        
        count = LiveOnlineClaim.objects.count()
        
        first_record = LiveOnlineClaim.objects.first()
        sample = None
        if first_record:
            sample = {
                'claim_no': first_record.claim_no,
                'claimant_name': first_record.claimant_name,
                'id_number': first_record.id_number,
                'id_number_alt': first_record.id_number_alt,
                'passport_no': first_record.passport_no,
                'status': first_record.status,
            }
        
        return Response({
            'success': True,
            'database_version': version[0] if version else 'Unknown',
            'record_count': count,
            'sample_record': sample,
        })
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Connection test failed: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'error': error_msg,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_data_fields(request):
    """Check what data exists in the database"""
    try:
        total = LiveOnlineClaim.objects.count()
        logger.info(f"Total claims: {total}")
        
        with_id_number = LiveOnlineClaim.objects.filter(
            id_number__isnull=False
        ).exclude(id_number='').count()
        
        with_id_number_alt = LiveOnlineClaim.objects.filter(
            id_number_alt__isnull=False
        ).exclude(id_number_alt='').count()
        
        with_passport = LiveOnlineClaim.objects.filter(
            passport_no__isnull=False
        ).exclude(passport_no='').count()
        
        samples = LiveOnlineClaim.objects.all()[:5]
        sample_data = []
        for s in samples:
            sample_data.append({
                'claim_no': s.claim_no,
                'claimant_name': s.claimant_name,
                'id_number': s.id_number,
                'id_number_alt': s.id_number_alt,
                'passport_no': s.passport_no,
                'status': s.status,
            })
        
        return Response({
            'success': True,
            'total_claims': total,
            'claims_with_id_number': with_id_number,
            'claims_with_id_number_alt': with_id_number_alt,
            'claims_with_passport': with_passport,
            'sample_records': sample_data,
        })
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error checking data: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'error': error_msg,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PUSH TO LIVE ENDPOINTS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_claim_to_live(request, claim_id):
    """
    Push a specific claim to the live database
    
    Args:
        claim_id: The ID of the claim to push
    """
    try:
        # Check if user has staff permission
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Push the claim
        result = LiveDatabaseService.push_claim_to_live(claim_id)
        
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error pushing claim to live: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_pending_claims(request):
    """
    Push all pending claims to the live database
    """
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        result = LiveDatabaseService.push_pending_claims_to_live()
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error pushing pending claims: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_push_status(request, task_id):
    """
    Check the status of a Celery push task
    
    Args:
        task_id: The Celery task ID
    """
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        task = AsyncResult(task_id)
        
        return Response({
            'task_id': task_id,
            'status': task.status,
            'ready': task.ready(),
            'result': task.result if task.ready() else None,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error checking task status: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_push_to_live(request):
    """
    Manually trigger the Celery task to push claims to live database
    """
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Trigger the Celery task
        task = push_pending_claims_to_live.delay()
        
        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'message': 'Push task triggered successfully'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error triggering push task: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_push_claims_by_ids(request):
    """
    Manually trigger push for specific claims by IDs
    """
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        claim_ids = request.data.get('claim_ids', [])
        
        if not claim_ids:
            return Response({
                'success': False,
                'message': 'claim_ids list is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Trigger the Celery task
        task = push_claims_by_ids.delay(claim_ids)
        
        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'claim_ids': claim_ids,
            'message': f'Push task triggered for {len(claim_ids)} claims'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error triggering push by IDs: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_single_claim_async(request):
    """
    Asynchronously push a single claim to the live database via Celery
    """
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        claim_id = request.data.get('claim_id')
        
        if not claim_id:
            return Response({
                'success': False,
                'message': 'claim_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Trigger the Celery task
        task = push_single_claim_to_live.delay(claim_id)
        
        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'claim_id': claim_id,
            'message': f'Push task triggered for claim ID {claim_id}'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error triggering single push: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
