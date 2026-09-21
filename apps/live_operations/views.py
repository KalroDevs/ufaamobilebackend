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
from .tasks import (
    push_pending_claims_to_live,
    push_single_claim_to_live,
    push_claims_by_ids,
)

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

    Response now includes `rejected` and `rejection_reason`
    (from `[Send Remarks]`).
    """
    identifier = request.data.get('identifier', '').strip()
    search_type = request.data.get('search_type', '').strip().lower()

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

    logger.info(
        "Searching claims - Identifier: %s, Type: %s", identifier, search_type,
    )

    try:
        results = LiveDatabaseService.search_live_claims(
            identifier, search_type,
        )

        logger.info(
            "Found %s claims for identifier: %s", len(results), identifier,
        )

        return Response({
            'count': len(results),
            'results': results,
            'search_type': search_type,
            'identifier': identifier,
        }, status=status.HTTP_200_OK)

    except ValueError as e:
        return Response({
            'error': str(e),
            'count': 0,
            'results': [],
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error searching claims: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

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

    Tries ID match first, then passport, then exact claim number.
    Response includes `rejected` and `rejection_reason`.
    """
    identifier = request.data.get('identifier', '').strip()

    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)

    logger.info("Universal search for: %s", identifier)

    try:
        merged = []
        seen = set()

        for search_type in ('id', 'passport', 'claim_no'):
            try:
                partial = LiveDatabaseService.search_live_claims(
                    identifier, search_type,
                )
            except Exception:
                logger.exception(
                    "Universal search: %s search failed for %s",
                    search_type, identifier,
                )
                continue

            for item in partial:
                key = item.get('claim_no')
                if key and key not in seen:
                    seen.add(key)
                    merged.append(item)

        logger.info(
            "Universal search found %s claims for: %s",
            len(merged), identifier,
        )

        return Response({
            'count': len(merged),
            'results': merged,
            'identifier': identifier,
            'search_fields': [
                'National ID Number',
                'Passport Number',
                'Claim Number',
            ],
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error in universal search: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'error': 'An error occurred while searching',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_unclaimed_assets(request):
    """
    Search for unclaimed assets using direct database access.

    Search types:
    - id: Search by National ID Number
    - passport: Search by Passport Number
    - cds: Search by CDS Account Number
    - name: Search by Owner/Holder Name
    """
    identifier = request.data.get('identifier', '').strip()
    search_type = request.data.get('search_type', 'id').strip()

    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)

    valid_types = ['id', 'passport', 'cds', 'name', 'owner', 'holder']
    if search_type not in valid_types:
        return Response({
            'error': f'Invalid search_type. Must be one of: {", ".join(valid_types)}',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)

    logger.info(
        "🔍 Searching assets via direct database access - Identifier: %s, Type: %s",
        identifier, search_type,
    )

    try:
        assets = LiveDatabaseService.search_unclaimed_assets(
            identifier, search_type,
        )

        logger.info(
            "✅ Found %s assets for identifier: %s", len(assets), identifier,
        )

        return Response({
            'count': len(assets),
            'results': assets,
            'search_type': search_type,
            'identifier': identifier,
            'source': 'direct_database',
        }, status=status.HTTP_200_OK)

    except ValueError as e:
        logger.error("❌ Validation error in asset search: %s", str(e))
        return Response({
            'error': str(e),
            'count': 0,
            'results': [],
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error(
            "❌ Error searching assets via direct database: %s", error_msg,
        )
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'error': 'An error occurred while searching for assets',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_unclaimed_assets_fallback(request):
    """
    Search for unclaimed assets with automatic fallback handling.
    """
    identifier = request.data.get('identifier', '').strip()
    search_type = request.data.get('search_type', 'id').strip()

    if not identifier:
        return Response({
            'error': 'identifier is required',
            'count': 0,
            'results': []
        }, status=status.HTTP_400_BAD_REQUEST)

    logger.info(
        "🔍 Searching assets with fallback - Identifier: %s, Type: %s",
        identifier, search_type,
    )

    try:
        assets = LiveDatabaseService.search_unclaimed_assets(
            identifier, search_type,
        )

        return Response({
            'count': len(assets),
            'results': assets,
            'search_type': search_type,
            'identifier': identifier,
            'method': 'direct_database',
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)

        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            logger.error("⚠️ Database connection issue: %s", error_msg)
            return Response({
                'error': 'Unable to connect to the asset database. Please try again later.',
                'count': 0,
                'results': [],
                'method': 'failed',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if "column" in error_msg.lower() or "table" in error_msg.lower():
            logger.error("⚠️ Database schema issue: %s", error_msg)
            return Response({
                'error': 'Database schema issue. Please contact support.',
                'count': 0,
                'results': [],
                'method': 'failed',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.error("❌ Error in fallback search: %s", error_msg)
        return Response({
            'error': 'An error occurred while searching for assets',
            'detail': error_msg if request.user.is_staff else None,
            'count': 0,
            'results': [],
            'method': 'failed',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== ASSET ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_asset_details(request, asset_no):
    """Get asset details by asset number using direct database access"""

    logger.info("Getting asset details for: %s", asset_no)

    try:
        asset = LiveDatabaseService.get_asset_by_no(asset_no)

        if asset:
            return Response({
                'success': True,
                'asset': asset,
                'source': 'direct_database',
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Asset not found',
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error getting asset details: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': 'An error occurred while fetching asset details',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_assets(request):
    """
    Get all unclaimed assets for the authenticated user using direct database access.
    """
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

    logger.info(
        "Getting user assets via direct database - User: %s, Identifier: %s",
        user.username, identifier,
    )

    try:
        assets = LiveDatabaseService.search_unclaimed_assets(
            identifier, search_type,
        )

        return Response({
            'count': len(assets),
            'results': assets,
            'source': 'direct_database',
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error getting user assets: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'error': 'An error occurred while fetching user assets',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== CLAIM DETAILS ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_details(request, claim_no):
    """Get claim details by claim number (includes rejection info)"""

    logger.info("Getting claim details for: %s", claim_no)

    try:
        claim = LiveDatabaseService.get_live_claim(claim_no)

        if not claim:
            return Response({
                'success': False,
                'message': 'Claim not found',
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'success': True,
            'claim': claim,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error getting claim details: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'error': 'An error occurred while fetching claim details',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_summary(request, claim_no):
    """Get claim summary with statistics (includes rejection info)"""

    logger.info("Getting claim summary for: %s", claim_no)

    try:
        claim = LiveDatabaseService.get_live_claim(claim_no)

        if not claim:
            return Response({
                'success': False,
                'message': 'Claim not found',
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'success': True,
            'claim_no': claim.get('claim_no'),
            'status': claim.get('status'),
            'amount': claim.get('amount'),
            'created_at': claim.get('created_at'),
            'claimant_name': claim.get('claimant_name'),
            'claimant_id': claim.get('id_number'),
            'rejected': claim.get('rejected', False),
            'rejection_reason': claim.get('rejection_reason', ''),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error getting claim summary: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'error': 'An error occurred while fetching claim summary',
            'detail': error_msg if request.user.is_staff else None,
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
            'valid_statuses': [
                'Pending', 'Under_Review', 'Approved',
                'Rejected', 'Paid', 'Completed',
            ],
        }, status=status.HTTP_400_BAD_REQUEST)

    if status_value in ['Approved', 'Paid'] and not request.user.is_staff:
        return Response({
            'success': False,
            'message': 'Only staff members can approve or process payments',
        }, status=status.HTTP_403_FORBIDDEN)

    logger.info(
        "Updating claim status - Claim: %s, Status: %s",
        claim_no, status_value,
    )

    try:
        result = LiveDatabaseService.update_claim_status(
            claim_no, status_value, remarks,
        )

        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                result, status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error updating claim status: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': 'An error occurred while updating claim status',
            'detail': error_msg if request.user.is_staff else None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_claim_for_review(request, claim_no):
    """Submit a claim for review (change status to Pending)"""

    logger.info("Submitting claim for review - Claim: %s", claim_no)

    try:
        result = LiveDatabaseService.update_claim_status(
            claim_no, 'Pending', 'Claim submitted for review',
        )

        if result['success']:
            return Response({
                'success': True,
                'message': 'Claim submitted for review successfully',
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                result, status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error submitting claim: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': 'An error occurred while submitting the claim',
            'detail': error_msg if request.user.is_staff else None,
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
                'rejected': bool(first_record.rejected),
                'rejection_reason': first_record.rejection_reason,
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

        logger.error("Connection test failed: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

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
        logger.info("Total claims: %s", total)

        with_id_number = LiveOnlineClaim.objects.filter(
            id_number__isnull=False
        ).exclude(id_number='').count()

        with_id_number_alt = LiveOnlineClaim.objects.filter(
            id_number_alt__isnull=False
        ).exclude(id_number_alt='').count()

        with_passport = LiveOnlineClaim.objects.filter(
            passport_no__isnull=False
        ).exclude(passport_no='').count()

        rejected_count = LiveOnlineClaim.objects.filter(
            rejected=True,
        ).count()

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
                'rejected': bool(s.rejected),
                'rejection_reason': s.rejection_reason,
            })

        return Response({
            'success': True,
            'total_claims': total,
            'claims_with_id_number': with_id_number,
            'claims_with_id_number_alt': with_id_number_alt,
            'claims_with_passport': with_passport,
            'claims_rejected': rejected_count,
            'sample_records': sample_data,
        })

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error checking data: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'error': error_msg,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_database_asset_search(request):
    """Test endpoint to verify direct database asset search is working."""
    try:
        test_identifier = request.GET.get('identifier', '12345678')
        test_search_type = request.GET.get('search_type', 'id')

        logger.info(
            "Testing direct database asset search - ID: %s", test_identifier,
        )

        assets = LiveDatabaseService.search_unclaimed_assets(
            test_identifier, test_search_type,
        )

        return Response({
            'success': True,
            'message': 'Direct database search is working',
            'test_identifier': test_identifier,
            'search_type': test_search_type,
            'assets_found': len(assets),
            'sample_assets': assets[:5] if assets else [],
            'database': 'ereunify',
        }, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Test database search failed: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'error': str(e),
            'detail': error_traceback,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PUSH TO LIVE ENDPOINTS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_claim_to_live(request, claim_id):
    """Push a specific claim to the live database"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
            }, status=status.HTTP_403_FORBIDDEN)

        result = LiveDatabaseService.push_claim_to_live(claim_id)

        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error pushing claim to live: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_pending_claims(request):
    """Push all pending claims to the live database"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
            }, status=status.HTTP_403_FORBIDDEN)

        result = LiveDatabaseService.push_pending_claims_to_live()

        return Response(result, status=status.HTTP_200_OK)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error pushing pending claims: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_push_status(request, task_id):
    """Check the status of a Celery push task"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
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

        logger.error("Error checking task status: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_push_to_live(request):
    """Manually trigger the Celery task to push claims to live database"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
            }, status=status.HTTP_403_FORBIDDEN)

        task = push_pending_claims_to_live.delay()

        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'message': 'Push task triggered successfully',
        }, status=status.HTTP_202_ACCEPTED)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error triggering push task: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_push_claims_by_ids(request):
    """Manually trigger push for specific claims by IDs"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
            }, status=status.HTTP_403_FORBIDDEN)

        claim_ids = request.data.get('claim_ids', [])

        if not claim_ids:
            return Response({
                'success': False,
                'message': 'claim_ids list is required',
            }, status=status.HTTP_400_BAD_REQUEST)

        task = push_claims_by_ids.delay(claim_ids)

        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'claim_ids': claim_ids,
            'message': f'Push task triggered for {len(claim_ids)} claims',
        }, status=status.HTTP_202_ACCEPTED)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error triggering push by IDs: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_single_claim_async(request):
    """Asynchronously push a single claim to the live database via Celery"""
    try:
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Permission denied. Staff access required.',
            }, status=status.HTTP_403_FORBIDDEN)

        claim_id = request.data.get('claim_id')

        if not claim_id:
            return Response({
                'success': False,
                'message': 'claim_id is required',
            }, status=status.HTTP_400_BAD_REQUEST)

        task = push_single_claim_to_live.delay(claim_id)

        return Response({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'claim_id': claim_id,
            'message': f'Push task triggered for claim ID {claim_id}',
        }, status=status.HTTP_202_ACCEPTED)

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        logger.error("Error triggering single push: %s", error_msg)
        logger.error("Traceback: %s", error_traceback)

        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
