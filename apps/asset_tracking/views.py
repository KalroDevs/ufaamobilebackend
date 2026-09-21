# apps/asset_tracking/views.py
import logging
import math

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.live_operations.services import LiveDatabaseService

from .models import TrackedAsset, AssetLocationLog, AssetTrackingDocument
from .serializers import (
    TrackedAssetSerializer,
    TrackedAssetCreateSerializer,
    AssetTrackingDocumentSerializer,
)

logger = logging.getLogger(__name__)


# ==================== HELPERS ====================

def _haversine_km(lat1, lon1, lat2, lon2):
    """
    Distance in km between two lat/lng points.

    Kept for future use — the current tracking flow no longer sends
    staff coordinates, so this is not called from `track_asset`.
    """
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _flatten_serializer_errors(errors):
    """
    Turn a DRF errors dict into a single readable string.
    """
    parts = []
    for field, msgs in errors.items():
        if isinstance(msgs, (list, tuple)):
            text = ', '.join(str(m) for m in msgs)
        else:
            text = str(msgs)
        parts.append(f"{field}: {text}")
    return '; '.join(parts) if parts else 'Invalid payload.'


# ==================== SEARCH: LIVE ASSETS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_search_assets(request):
    """
    Search for unclaimed assets using the live database.

    Body:
        { "identifier": "27457180", "search_type": "id" }

    search_type: 'id' | 'passport' | 'cds'

    Only assets whose live [Status] is below
    MAX_SEARCHABLE_ASSET_STATUS (2) are returned.
    """
    identifier = (request.data.get('identifier') or '').strip()
    search_type = (request.data.get('search_type') or 'id').strip().lower()

    if not identifier:
        return Response(
            {'success': False, 'message': 'identifier is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if search_type not in ('id', 'passport', 'cds'):
        return Response(
            {
                'success': False,
                'message': 'search_type must be one of: id, passport, cds',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        assets = LiveDatabaseService.search_unclaimed_assets(
            identifier, search_type
        )
        return Response({
            'success': True,
            'count': len(assets),
            'results': assets,
            'search_type': search_type,
            'identifier': identifier,
        })
    except Exception as exc:
        logger.exception(
            "Asset search failed for %s=%s", search_type, identifier,
        )
        return Response(
            {'success': False, 'message': str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== TRACKED ASSETS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_asset(request):
    """
    Create or update a TrackedAsset for the current user.

    Body: see TrackedAssetCreateSerializer.

    Idempotency:
        unique_together on (asset_no, staff_email) means re-posting the
        same asset for the same user updates the existing row instead
        of creating a duplicate.
    """
    serializer = TrackedAssetCreateSerializer(data=request.data)

    if not serializer.is_valid():
        flat_message = _flatten_serializer_errors(serializer.errors)

        logger.warning(
            "track_asset validation failed | user=%s | payload=%r | errors=%r",
            getattr(request.user, 'email', None),
            request.data,
            serializer.errors,
        )

        return Response(
            {
                'success': False,
                'message': f'Invalid payload: {flat_message}',
                'errors': serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    user = request.user

    asset_no = data['asset_no']
    staff_email = (user.email or '').strip().lower()

    if not staff_email:
        return Response(
            {'success': False, 'message': 'User email is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---------------------------------------------------------------- #
    # Upsert the TrackedAsset
    # ---------------------------------------------------------------- #
    tracked, created = TrackedAsset.objects.get_or_create(
        asset_no=asset_no,
        staff_email=staff_email,
        defaults={
            'staff_user': user,
            'staff_name': user.get_full_name() or user.username,
        },
    )

    # Fields we always accept on update.
    updatable_fields = [
        'asset_name', 'asset_owner', 'holder_name', 'holder_no',
        'asset_type', 'source',
        'id_number', 'passport_no', 'cds_account_no',
        'postal_address', 'city_town', 'county', 'physical_address',
        'latitude', 'longitude',
    ]
    for field in updatable_fields:
        value = data.get(field)
        if value not in (None, ''):
            setattr(tracked, field, value)

    # ---------------------------------------------------------------- #
    # Status + notes
    # ---------------------------------------------------------------- #
    new_status = data.get('status') or tracked.status or 'pending'
    notes = data.get('notes') or ''

    tracked.status = new_status
    if notes:
        tracked.last_notes = notes
    tracked.last_tracked_at = timezone.now()
    tracked.last_tracked_by = staff_email

    # The client no longer sends staff coordinates. Clear the cached
    # values on the model so the last update reflects the current
    # payload. The columns remain for future use.
    tracked.last_staff_latitude = None
    tracked.last_staff_longitude = None
    tracked.save()

    # ---------------------------------------------------------------- #
    # Always log a tracking event
    # ---------------------------------------------------------------- #
    AssetLocationLog.objects.create(
        tracked_asset=tracked,
        status=new_status,
        notes=notes,
        staff_email=staff_email,
        staff_name=user.get_full_name() or user.username,
        # No staff coordinates on the payload any more.
        staff_latitude=None,
        staff_longitude=None,
        distance_km=None,
    )

    logger.info(
        "track_asset %s | created=%s | status=%s | staff=%s",
        asset_no,
        created,
        new_status,
        staff_email,
    )

    return Response({
        'success': True,
        'created': created,
        'asset': TrackedAssetSerializer(tracked).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tracked_assets(request):
    """Return every asset this user has tracked."""
    staff_email = (request.user.email or '').strip().lower()
    qs = (
        TrackedAsset.objects
        .filter(staff_email=staff_email)
        .prefetch_related('documents', 'location_logs')
    )

    return Response({
        'success': True,
        'count': qs.count(),
        'results': TrackedAssetSerializer(qs, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tracked_asset_detail(request, asset_id):
    """Detail view for a single tracked asset."""
    try:
        tracked = (
            TrackedAsset.objects
            .prefetch_related('documents', 'location_logs')
            .get(id=asset_id)
        )
    except TrackedAsset.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Tracked asset not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        'success': True,
        'asset': TrackedAssetSerializer(tracked).data,
    })


# ==================== DOCUMENTS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_tracking_document(request, asset_id):
    """
    Upload a tracking document for a tracked asset.

    Form fields:
        file           (required)
        document_type  (photo|form|receipt|letter|id|other)
        document_name  (optional)
        notes          (optional)
    """
    try:
        tracked = TrackedAsset.objects.get(id=asset_id)
    except TrackedAsset.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Tracked asset not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    upload = request.FILES.get('file')
    if not upload:
        return Response(
            {'success': False, 'message': 'file is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    document_type = (request.data.get('document_type') or 'other').strip()
    document_name = (request.data.get('document_name') or upload.name).strip()
    notes = request.data.get('notes', '')

    doc = AssetTrackingDocument.objects.create(
        tracked_asset=tracked,
        document_type=document_type,
        document_name=document_name,
        file=upload,
        file_size=upload.size,
        file_extension=(
            upload.name.split('.')[-1].lower() if '.' in upload.name else ''
        ),
        uploaded_by=request.user,
        uploaded_by_email=(request.user.email or '').lower(),
        notes=notes,
    )

    logger.info(
        "upload_tracking_document | asset_id=%s | doc_id=%s | size=%s | user=%s",
        asset_id, doc.id, upload.size, getattr(request.user, 'email', None),
    )

    return Response({
        'success': True,
        'document': AssetTrackingDocumentSerializer(doc).data,
    }, status=status.HTTP_201_CREATED)
