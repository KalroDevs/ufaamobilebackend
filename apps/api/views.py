# apps/api/views.py
import logging

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    login as django_login,
    logout as django_logout,
)
from django.db import models as django_models
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

from axes.decorators import axes_dispatch

from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

# Models
from apps.accounts.models import (
    User,
    LoginAttempt,
    UserActivityLog,
    Notification,
)
from apps.assets.models import Asset, AssetLocation, AssetTrackingHistory
from apps.claims.models import (
    Claim,
    ClaimAsset,
    ClaimDocument,
    ClaimNote,
    ClaimStatusHistory,
)

# Serializers
from apps.accounts.serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    StaffProfileSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
    CheckVerificationStatusSerializer,
    DeleteAccountSerializer,
    NotificationSerializer,
)
from apps.assets.serializers import (
    AssetSerializer,
    AssetSearchSerializer,
    AssetLocationSerializer,
    AssetLocationUpdateSerializer,
    AssetTrackingHistorySerializer,
)
from apps.claims.serializers import (
    ClaimSerializer,
    ClaimCreateSerializer,
    ClaimStatusSerializer,
    ClaimActionSerializer,
    ClaimSearchSerializer,
    ClaimDocumentSerializer,
    ClaimNoteSerializer,
    ClaimStatusHistorySerializer,
)

logger = logging.getLogger(__name__)


