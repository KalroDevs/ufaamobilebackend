# apps/iprs/views.py
import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IprsCache, IprsSearchLog
from .serializers import (
    IprsBulkLookupSerializer,
    IprsCacheSerializer,
    IprsLookupRequestSerializer,
    IprsPersonalDetailsSerializer,
    IprsSearchLogSerializer,
)
from .services import (
    IprsNotFoundError,
    IprsRateLimitError,
    IprsServiceError,
    IprsTimeoutError,
    get_iprs_service,
)

logger = logging.getLogger(__name__)


class IsStaffOrAdminUser(BasePermission):
    """Permission class to allow access to Django staff or users with staff/admin roles."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_staff or getattr(user, 'role', '') in ['staff', 'admin'])


def get_client_ip(request):
    """Extract client IP address safely from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        if ip:
            return ip
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _get_safe_int(value, default=100, max_val=None):
    """Safely convert string query parameters to integer without throwing ValueError."""
    try:
        parsed = int(value)
        if max_val is not None:
            return min(parsed, max_val)
        return parsed
    except (TypeError, ValueError):
        return default


class IprsLookupView(APIView):
    """
    Public API endpoint to look up personal details from IPRS using a national ID number.
    
    POST /api/iprs/lookup/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = IprsLookupRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        id_card = serializer.validated_data['id_card']
        use_cache = serializer.validated_data.get('use_cache', True)
        device_fingerprint = serializer.validated_data.get('device_fingerprint', '')

        service = get_iprs_service()

        try:
            result = service.lookup_id(
                id_card=id_card,
                use_cache=use_cache,
                log_search=True,
                requested_from_ip=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint,
            )

            details_serializer = IprsPersonalDetailsSerializer(result)

            return Response({
                'success': True,
                'message': 'ID card found in IPRS',
                'data': details_serializer.data,
            }, status=status.HTTP_200_OK)

        except IprsNotFoundError:
            return Response({
                'success': False,
                'message': 'ID card not found in IPRS',
                'error': 'not_found',
                'id_card': id_card,
            }, status=status.HTTP_404_NOT_FOUND)

        except IprsTimeoutError:
            logger.warning(f"IPRS lookup timed out for ID: {id_card}")
            return Response({
                'success': False,
                'message': 'IPRS service timed out. Please try again.',
                'error': 'timeout',
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)

        except IprsRateLimitError as e:
            logger.warning(f"IPRS rate limit reached during lookup for ID: {id_card}")
            return Response({
                'success': False,
                'message': str(e),
                'error': 'rate_limited',
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        except IprsServiceError as e:
            logger.error(f"IPRS service error for ID {id_card}: {e}")
            return Response({
                'success': False,
                'message': 'Failed to look up ID card',
                'error': str(e) if settings.DEBUG else 'service_error',
            }, status=status.HTTP_502_BAD_GATEWAY)

        except ValueError as e:
            return Response({
                'success': False,
                'message': str(e),
                'error': 'validation_error',
            }, status=status.HTTP_400_BAD_REQUEST)


class IprsVerifyView(APIView):
    """
    Public API endpoint to verify if an ID card exists in IPRS.
    
    POST /api/iprs/verify/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = IprsLookupRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        id_card = serializer.validated_data['id_card']
        use_cache = serializer.validated_data.get('use_cache', True)
        device_fingerprint = serializer.validated_data.get('device_fingerprint', '')

        service = get_iprs_service()

        try:
            service.lookup_id(
                id_card=id_card,
                use_cache=use_cache,
                log_search=True,
                requested_from_ip=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint,
            )

            return Response({
                'success': True,
                'id_card': id_card,
                'exists': True,
                'message': 'ID card exists in IPRS',
            }, status=status.HTTP_200_OK)

        except IprsNotFoundError:
            return Response({
                'success': True,
                'id_card': id_card,
                'exists': False,
                'message': 'ID card not found in IPRS',
            }, status=status.HTTP_200_OK)

        except (IprsTimeoutError, IprsRateLimitError, IprsServiceError) as e:
            logger.error(f"IPRS verification failed for ID {id_card}: {e}")
            return Response({
                'success': False,
                'message': 'Failed to verify ID card',
                'error': str(e) if settings.DEBUG else 'service_error',
            }, status=status.HTTP_502_BAD_GATEWAY)


class IprsBulkLookupView(APIView):
    """
    API endpoint for bulk IPRS lookups.
    
    POST /api/iprs/bulk-lookup/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = IprsBulkLookupSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        id_cards = serializer.validated_data['id_cards']
        use_cache = serializer.validated_data.get('use_cache', True)
        device_fingerprint = serializer.validated_data.get('device_fingerprint', '')

        service = get_iprs_service()
        client_ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        results = []
        found_count = 0
        not_found_count = 0
        error_count = 0

        for id_card in id_cards:
            try:
                result = service.lookup_id(
                    id_card=id_card,
                    use_cache=use_cache,
                    log_search=True,
                    requested_from_ip=client_ip,
                    user_agent=user_agent,
                    device_fingerprint=device_fingerprint,
                )

                results.append({
                    'id_card': id_card,
                    'success': True,
                    'data': IprsPersonalDetailsSerializer(result).data,
                })
                found_count += 1

            except IprsNotFoundError:
                results.append({
                    'id_card': id_card,
                    'success': False,
                    'error': 'not_found',
                    'message': 'ID card not found in IPRS',
                })
                not_found_count += 1

            except (IprsTimeoutError, IprsRateLimitError, IprsServiceError) as e:
                results.append({
                    'id_card': id_card,
                    'success': False,
                    'error': 'service_error',
                    'message': str(e) if settings.DEBUG else 'Failed to complete search',
                })
                error_count += 1

        return Response({
            'success': True,
            'message': f'Processed {len(id_cards)} ID cards',
            'summary': {
                'total': len(id_cards),
                'found': found_count,
                'not_found': not_found_count,
                'errors': error_count,
            },
            'results': results,
        }, status=status.HTTP_200_OK)


class IprsSearchLogListView(APIView):
    """
    Staff-only endpoint to view IPRS search logs.
    
    GET /api/iprs/search-logs/
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdminUser]

    def get(self, request):
        qs = IprsSearchLog.objects.all()

        id_card = request.query_params.get('id_card')
        if id_card:
            qs = qs.filter(id_card=id_card)

        log_status = request.query_params.get('status')
        if log_status:
            qs = qs.filter(status=log_status)

        hours = request.query_params.get('hours')
        if hours:
            hours_val = _get_safe_int(hours, default=None)
            if hours_val and hours_val > 0:
                cutoff = timezone.now() - timezone.timedelta(hours=hours_val)
                qs = qs.filter(created_at__gte=cutoff)

        limit = _get_safe_int(request.query_params.get('limit'), default=100, max_val=500)
        qs = qs[:limit]

        serializer = IprsSearchLogSerializer(qs, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'results': serializer.data,
        }, status=status.HTTP_200_OK)


class IprsCacheListView(APIView):
    """
    Staff-only endpoint to view and manage the IPRS cache.
    
    GET /api/iprs/cache/
    DELETE /api/iprs/cache/
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdminUser]

    def get(self, request):
        qs = IprsCache.objects.all()

        id_card = request.query_params.get('id_card')
        if id_card:
            qs = qs.filter(id_card=id_card)

        is_valid = request.query_params.get('is_valid')
        if is_valid is not None:
            qs = qs.filter(is_valid=is_valid.lower() in ['true', '1', 'yes'])

        limit = _get_safe_int(request.query_params.get('limit'), default=100, max_val=500)
        qs = qs[:limit]

        serializer = IprsCacheSerializer(qs, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'results': serializer.data,
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        id_card = request.query_params.get('id_card')

        if id_card:
            deleted, _ = IprsCache.objects.filter(id_card=id_card).delete()
            return Response({
                'success': True,
                'message': f'Deleted cache entry for ID {id_card}',
                'deleted': deleted,
            }, status=status.HTTP_200_OK)

        count = IprsCache.cleanup_expired()
        return Response({
            'success': True,
            'message': f'Cleaned up {count} expired cache entries',
            'deleted': count,
        }, status=status.HTTP_200_OK)