# ============================================================
# AUTH VIEWSET
# ============================================================
class AuthViewSet(viewsets.GenericViewSet):
    """
    Authentication ViewSet for user registration, login, and password
    management.
    """

    permission_classes = [AllowAny]
    serializer_class = None

    # ---------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------- #
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
            if ip:
                return ip
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip
        remote_addr = request.META.get('REMOTE_ADDR')
        if remote_addr:
            return remote_addr
        return '0.0.0.0'

    def _log_activity(self, user, activity_type, description, request):
        try:
            UserActivityLog.objects.create(
                user=user,
                activity_type=activity_type,
                description=description,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        except Exception as e:
            logger.error("Failed to log activity: %s", e)

    # ---------------------------------------------------------------- #
    # Registration
    # ---------------------------------------------------------------- #
    @action(detail=False, methods=['post'])
    def register(self, request):
        try:
            serializer = RegisterSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save()
            refresh = RefreshToken.for_user(user)

            self._log_activity(
                user, 'register',
                f'User registered with ID: {user.id_number}', request,
            )

            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)
            csrf_token = get_token(request)

            return Response(
                {
                    'success': True,
                    'message': (
                        'Registration successful! Please check your email '
                        'to verify your account.'
                    ),
                    'user': UserSerializer(user).data,
                    'csrf_token': csrf_token,
                    'session_id': request.session.session_key,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.exception("Registration error")
            return Response(
                {
                    'success': False,
                    'message': 'Registration failed',
                    'error': (
                        str(e) if settings.DEBUG
                        else 'An error occurred during registration'
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ---------------------------------------------------------------- #
    # Login / Logout
    # ---------------------------------------------------------------- #
    @method_decorator(csrf_exempt)
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        client_ip = self._get_client_ip(request)
        identifier = request.data.get('identifier', '').strip()
        password = request.data.get('password', '')
        device_fingerprint = request.data.get('device_fingerprint', '')

        if not identifier or not password:
            return Response(
                {
                    'success': False,
                    'message': 'Please provide identifier and password',
                    'error': 'Missing credentials',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = LoginSerializer(
            data=request.data,
            context={'request': request},
        )

        if not serializer.is_valid():
            LoginAttempt.objects.create(
                user=None,
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint,
            )
            return Response(
                {
                    'success': False,
                    'message': 'Invalid credentials',
                    'errors': serializer.errors,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.validated_data['user']

        try:
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)
            csrf_token = get_token(request)
            refresh = RefreshToken.for_user(user)

            if device_fingerprint:
                user.device_fingerprint = device_fingerprint
                user.save(update_fields=['device_fingerprint'])

            LoginAttempt.objects.create(
                user=user,
                identifier=identifier,
                ip_address=client_ip,
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint,
            )

            self._log_activity(
                user, 'login', 'User logged in from mobile app', request,
            )

            return Response(
                {
                    'success': True,
                    'message': (
                        f'Welcome back, '
                        f'{user.get_full_name() or user.username}!'
                    ),
                    'user': UserSerializer(user).data,
                    'session_id': request.session.session_key,
                    'csrf_token': csrf_token,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Login error for user %s", identifier)
            return Response(
                {
                    'success': False,
                    'message': 'Login failed',
                    'error': (
                        str(e) if settings.DEBUG
                        else 'An error occurred during login'
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @method_decorator(csrf_exempt)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        try:
            user = request.user
            refresh_token = request.data.get('refresh')

            if refresh_token:
                try:
                    RefreshToken(refresh_token).blacklist()
                except Exception as e:
                    logger.warning("Failed to blacklist token: %s", e)

            self._log_activity(user, 'logout', 'User logged out', request)
            django_logout(request)

            return Response(
                {'success': True, 'message': 'Successfully logged out'},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error("Logout error: %s", e)
            return Response(
                {
                    'success': False,
                    'message': 'Logout failed',
                    'error': str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ---------------------------------------------------------------- #
    # Password management
    # ---------------------------------------------------------------- #
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        try:
            serializer = ChangePasswordSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = request.user

            if not user.check_password(serializer.validated_data['old_password']):
                return Response(
                    {
                        'success': False,
                        'message': 'Wrong password',
                        'error': 'old_password',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(serializer.validated_data['new_password'])
            user.save()

            self._log_activity(
                user, 'password_change', 'User changed password', request,
            )

            return Response(
                {'success': True, 'message': 'Password changed successfully'},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Password change error")
            return Response(
                {
                    'success': False,
                    'message': 'Password change failed',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        try:
            serializer = ForgotPasswordSerializer(
                data=request.data,
                context={'request': request},
            )

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = serializer.save()

            return Response(
                {
                    'success': True,
                    'message': result.get(
                        'message',
                        'Password reset instructions sent to your email.',
                    ),
                    'email': result.get('email'),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Forgot password error")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to process password reset',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        try:
            serializer = ResetPasswordSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer.save()

            return Response(
                {
                    'success': True,
                    'message': (
                        'Password reset successfully. You can now login with '
                        'your new password.'
                    ),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Reset password error")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to reset password',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ---------------------------------------------------------------- #
    # Profile
    # ---------------------------------------------------------------- #
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        try:
            return Response(
                {
                    'success': True,
                    'message': 'Profile retrieved successfully',
                    'user': UserSerializer(request.user).data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error("Profile error: %s", e)
            return Response(
                {
                    'success': False,
                    'message': 'Failed to get profile',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        try:
            serializer = UserSerializer(
                request.user, data=request.data, partial=True,
            )

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save()

            self._log_activity(
                user, 'profile_update', 'User updated profile', request,
            )

            return Response(
                {
                    'success': True,
                    'message': 'Profile updated successfully',
                    'user': UserSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Profile update error")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to update profile',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ---------------------------------------------------------------- #
    # Session / CSRF / JWT
    # ---------------------------------------------------------------- #
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def check_session(self, request):
        try:
            expiry_age = request.session.get_expiry_age()
            expiry_date = request.session.get_expiry_date()

            return Response(
                {
                    'success': True,
                    'authenticated': True,
                    'message': 'Session is valid',
                    'user': UserSerializer(request.user).data,
                    'session_id': request.session.session_key,
                    'session_expires_in_seconds': expiry_age,
                    'session_expires_in_hours': round(expiry_age / 3600, 1),
                    'session_expiry_date': expiry_date,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    'success': False,
                    'authenticated': False,
                    'message': 'Session is invalid or expired',
                    'error': str(e) if settings.DEBUG else 'Please login again',
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def csrf_token(self, request):
        try:
            csrf_token = get_token(request)
            return Response(
                {
                    'success': True,
                    'message': 'CSRF token retrieved successfully',
                    'csrf_token': csrf_token,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error("CSRF token error: %s", e)
            return Response(
                {
                    'success': False,
                    'message': 'Failed to get CSRF token',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_jwt(self, request):
        try:
            from rest_framework_simplejwt.views import TokenRefreshView
            return TokenRefreshView.as_view()(request)
        except Exception as e:
            logger.error("JWT refresh error: %s", e)
            return Response(
                {
                    'success': False,
                    'message': 'Failed to refresh token',
                    'error': str(e) if settings.DEBUG else 'Invalid refresh token',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ---------------------------------------------------------------- #
    # Email verification
    # ---------------------------------------------------------------- #
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        try:
            serializer = VerifyEmailSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer.save()

            return Response(
                {
                    'success': True,
                    'message': 'Email verified successfully. You can now login.',
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Email verification error")
            return Response(
                {
                    'success': False,
                    'message': 'Email verification failed',
                    'error': (
                        str(e) if settings.DEBUG
                        else 'Invalid or expired verification token'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        try:
            serializer = ResendVerificationSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer.save()

            return Response(
                {
                    'success': True,
                    'message': (
                        'Verification email sent successfully. '
                        'Please check your inbox.'
                    ),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Resend verification error")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to resend verification email',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        try:
            serializer = CheckVerificationStatusSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Validation failed',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = serializer.to_representation(None)

            return Response(
                {
                    'success': True,
                    'message': 'Verification status retrieved',
                    'data': data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Check verification error")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to check verification status',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ---------------------------------------------------------------- #
    # Delete account (soft delete)
    # ---------------------------------------------------------------- #
    @method_decorator(csrf_exempt)
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAuthenticated],
        url_path='delete-account',
    )
    def delete_account(self, request):
        user = request.user

        serializer = DeleteAccountSerializer(
            data=request.data,
            context={'request': request, 'user': user},
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Account deletion failed',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            snapshot = serializer.save()

            refresh_token = request.data.get('refresh')
            if refresh_token:
                try:
                    RefreshToken(refresh_token).blacklist()
                except Exception as e:
                    logger.warning("Could not blacklist refresh token: %s", e)

            try:
                django_logout(request)
            except Exception:
                pass

            return Response(
                {
                    'success': True,
                    'message': (
                        'Your account has been deleted. '
                        'We are sorry to see you go.'
                    ),
                    'deleted': {
                        'username': snapshot.get('username'),
                        'email': snapshot.get('email'),
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Unexpected error soft-deleting account")
            return Response(
                {
                    'success': False,
                    'message': 'Account deletion failed',
                    'error': str(e) if settings.DEBUG else 'An error occurred',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ============================================================
# ASSET VIEWSET
# ============================================================
class AssetViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing and searching assets."""

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
        if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
            return Asset.objects.all()
        return Asset.objects.filter(
            django_models.Q(id_number=user.id_number)
            | django_models.Q(passport_no=user.passport_no)
        )

    @action(detail=False, methods=['post'])
    def search(self, request):
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
            return Response(
                {'count': assets.count(), 'results': result_serializer.data}
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def location(self, request, pk=None):
        asset = self.get_object()
        location = AssetLocation.objects.filter(asset=asset).first()
        if location:
            return Response(AssetLocationSerializer(location).data)
        return Response(
            {'message': 'Location not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        asset = self.get_object()
        history = AssetTrackingHistory.objects.filter(asset=asset)
        return Response(
            AssetTrackingHistorySerializer(history, many=True).data
        )


# ============================================================
# STAFF ASSET TRACKER VIEWSET
# ============================================================
class StaffAssetTrackerViewSet(viewsets.GenericViewSet):
    """
    ViewSet for staff asset tracking.

    Registered at /api/staff/assets/. Provides search, per-asset
    location updates, a pending-verification list, and aggregate
    statistics. Only staff and admin roles can reach the actions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()

    def get_queryset(self):
        if not (
            self.request.user.is_staff
            or getattr(self.request.user, 'role', '') in ['staff', 'admin']
        ):
            return Asset.objects.none()
        return Asset.objects.all()

    @action(detail=False, methods=['post'])
    def search_assets(self, request):
        """Search for assets by staff."""
        search_term = request.data.get('search_term', '')
        assets = Asset.objects.filter(
            django_models.Q(name__icontains=search_term)
            | django_models.Q(holder_name__icontains=search_term)
            | django_models.Q(asset_no__icontains=search_term)
            | django_models.Q(id_number__icontains=search_term)
        )
        serializer = AssetSerializer(assets, many=True)
        return Response({
            'count': assets.count(),
            'results': serializer.data,
        })

    @action(detail=True, methods=['patch'])
    def update_location(self, request, pk=None):
        """Update asset location."""
        asset = self.get_object()
        serializer = AssetLocationUpdateSerializer(data=request.data)

        if serializer.is_valid():
            asset.location_source = request.data.get(
                'location_source', asset.location_source
            )
            asset.physical_address = request.data.get(
                'address', asset.physical_address
            )
            asset.latitude = request.data.get('latitude', asset.latitude)
            asset.longitude = request.data.get('longitude', asset.longitude)
            asset.status = request.data.get('status', asset.status)
            asset.save()

            AssetLocation.objects.update_or_create(
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
                },
            )

            AssetTrackingHistory.objects.create(
                asset=asset,
                previous_status=asset.status,
                new_status=request.data.get('status', asset.status),
                notes=request.data.get('notes', ''),
                updated_by=request.user,
                location=request.data.get('address', ''),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude'),
            )

            return Response({
                'message': 'Asset location updated successfully',
                'asset_no': asset.asset_no,
                'status': asset.status,
                'location': {
                    'latitude': str(asset.latitude) if asset.latitude else None,
                    'longitude': str(asset.longitude) if asset.longitude else None,
                    'address': asset.physical_address,
                },
            })
        return Response(
            serializer.errors, status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['get'])
    def pending_assets(self, request):
        """Get assets pending location verification."""
        assets = Asset.objects.filter(status='pending')
        serializer = AssetSerializer(assets, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get asset tracking statistics."""
        stats = {
            'total_assets': Asset.objects.count(),
            'pending_verification': Asset.objects.filter(status='pending').count(),
            'verified_found': Asset.objects.filter(status='found').count(),
            'verified_not_found': Asset.objects.filter(status='not_found').count(),
            'transferred': Asset.objects.filter(status='transferred').count(),
        }
        return Response(stats)


# ============================================================
# CLAIM VIEWSET
# ============================================================
class ClaimViewSet(viewsets.ModelViewSet):
    """ViewSet for managing claims."""

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
            django_models.Q(claimant=user)
            | django_models.Q(id_number=user.id_number)
            | django_models.Q(phone_no=user.phone_no)
            | django_models.Q(e_mail=user.email)
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
            data=request.data, context={'request': request},
        )
        if serializer.is_valid():
            claim = serializer.save()
            return Response(
                ClaimSerializer(claim).data, status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
            claim=claim,
            previous_status=old_status,
            new_status='Pending',
            changed_by=request.user,
            reason='Claim submitted for review',
        )

        return Response({
            'message': 'Claim submitted successfully',
            'claim_no': claim.no,
            'status': claim.status,
        })

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        claim = self.get_object()
        return Response(ClaimStatusSerializer(claim).data)

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        claim = self.get_object()
        history = claim.status_history.all()
        return Response(
            ClaimStatusHistorySerializer(history, many=True).data
        )

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        claim = self.get_object()
        documents = claim.documents.all()
        return Response(
            ClaimDocumentSerializer(documents, many=True).data
        )

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        claim = self.get_object()

        file = request.FILES.get('file')
        document_type = request.data.get('document_type')
        document_name = request.data.get(
            'document_name', file.name if file else ''
        )

        if not file or not document_type:
            return Response(
                {'error': 'file and document_type are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = ClaimDocument.objects.create(
            claim=claim,
            document_type=document_type,
            document_name=document_name,
            file_path=f"documents/{claim.no}/{file.name}",
            file_size=file.size,
            file_extension=(
                file.name.split('.')[-1] if '.' in file.name else ''
            ),
            uploaded_by=request.user,
        )

        return Response(
            ClaimDocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
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


# ============================================================
# NOTIFICATION VIEWSET
# ============================================================
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and manage the current user's in-app notifications.

    Routes:
        GET    /api/notifications/
        GET    /api/notifications/unread_count/
        POST   /api/notifications/{id}/mark_read/
        POST   /api/notifications/mark_all_read/
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['category', 'is_read']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='unread_count')
    def unread_count(self, request):
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return Response(
            {'success': True, 'unread_count': count},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='mark_read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response(
            {'success': True},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='mark_all_read')
    def mark_all_read(self, request):
        marked = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response(
            {'success': True, 'marked': marked},
            status=status.HTTP_200_OK,
        )


# ============================================================
# FUNCTION-BASED VIEWS
# ============================================================
@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification(request):
    serializer = ResendVerificationSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(
            {
                'success': True,
                'message': (
                    'Verification email sent successfully. '
                    'Please check your inbox.'
                ),
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {'success': False, 'errors': serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def verify_email(request):
    if request.method == 'GET':
        token = request.GET.get('token')
        email = request.GET.get('email')

        if not email or not token:
            return redirect(
                f"{settings.FRONTEND_URL}/email-verification"
                f"?success=false&error=missing_params"
            )

        data = {'email': email, 'token': token, 'verification_code': ''}
        serializer = VerifyEmailSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            return redirect(
                f"{settings.FRONTEND_URL}/email-verification?success=true"
            )
        return redirect(
            f"{settings.FRONTEND_URL}/email-verification"
            f"?success=false&error=invalid_token"
        )

    serializer = VerifyEmailSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(
            {
                'success': True,
                'message': 'Email verified successfully. You can now login.',
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {'success': False, 'errors': serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def check_verification_status(request):
    serializer = CheckVerificationStatusSerializer(data=request.data)

    if serializer.is_valid():
        return Response(
            {
                'success': True,
                'data': serializer.to_representation(None),
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {'success': False, 'errors': serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_claim_document(request, claim_id):
    try:
        claim = Claim.objects.get(id=claim_id)

        if claim.claimant != request.user:
            if not (
                request.user.is_staff
                or getattr(request.user, 'role', '') in ['staff', 'admin']
            ):
                return Response(
                    {
                        'error': (
                            'You do not have permission to upload documents '
                            'for this claim.'
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
    except Claim.DoesNotExist:
        return Response(
            {'error': 'Claim not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    file = request.FILES.get('file')
    document_type = request.data.get('document_type', 'other')
    document_name = request.data.get(
        'document_name', file.name if file else ''
    )

    if not file:
        return Response(
            {'error': 'No file provided.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    document = ClaimDocument.objects.create(
        claim=claim,
        document_type=document_type,
        document_name=document_name,
        file_path=f"documents/{claim.no}/{file.name}",
        file_size=file.size,
        file_extension=file.name.split('.')[-1] if '.' in file.name else '',
        uploaded_by=request.user,
    )

    return Response(
        {
            'success': True,
            'message': 'Document uploaded successfully',
            'document': {
                'id': document.id,
                'document_type': document.document_type,
                'document_name': document.document_name,
                'uploaded_at': document.uploaded_at,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_documents(request, claim_id):
    try:
        claim = Claim.objects.get(id=claim_id)

        if claim.claimant != request.user:
            if not (
                request.user.is_staff
                or getattr(request.user, 'role', '') in ['staff', 'admin']
            ):
                return Response(
                    {
                        'error': (
                            'You do not have permission to view documents '
                            'for this claim.'
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
    except Claim.DoesNotExist:
        return Response(
            {'error': 'Claim not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    documents = claim.documents.all()
    return Response([
        {
            'id': doc.id,
            'document_type': doc.document_type,
            'document_name': doc.document_name,
            'file_path': doc.file_path,
            'file_size': doc.file_size,
            'uploaded_at': doc.uploaded_at,
            'is_verified': doc.is_verified,
        }
        for doc in documents
    ], status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def test_forgot_password(request):
    identifier = request.data.get('identifier')
    if not identifier:
        return Response({'error': 'No identifier provided'}, status=400)

    user = None

    if '@' in identifier:
        try:
            user = User.objects.get(email=identifier)
        except User.DoesNotExist:
            pass

    if not user and identifier.isdigit() and len(identifier) in [7, 8]:
        try:
            user = User.objects.get(id_number=identifier)
        except User.DoesNotExist:
            pass

    if not user:
        try:
            import re
            clean_phone = re.sub(r'[\s\-\(\)]', '', identifier)
            if clean_phone.startswith('0'):
                clean_phone = '254' + clean_phone[1:]
            elif clean_phone.startswith('7'):
                clean_phone = '254' + clean_phone
            elif clean_phone.startswith('+254'):
                clean_phone = clean_phone[1:]
            user = User.objects.get(phone_no__contains=clean_phone[-9:])
        except User.DoesNotExist:
            pass

    if not user:
        return Response(
            {'error': f'No user found with identifier: {identifier}'},
            status=404,
        )

    return Response(
        {
            'success': True,
            'message': f'Found user: {user.email}',
            'email': user.email,
            'id_number': user.id_number,
            'phone_no': user.phone_no,
        },
        status=200,
    )
