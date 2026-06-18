# apps/api/views.py
import logging
from rest_framework import viewsets, status, generics, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models as django_models
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from axes.decorators import axes_dispatch
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.middleware.csrf import get_token



from apps.claims.serializers import ClaimSerializer, ClaimCreateSerializer
from apps.accounts.models import User, LoginAttempt, UserActivityLog
from apps.accounts.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, 
    StaffProfileSerializer, ChangePasswordSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer, ResendVerificationSerializer,
    VerifyEmailSerializer, CheckVerificationStatusSerializer
)
from apps.assets.models import Asset, AssetLocation, AssetTrackingHistory
from apps.assets.serializers import (
    AssetSerializer, AssetSearchSerializer, AssetLocationSerializer,
    AssetLocationUpdateSerializer, AssetTrackingHistorySerializer
)
from apps.claims.models import Claim, ClaimAsset, ClaimDocument, ClaimNote, ClaimStatusHistory
from apps.claims.serializers import (
    ClaimSerializer, ClaimCreateSerializer, ClaimStatusSerializer,
    ClaimActionSerializer, ClaimSearchSerializer, ClaimDocumentSerializer,
    ClaimNoteSerializer, ClaimStatusHistorySerializer
)

logger = logging.getLogger(__name__)

class AuthViewSetNew(viewsets.GenericViewSet):
    """
    Authentication ViewSet supporting both Session and JWT authentication.
    Returns response format compatible with Flutter app.
    """
    permission_classes = [AllowAny]
    serializer_class = None

    def _get_client_ip(self, request):
        """
        Get client IP address from request headers.
        Handles cases where the app is behind a proxy (nginx/gunicorn).
        """
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
        """Log user activity"""
        try:
            UserActivityLog.objects.create(
                user=user,
                activity_type=activity_type,
                description=description,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user - Flutter compatible response"""
        try:
            serializer = RegisterSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            # Log registration
            self._log_activity(
                user, 
                'register', 
                f'User registered with ID: {user.id_number}',
                request
            )
            
            # Create session
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)  # 72 hours
            csrf_token = get_token(request)
            
            # Flutter expects access and refresh at top level
            return Response({
                'success': True,
                'message': 'Registration successful! Please check your email to verify your account.',
                'user': UserSerializer(user).data,
                'csrf_token': csrf_token,
                'session_id': request.session.session_key,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return Response({
                'success': False,
                'message': 'Registration failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during registration'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """
        Login user - Flutter compatible response.
        Returns access and refresh tokens at top level.
        """
        client_ip = self._get_client_ip(request)
        identifier = request.data.get('identifier', '').strip()
        password = request.data.get('password', '')
        device_fingerprint = request.data.get('device_fingerprint', '')
        
        # Log login attempt
        logger.info(f"Login attempt for identifier: {identifier} from IP: {client_ip}")
        
        # Validate input
        if not identifier or not password:
            return Response({
                'success': False,
                'message': 'Please provide identifier and password',
                'error': 'Missing credentials'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use LoginSerializer for validation
        serializer = LoginSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if not serializer.is_valid():
            # Log failed attempt
            LoginAttempt.objects.create(
                user=None,
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            return Response({
                'success': False,
                'message': 'Invalid credentials',
                'errors': serializer.errors
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated user
        user = serializer.validated_data['user']
        logger.info(f"User authenticated: {user.username}")
        
        try:
            # ============ CREATE SESSION ============
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)  # 72 hours
            logger.info(f"Session created: {request.session.session_key}")
            
            # ============ GET CSRF TOKEN ============
            csrf_token = get_token(request)
            
            # ============ GENERATE JWT ============
            refresh = RefreshToken.for_user(user)
            
            # ============ UPDATE DEVICE FINGERPRINT ============
            if device_fingerprint:
                user.device_fingerprint = device_fingerprint
                user.save(update_fields=['device_fingerprint'])
            
            # ============ LOG LOGIN ATTEMPT ============
            LoginAttempt.objects.create(
                user=user,
                identifier=identifier,
                ip_address=client_ip,
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            # ============ LOG USER ACTIVITY ============
            self._log_activity(
                user,
                'login',
                'User logged in from mobile app',
                request
            )
            
            logger.info(f"User {user.username} logged in successfully from {client_ip}")
            
            # Get user data
            user_data = UserSerializer(user).data
            
            # ============ FLUTTER COMPATIBLE RESPONSE ============
            # Flutter app expects access and refresh at top level,
            # not nested inside 'data' object
            return Response({
                'success': True,
                'message': f'Welcome back, {user.get_full_name() or user.username}!',
                'user': user_data,
                'session_id': request.session.session_key,
                'csrf_token': csrf_token,
                'refresh': str(refresh),      # Top level for Flutter
                'access': str(refresh.access_token),  # Top level for Flutter
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Login error for user {identifier}: {e}", exc_info=True)
            return Response({
                'success': False,
                'message': 'Login failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during login'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user - Flutter compatible response"""
        try:
            user = request.user
            refresh_token = request.data.get('refresh')
            
            # Blacklist refresh token if provided
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except Exception as e:
                    logger.warning(f"Failed to blacklist token: {e}")
            
            # Log logout activity
            self._log_activity(
                user,
                'logout',
                'User logged out',
                request
            )
            
            # Destroy session
            django_logout(request)
            
            logger.info(f"User {user.username} logged out successfully")
            
            # Flutter expects success at top level
            return Response({
                'success': True,
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({
                'success': False,
                'message': 'Logout failed',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password"""
        try:
            serializer = ChangePasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            
            # Check old password
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'success': False,
                    'message': 'Wrong password',
                    'error': 'old_password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Log activity
            self._log_activity(
                user,
                'password_change',
                'User changed password',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return Response({
                'success': False,
                'message': 'Password change failed',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Request password reset"""
        try:
            serializer = ForgotPasswordSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            result = serializer.save()
            
            return Response({
                'success': True,
                'message': result.get('message', 'Password reset instructions sent to your email.'),
                'email': result.get('email')
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to process password reset',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to reset password',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get current user profile - Flutter compatible"""
        try:
            return Response({
                'success': True,
                'message': 'Profile retrieved successfully',
                'user': UserSerializer(request.user).data  # Direct user object, not nested
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user profile"""
        try:
            serializer = UserSerializer(
                request.user,
                data=request.data,
                partial=True
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = serializer.save()
            
            self._log_activity(
                user,
                'profile_update',
                'User updated profile',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to update profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def check_session(self, request):
        """Check if session is valid"""
        try:
            expiry_age = request.session.get_expiry_age()
            expiry_date = request.session.get_expiry_date()
            
            return Response({
                'success': True,
                'authenticated': True,
                'message': 'Session is valid',
                'user': UserSerializer(request.user).data,
                'session_id': request.session.session_key,
                'session_expires_in_seconds': expiry_age,
                'session_expires_in_hours': round(expiry_age / 3600, 1),
                'session_expiry_date': expiry_date,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'authenticated': False,
                'message': 'Session is invalid or expired',
                'error': str(e) if settings.DEBUG else 'Please login again'
            }, status=status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def csrf_token(self, request):
        """Get CSRF token for mobile app"""
        try:
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'CSRF token retrieved successfully',
                'csrf_token': csrf_token
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"CSRF token error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get CSRF token',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_jwt(self, request):
        """
        Refresh JWT access token - returns only the new access token.
        Flutter expects the new access token.
        """
        try:
            from rest_framework_simplejwt.views import TokenRefreshView
            return TokenRefreshView.as_view()(request)
            
        except Exception as e:
            logger.error(f"JWT refresh error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to refresh token',
                'error': str(e) if settings.DEBUG else 'Invalid refresh token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify user's email address"""
        try:
            serializer = VerifyEmailSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Email verified successfully. You can now login.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({
                'success': False,
                'message': 'Email verification failed',
                'error': str(e) if settings.DEBUG else 'Invalid or expired verification token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        """Resend verification email"""
        try:
            serializer = ResendVerificationSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Verification email sent successfully. Please check your inbox.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Resend verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to resend verification email',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        """Check if user's email is verified"""
        try:
            serializer = CheckVerificationStatusSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = serializer.to_representation(None)
            
            return Response({
                'success': True,
                'message': 'Verification status retrieved',
                'data': data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Check verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to check verification status',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class AuthViewSetOld4(viewsets.GenericViewSet):
    """
    Authentication ViewSet supporting both Session and JWT authentication.
    - Session authentication for mobile app (cookies)
    - JWT authentication for API clients
    """
    permission_classes = [AllowAny]
    serializer_class = None

    def _get_client_ip(self, request):
        """
        Get client IP address from request headers.
        Handles cases where the app is behind a proxy (nginx/gunicorn).
        """
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
        """Log user activity"""
        try:
            UserActivityLog.objects.create(
                user=user,
                activity_type=activity_type,
                description=description,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except Exception as e:
            print(f"Failed to log activity: {e}")

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        try:
            serializer = RegisterSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            # Log registration
            self._log_activity(
                user, 
                'register', 
                f'User registered with ID: {user.id_number}',
                request
            )
            
            # Create session
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)  # 72 hours
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'Registration successful! Please check your email to verify your account.',
                'data': {
                    'user': UserSerializer(user).data,
                    'csrf_token': csrf_token,
                    'session_id': request.session.session_key,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return Response({
                'success': False,
                'message': 'Registration failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during registration'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """
        Login user with ID Number, Email, or Phone Number.
        Creates both session and JWT tokens.
        """
        client_ip = self._get_client_ip(request)
        identifier = request.data.get('identifier', '').strip()
        password = request.data.get('password', '')
        device_fingerprint = request.data.get('device_fingerprint', '')
        
        # Log login attempt (without password)
        logger.info(f"Login attempt for identifier: {identifier} from IP: {client_ip}")
        
        # Validate input
        if not identifier or not password:
            return Response({
                'success': False,
                'message': 'Please provide identifier and password',
                'error': 'Missing credentials'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use LoginSerializer for validation
        serializer = LoginSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if not serializer.is_valid():
            # Log failed attempt
            LoginAttempt.objects.create(
                user=None,
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            return Response({
                'success': False,
                'message': 'Invalid credentials',
                'errors': serializer.errors
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated user
        user = serializer.validated_data['user']
        logger.info(f"User authenticated: {user.username}")
        
        try:
            # ============ CREATE SESSION ============
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)  # 72 hours
            logger.info(f"Session created: {request.session.session_key}")
            
            # ============ GET CSRF TOKEN ============
            csrf_token = get_token(request)
            
            # ============ GENERATE JWT ============
            refresh = RefreshToken.for_user(user)
            
            # ============ UPDATE DEVICE FINGERPRINT ============
            if device_fingerprint:
                user.device_fingerprint = device_fingerprint
                user.save(update_fields=['device_fingerprint'])
            
            # ============ LOG LOGIN ATTEMPT ============
            LoginAttempt.objects.create(
                user=user,
                identifier=identifier,
                ip_address=client_ip,
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            # ============ LOG USER ACTIVITY ============
            self._log_activity(
                user,
                'login',
                'User logged in from mobile app',
                request
            )
            
            logger.info(f"User {user.username} logged in successfully from {client_ip}")
            
            # Get user data
            user_data = UserSerializer(user).data
            
            return Response({
                'success': True,
                'message': f'Welcome back, {user.get_full_name() or user.username}!',
                'data': {
                    'user': user_data,
                    'session_id': request.session.session_key,
                    'csrf_token': csrf_token,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Login error for user {identifier}: {e}", exc_info=True)
            return Response({
                'success': False,
                'message': 'Login failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during login'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout user - destroys session and blacklists refresh token.
        """
        try:
            user = request.user
            refresh_token = request.data.get('refresh')
            
            # Blacklist refresh token if provided
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except Exception as e:
                    logger.warning(f"Failed to blacklist token: {e}")
            
            # Log logout activity
            self._log_activity(
                user,
                'logout',
                'User logged out',
                request
            )
            
            # Destroy session
            django_logout(request)
            
            logger.info(f"User {user.username} logged out successfully")
            
            return Response({
                'success': True,
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({
                'success': False,
                'message': 'Logout failed',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password"""
        try:
            serializer = ChangePasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            
            # Check old password
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'success': False,
                    'message': 'Wrong password',
                    'error': 'old_password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Log activity
            self._log_activity(
                user,
                'password_change',
                'User changed password',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return Response({
                'success': False,
                'message': 'Password change failed',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Request password reset"""
        try:
            serializer = ForgotPasswordSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            result = serializer.save()
            
            return Response({
                'success': True,
                'message': result.get('message', 'Password reset instructions sent to your email.'),
                'data': {
                    'email': result.get('email')
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to process password reset',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to reset password',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get current user profile"""
        try:
            return Response({
                'success': True,
                'message': 'Profile retrieved successfully',
                'data': {
                    'user': UserSerializer(request.user).data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user profile"""
        try:
            serializer = UserSerializer(
                request.user,
                data=request.data,
                partial=True
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = serializer.save()
            
            self._log_activity(
                user,
                'profile_update',
                'User updated profile',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {
                    'user': UserSerializer(user).data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to update profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def check_session(self, request):
        """Check if session is valid"""
        try:
            expiry_age = request.session.get_expiry_age()
            expiry_date = request.session.get_expiry_date()
            
            return Response({
                'success': True,
                'authenticated': True,
                'message': 'Session is valid',
                'data': {
                    'user': UserSerializer(request.user).data,
                    'session_id': request.session.session_key,
                    'session_expires_in_seconds': expiry_age,
                    'session_expires_in_hours': round(expiry_age / 3600, 1),
                    'session_expiry_date': expiry_date,
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'authenticated': False,
                'message': 'Session is invalid or expired',
                'error': str(e) if settings.DEBUG else 'Please login again'
            }, status=status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def csrf_token(self, request):
        """Get CSRF token for mobile app"""
        try:
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'CSRF token retrieved successfully',
                'data': {
                    'csrf_token': csrf_token
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"CSRF token error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get CSRF token',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_jwt(self, request):
        """Refresh JWT access token"""
        try:
            from rest_framework_simplejwt.views import TokenRefreshView
            return TokenRefreshView.as_view()(request)
            
        except Exception as e:
            logger.error(f"JWT refresh error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to refresh token',
                'error': str(e) if settings.DEBUG else 'Invalid refresh token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify user's email address"""
        try:
            serializer = VerifyEmailSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Email verified successfully. You can now login.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({
                'success': False,
                'message': 'Email verification failed',
                'error': str(e) if settings.DEBUG else 'Invalid or expired verification token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        """Resend verification email"""
        try:
            serializer = ResendVerificationSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Verification email sent successfully. Please check your inbox.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Resend verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to resend verification email',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        """Check if user's email is verified"""
        try:
            serializer = CheckVerificationStatusSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = serializer.to_representation(None)
            
            return Response({
                'success': True,
                'message': 'Verification status retrieved',
                'data': data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Check verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to check verification status',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AuthViewSetOld3(viewsets.GenericViewSet):
    """
    Authentication ViewSet supporting both Session and JWT authentication.
    - Session authentication for mobile app (cookies)
    - JWT authentication for API clients
    
    All responses follow a consistent format:
    {
        'success': True/False,
        'message': 'Human readable message',
        'data': {...} or 'error': 'Error message'
    }
    """
    permission_classes = [AllowAny]
    serializer_class = None

    def _get_client_ip(self, request):
        """
        Get client IP address from request headers.
        Handles cases where the app is behind a proxy (nginx/gunicorn).
        """
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

    def _create_session(self, request, user):
        """
        Create Django session for the user.
        Sets expiry to 72 hours.
        """
        django_login(request, user)
        request.session.set_expiry(60 * 60 * 72)  # 72 hours
        return request.session.session_key

    def _log_activity(self, user, activity_type, description, request):
        """Log user activity"""
        try:
            UserActivityLog.objects.create(
                user=user,
                activity_type=activity_type,
                description=description,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")

    @action(detail=False, methods=['post'])
    def register(self, request):
        """
        Register a new user.
        Creates both session and JWT tokens.
        """
        try:
            serializer = RegisterSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create user
            user = serializer.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Log registration
            self._log_activity(
                user, 
                'register', 
                f'User registered with ID: {user.id_number}',
                request
            )
            
            # Create session for the user
            session_id = self._create_session(request, user)
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'Registration successful! Please check your email to verify your account.',
                'data': {
                    'user': UserSerializer(user).data,
                    'csrf_token': csrf_token,
                    'session_id': session_id,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return Response({
                'success': False,
                'message': 'Registration failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during registration'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """
        Login user with ID Number, Email, or Phone Number.
        Creates both session and JWT tokens.
        """
        client_ip = self._get_client_ip(request)
        identifier = request.data.get('identifier', '').strip()
        password = request.data.get('password', '')
        device_fingerprint = request.data.get('device_fingerprint', '')
        
        # Validate input
        if not identifier or not password:
            return Response({
                'success': False,
                'message': 'Please provide identifier and password',
                'error': 'Missing credentials'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use LoginSerializer for validation
        serializer = LoginSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if not serializer.is_valid():
            # Log failed attempt
            LoginAttempt.objects.create(
                user=None,
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            return Response({
                'success': False,
                'message': 'Invalid credentials',
                'errors': serializer.errors
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated user
        user = serializer.validated_data['user']
        
        try:
            # Create session
            session_id = self._create_session(request, user)
            csrf_token = get_token(request)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Update device fingerprint if provided
            if device_fingerprint:
                user.device_fingerprint = device_fingerprint
                user.save(update_fields=['device_fingerprint'])
            
            # Log successful login
            LoginAttempt.objects.create(
                user=user,
                identifier=identifier,
                ip_address=client_ip,
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=device_fingerprint
            )
            
            # Log user activity
            self._log_activity(
                user,
                'login',
                'User logged in from mobile app',
                request
            )
            
            logger.info(f"User {user.username} logged in successfully from {client_ip}")
            
            # Get user data
            user_data = UserSerializer(user).data
            
            return Response({
                'success': True,
                'message': f'Welcome back, {user.get_full_name() or user.username}!',
                'data': {
                    'user': user_data,
                    'session_id': session_id,
                    'csrf_token': csrf_token,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Login error for user {identifier}: {e}")
            return Response({
                'success': False,
                'message': 'Login failed',
                'error': str(e) if settings.DEBUG else 'An error occurred during login'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @method_decorator(csrf_exempt)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout user - destroys session and blacklists refresh token.
        """
        try:
            user = request.user
            refresh_token = request.data.get('refresh')
            
            # Blacklist refresh token if provided
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except Exception as e:
                    logger.warning(f"Failed to blacklist token: {e}")
            
            # Log logout activity
            self._log_activity(
                user,
                'logout',
                'User logged out',
                request
            )
            
            # Get username before destroying session
            username = user.username
            
            # Destroy session
            django_logout(request)
            
            logger.info(f"User {username} logged out successfully")
            
            return Response({
                'success': True,
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({
                'success': False,
                'message': 'Logout failed',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Change user password.
        Requires old password and new password.
        """
        try:
            serializer = ChangePasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            
            # Check old password
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'success': False,
                    'message': 'Wrong password',
                    'error': 'old_password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Log activity
            self._log_activity(
                user,
                'password_change',
                'User changed password',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Password change error for user {request.user.username}: {e}")
            return Response({
                'success': False,
                'message': 'Password change failed',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """
        Request password reset using email, ID number, or phone number.
        Sends reset link to user's email.
        """
        try:
            serializer = ForgotPasswordSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Process forgot password
            result = serializer.save()
            
            return Response({
                'success': True,
                'message': result.get('message', 'Password reset instructions sent to your email.'),
                'data': {
                    'email': result.get('email')
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to process password reset',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """
        Reset password using token received in email.
        """
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Reset password
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to reset password',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """
        Get current user profile.
        """
        try:
            user_data = UserSerializer(request.user).data
            
            return Response({
                'success': True,
                'message': 'Profile retrieved successfully',
                'data': {
                    'user': user_data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile error for user {request.user.username}: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """
        Update current user profile.
        """
        try:
            serializer = UserSerializer(
                request.user,
                data=request.data,
                partial=True
            )
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Save updated profile
            user = serializer.save()
            
            # Log activity
            self._log_activity(
                user,
                'profile_update',
                'User updated profile',
                request
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {
                    'user': UserSerializer(user).data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Profile update error for user {request.user.username}: {e}")
            return Response({
                'success': False,
                'message': 'Failed to update profile',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def check_session(self, request):
        """
        Check if session is valid.
        Used by mobile app to verify session status.
        """
        try:
            expiry_age = request.session.get_expiry_age()
            expiry_date = request.session.get_expiry_date()
            
            return Response({
                'success': True,
                'authenticated': True,
                'message': 'Session is valid',
                'data': {
                    'user': UserSerializer(request.user).data,
                    'session_id': request.session.session_key,
                    'session_expires_in_seconds': expiry_age,
                    'session_expires_in_hours': round(expiry_age / 3600, 1),
                    'session_expiry_date': expiry_date,
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'authenticated': False,
                'message': 'Session is invalid or expired',
                'error': str(e) if settings.DEBUG else 'Please login again'
            }, status=status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def csrf_token(self, request):
        """
        Get CSRF token for mobile app.
        Useful for initializing the app before login.
        """
        try:
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'CSRF token retrieved successfully',
                'data': {
                    'csrf_token': csrf_token
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"CSRF token error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to get CSRF token',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_jwt(self, request):
        """
        Refresh JWT access token using refresh token.
        """
        try:
            from rest_framework_simplejwt.views import TokenRefreshView
            return TokenRefreshView.as_view()(request)
            
        except Exception as e:
            logger.error(f"JWT refresh error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to refresh token',
                'error': str(e) if settings.DEBUG else 'Invalid refresh token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """
        Verify user's email address using token or verification code.
        """
        try:
            serializer = VerifyEmailSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify email
            user = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Email verified successfully. You can now login.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({
                'success': False,
                'message': 'Email verification failed',
                'error': str(e) if settings.DEBUG else 'Invalid or expired verification token'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        """
        Resend verification email to user.
        """
        try:
            serializer = ResendVerificationSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Resend verification
            serializer.save()
            
            return Response({
                'success': True,
                'message': 'Verification email sent successfully. Please check your inbox.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Resend verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to resend verification email',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        """
        Check if user's email is verified.
        """
        try:
            serializer = CheckVerificationStatusSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get verification status
            data = serializer.to_representation(None)
            
            return Response({
                'success': True,
                'message': 'Verification status retrieved',
                'data': data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Check verification error: {e}")
            return Response({
                'success': False,
                'message': 'Failed to check verification status',
                'error': str(e) if settings.DEBUG else 'An error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AuthViewSetOld2(viewsets.GenericViewSet):
    """
    Authentication ViewSet supporting both Session and JWT authentication.
    - Session authentication for mobile app (cookies)
    - JWT authentication for API clients
    """
    permission_classes = [AllowAny]
    serializer_class = None

    def _get_client_ip(self, request):
        """
        Get client IP address from request headers.
        Handles cases where the app is behind a proxy (nginx/gunicorn).
        """
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

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            # Log registration
            UserActivityLog.objects.create(
                user=user,
                activity_type='register',
                description=f'User registered with ID: {user.id_number}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Create session for the new user
            django_login(request, user)
            request.session.set_expiry(60 * 60 * 72)  # 72 hours
            csrf_token = get_token(request)
            
            return Response({
                'success': True,
                'message': 'Registration successful! Please check your email to verify your account.',
                'user': UserSerializer(user).data,
                'csrf_token': csrf_token,
                'session_id': request.session.session_key,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(csrf_exempt)
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """
        Login user with ID Number, Email, or Phone Number.
        Creates both session and JWT tokens for maximum compatibility.
        """
        client_ip = self._get_client_ip(request)
        identifier = request.data.get('identifier')
        password = request.data.get('password')
        
        # Validate input
        if not identifier or not password:
            return Response({
                'success': False,
                'error': 'Please provide identifier and password'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use LoginSerializer for validation
        serializer = LoginSerializer(data=request.data, context={'request': request})
        
        if not serializer.is_valid():
            # Log failed attempt
            LoginAttempt.objects.create(
                user=None,
                identifier=identifier,
                ip_address=client_ip,
                success=False,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=request.data.get('device_fingerprint', '')
            )
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated user from serializer
        user = serializer.validated_data['user']
        
        # ============ SUCCESSFUL LOGIN ============
        
        # 1. Create Django session for mobile app
        django_login(request, user)
        request.session.set_expiry(60 * 60 * 72)  # 72 hours
        
        # 2. Get CSRF token for mobile app
        csrf_token = get_token(request)
        
        # 3. Generate JWT tokens for API clients
        refresh = RefreshToken.for_user(user)
        
        # 4. Update device fingerprint if provided
        if request.data.get('device_fingerprint'):
            user.device_fingerprint = request.data['device_fingerprint']
            user.save()
        
        # 5. Log successful login attempt
        LoginAttempt.objects.create(
            user=user,
            identifier=identifier,
            ip_address=client_ip,
            success=True,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            device_fingerprint=request.data.get('device_fingerprint', '')
        )
        
        # 6. Log user activity
        UserActivityLog.objects.create(
            user=user,
            activity_type='login',
            description=f'User logged in from mobile app',
            ip_address=client_ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # 7. Prepare user data
        user_data = UserSerializer(user).data
        
        logger.info(f"User {user.username} logged in successfully from {client_ip}")
        
        return Response({
            'success': True,
            'message': f'Welcome back, {user.get_full_name() or user.username}!',
            'user': user_data,
            # Session data (for mobile app)
            'session_id': request.session.session_key,
            'csrf_token': csrf_token,
            # JWT tokens (for API clients)
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)

    @method_decorator(csrf_exempt)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout user - destroys session and blacklists refresh token.
        """
        try:
            # Get refresh token if provided
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Log logout activity
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='logout',
                description='User logged out',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Destroy session
            django_logout(request)
            
            logger.info(f"User {request.user.username} logged out successfully")
            
            return Response({
                'success': True,
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            
            # Check old password
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'success': False,
                    'error': 'Wrong password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Log activity
            UserActivityLog.objects.create(
                user=user,
                activity_type='password_change',
                description='User changed password',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Request password reset using email, ID number, or phone number"""
        serializer = ForgotPasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                result = serializer.save()
                return Response({
                    'success': True,
                    'message': result.get('message', 'Password reset instructions sent to your email.'),
                    'email': result.get('email')
                }, status=status.HTTP_200_OK)
            except Exception as e:
                logger.error(f"Forgot password error: {e}")
                return Response({
                    'success': False,
                    'message': f'Error processing request: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Failed to reset password',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get current user profile"""
        user_data = UserSerializer(request.user).data
        return Response({
            'success': True,
            'user': user_data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user profile"""
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='profile_update',
                description='User updated profile',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'user': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def check_session(self, request):
        """
        Check if session is valid.
        Used by mobile app to verify session status.
        """
        try:
            expiry_age = request.session.get_expiry_age()
            expiry_date = request.session.get_expiry_date()
            
            return Response({
                'success': True,
                'authenticated': True,
                'user': UserSerializer(request.user).data,
                'session_id': request.session.session_key,
                'session_expires_in_seconds': expiry_age,
                'session_expires_in_hours': round(expiry_age / 3600, 1),
                'session_expiry_date': expiry_date,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'authenticated': False,
                'error': str(e)
            }, status=status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def csrf_token(self, request):
        """
        Get CSRF token for mobile app.
        Useful for initializing the app before login.
        """
        try:
            csrf_token = get_token(request)
            return Response({
                'success': True,
                'csrf_token': csrf_token
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_jwt(self, request):
        """
        Refresh JWT access token using refresh token.
        """
        from rest_framework_simplejwt.views import TokenRefreshView
        return TokenRefreshView.as_view()(request)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify user's email address"""
        serializer = VerifyEmailSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Email verified successfully. You can now login.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        """Resend verification email"""
        serializer = ResendVerificationSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Verification email sent successfully. Please check your inbox.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        """Check if user's email is verified"""
        serializer = CheckVerificationStatusSerializer(data=request.data)
        
        if serializer.is_valid():
            return Response({
                'success': True,
                'data': serializer.to_representation(None)
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class AuthViewSet(viewsets.GenericViewSet):
    """Authentication ViewSet for user registration, login, and password management"""    
    permission_classes = [AllowAny]
    serializer_class = None    

    def _get_client_ip(self, request):
        """
        Get client IP address from request headers.
        Handles cases where the app is behind a proxy (nginx/gunicorn).
        """
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

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            UserActivityLog.objects.create(
                user=user,
                activity_type='register',
                description=f'User registered with ID: {user.id_number}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': 'Registration successful!'
            }, status=status.HTTP_201_CREATED)
        
        errors = serializer.errors
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    
    @method_decorator(axes_dispatch)
    @action(detail=False, methods=['post'])
    def login(self, request):
        """Login user with ID Number, Email, or Phone Number"""
        client_ip = self._get_client_ip(request)
        
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            if request.data.get('device_fingerprint'):
                user.device_fingerprint = request.data['device_fingerprint']
                user.save()
            
            LoginAttempt.objects.create(
                user=user,
                identifier=request.data.get('identifier', ''),
                ip_address=client_ip,
                success=True,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                device_fingerprint=request.data.get('device_fingerprint', '')
            )
            
            UserActivityLog.objects.create(
                user=user,
                activity_type='login',
                description=f'User logged in',
                ip_address=client_ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': f'Welcome back, {user.get_full_name() or user.username}!'
            })
        
        LoginAttempt.objects.create(
            user=None,
            identifier=request.data.get('identifier', ''),
            ip_address=client_ip,
            success=False,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            device_fingerprint=request.data.get('device_fingerprint', '')
        )
        
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user by blacklisting refresh token"""
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='logout',
                description='User logged out',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'old_password': 'Wrong password.'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            UserActivityLog.objects.create(
                user=user,
                activity_type='password_change',
                description='User changed password',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'message': 'Password changed successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Request password reset using email, ID number, or phone number"""
        print(f"📝 Forgot password request data: {request.data}")
        
        # Create serializer with context
        serializer = ForgotPasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                result = serializer.save()
                return Response({
                    'success': True,
                    'message': result.get('message', 'Password reset instructions sent to your email.'),
                    'email': result.get('email')
                }, status=status.HTTP_200_OK)
            except Exception as e:
                print(f"❌ Error in forgot_password save: {e}")
                return Response({
                    'success': False,
                    'message': f'Error processing request: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            print(f"❌ Serializer errors: {serializer.errors}")
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Failed to reset password',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get current user profile"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user profile"""
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            UserActivityLog.objects.create(
                user=request.user,
                activity_type='profile_update',
                description='User updated profile',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AssetViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing and searching assets"""
    
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
            django_models.Q(id_number=user.id_number) |
            django_models.Q(passport_no=user.passport_no)
        )
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search for assets by identifier"""
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
            return Response({
                'count': assets.count(),
                'results': result_serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def location(self, request, pk=None):
        """Get asset location"""
        asset = self.get_object()
        location = AssetLocation.objects.filter(asset=asset).first()
        if location:
            serializer = AssetLocationSerializer(location)
            return Response(serializer.data)
        return Response({'message': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get asset tracking history"""
        asset = self.get_object()
        history = AssetTrackingHistory.objects.filter(asset=asset)
        serializer = AssetTrackingHistorySerializer(history, many=True)
        return Response(serializer.data)


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
        
        if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
            return Claim.objects.all()
        
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


class StaffClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for staff claim management"""
    
    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if not (self.request.user.is_staff or getattr(self.request.user, 'role', '') in ['staff', 'admin']):
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


class StaffAssetTrackerViewSet(viewsets.GenericViewSet):
    """ViewSet for staff asset tracking"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()
    
    def get_queryset(self):
        if not (self.request.user.is_staff or getattr(self.request.user, 'role', '') in ['staff', 'admin']):
            return Asset.objects.none()
        return Asset.objects.all()
    
    @action(detail=False, methods=['post'])
    def search_assets(self, request):
        """Search for assets by staff"""
        search_term = request.data.get('search_term', '')
        assets = Asset.objects.filter(
            django_models.Q(name__icontains=search_term) |
            django_models.Q(holder_name__icontains=search_term) |
            django_models.Q(asset_no__icontains=search_term) |
            django_models.Q(id_number__icontains=search_term)
        )
        serializer = AssetSerializer(assets, many=True)
        return Response({
            'count': assets.count(),
            'results': serializer.data
        })
    
    @action(detail=True, methods=['patch'])
    def update_location(self, request, pk=None):
        """Update asset location"""
        asset = self.get_object()
        serializer = AssetLocationUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            asset.location_source = request.data.get('location_source', asset.location_source)
            asset.physical_address = request.data.get('address', asset.physical_address)
            asset.latitude = request.data.get('latitude', asset.latitude)
            asset.longitude = request.data.get('longitude', asset.longitude)
            asset.status = request.data.get('status', asset.status)
            asset.save()
            
            location, created = AssetLocation.objects.update_or_create(
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
                }
            )
            
            AssetTrackingHistory.objects.create(
                asset=asset,
                previous_status=asset.status,
                new_status=request.data.get('status', asset.status),
                notes=request.data.get('notes', ''),
                updated_by=request.user,
                location=request.data.get('address', ''),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude')
            )
            
            return Response({
                'message': 'Asset location updated successfully',
                'asset_no': asset.asset_no,
                'status': asset.status,
                'location': {
                    'latitude': str(asset.latitude) if asset.latitude else None,
                    'longitude': str(asset.longitude) if asset.longitude else None,
                    'address': asset.physical_address,
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending_assets(self, request):
        """Get assets pending location verification"""
        assets = Asset.objects.filter(status='pending')
        serializer = AssetSerializer(assets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get asset tracking statistics"""
        stats = {
            'total_assets': Asset.objects.count(),
            'pending_verification': Asset.objects.filter(status='pending').count(),
            'verified_found': Asset.objects.filter(status='found').count(),
            'verified_not_found': Asset.objects.filter(status='not_found').count(),
            'transferred': Asset.objects.filter(status='transferred').count(),
        }
        return Response(stats)


class InitiateECitizenLoginView(APIView):
    """Returns the eCitizen authorization URL for the mobile app"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        auth_url = request.build_absolute_uri(reverse('oidc_authentication'))
        auth_url += f'?next=/api/auth/ecitizen/callback/&fail=/api/auth/ecitizen/fail/'
        
        return Response({
            'authorization_url': auth_url,
            'redirect_scheme': 'ufaareunite://callback'
        })


class ECitizenCallbackView(APIView):
    """Handles the OIDC callback after successful authentication"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        if request.user.is_authenticated:
            from rest_framework_simplejwt.tokens import RefreshToken
            
            refresh = RefreshToken.for_user(request.user)
            
            return Response({
                'success': True,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'email': request.user.email,
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'id_number': getattr(request.user, 'id_number', ''),
                    'phone_no': getattr(request.user, 'phone_no', ''),
                }
            })
        return Response({'success': False, 'error': 'Authentication failed'}, status=401)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification(request):
    """Resend verification email"""
    serializer = ResendVerificationSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        return Response({
            'success': True,
            'message': 'Verification email sent successfully. Please check your inbox.'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def verify_email(request):
    """Verify user's email address - handles both email link (GET) and API (POST) requests"""
    
    # Handle GET request (from email verification link)
    if request.method == 'GET':
        token = request.GET.get('token')
        email = request.GET.get('email')
        
        # Check for required parameters
        if not email:
            if settings.DEBUG:
                return HttpResponse("""
                    <html>
                    <body>
                        <h1>Verification Failed</h1>
                        <p>Email parameter is missing from verification link.</p>
                    </body>
                    </html>
                """, status=400)
            return redirect(f"{settings.FRONTEND_URL}/email-verification?success=false&error=missing_email")
        
        # For GET requests, we need token
        if not token:
            if settings.DEBUG:
                return HttpResponse("""
                    <html>
                    <body>
                        <h1>Verification Failed</h1>
                        <p>Token parameter is missing from verification link.</p>
                    </body>
                    </html>
                """, status=400)
            return redirect(f"{settings.FRONTEND_URL}/email-verification?success=false&error=missing_token")
        
        # Prepare data for serializer
        data = {
            'email': email,
            'token': token,
            'verification_code': ''  # Empty since we're using token
        }
        
        serializer = VerifyEmailSerializer(data=data)
        
        if serializer.is_valid():
            try:
                # Save will mark user as verified
                serializer.save()
                
                # Success - redirect to frontend success page
                if settings.DEBUG:
                    return HttpResponse("""
                        <html>
                        <body>
                            <h1>✓ Email Verified Successfully!</h1>
                            <p>Your email has been verified. You can now close this window and login to the app.</p>
                            <script>
                                setTimeout(function() {
                                    window.close();
                                }, 3000);
                            </script>
                        </body>
                        </html>
                    """)
                return redirect(f"{settings.FRONTEND_URL}/email-verification?success=true")
                
            except Exception as e:
                if settings.DEBUG:
                    return HttpResponse(f"""
                        <html>
                        <body>
                            <h1>Verification Error</h1>
                            <p>An error occurred: {str(e)}</p>
                        </body>
                        </html>
                    """, status=400)
                return redirect(f"{settings.FRONTEND_URL}/email-verification?success=false&error=verification_failed")
        else:
            # Validation failed
            error_message = ""
            if 'email' in serializer.errors:
                error_message = serializer.errors['email'][0]
            elif 'non_field_errors' in serializer.errors:
                error_message = serializer.errors['non_field_errors'][0]
            else:
                error_message = "Invalid or expired verification token"
            
            if settings.DEBUG:
                return HttpResponse(f"""
                    <html>
                    <body>
                        <h1>Verification Failed</h1>
                        <p>{error_message}</p>
                        <p>Details: {serializer.errors}</p>
                    </body>
                    </html>
                """, status=400)
            return redirect(f"{settings.FRONTEND_URL}/email-verification?success=false&error={error_message}")
    
    # Handle POST request (from mobile app API)
    elif request.method == 'POST':
        serializer = VerifyEmailSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Email verified successfully. You can now login.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)





@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email_old(request):
    """Verify user's email address"""
    serializer = VerifyEmailSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        return Response({
            'success': True,
            'message': 'Email verified successfully. You can now login.'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def check_verification_status(request):
    """Check if user's email is verified"""
    serializer = CheckVerificationStatusSerializer(data=request.data)
    
    if serializer.is_valid():
        return Response({
            'success': True,
            'data': serializer.to_representation(None)
        }, status=status.HTTP_200_OK)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)





@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_claim_document(request, claim_id):
    """Upload a document for a claim"""
    try:
        from apps.claims.models import Claim, ClaimDocument
        
        claim = Claim.objects.get(id=claim_id)
        
        # Check if user owns the claim
        if claim.claimant != request.user:
            if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                return Response(
                    {'error': 'You do not have permission to upload documents for this claim.'},
                    status=status.HTTP_403_FORBIDDEN
                )
    except Claim.DoesNotExist:
        return Response(
            {'error': 'Claim not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    file = request.FILES.get('file')
    document_type = request.data.get('document_type', 'other')
    document_name = request.data.get('document_name', file.name if file else '')
    
    if not file:
        return Response(
            {'error': 'No file provided.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create document record
    document = ClaimDocument.objects.create(
        claim=claim,
        document_type=document_type,
        document_name=document_name,
        file_path=f"documents/{claim.no}/{file.name}",
        file_size=file.size,
        file_extension=file.name.split('.')[-1] if '.' in file.name else '',
        uploaded_by=request.user
    )
    
    return Response({
        'success': True,
        'message': 'Document uploaded successfully',
        'document': {
            'id': document.id,
            'document_type': document.document_type,
            'document_name': document.document_name,
            'uploaded_at': document.uploaded_at,
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_documents(request, claim_id):
    """Get all documents for a claim"""
    try:
        from apps.claims.models import Claim
        
        claim = Claim.objects.get(id=claim_id)
        
        # Check if user owns the claim
        if claim.claimant != request.user:
            if not (request.user.is_staff or getattr(request.user, 'role', '') in ['staff', 'admin']):
                return Response(
                    {'error': 'You do not have permission to view documents for this claim.'},
                    status=status.HTTP_403_FORBIDDEN
                )
    except Claim.DoesNotExist:
        return Response(
            {'error': 'Claim not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    documents = claim.documents.all()
    data = []
    for doc in documents:
        data.append({
            'id': doc.id,
            'document_type': doc.document_type,
            'document_name': doc.document_name,
            'file_path': doc.file_path,
            'file_size': doc.file_size,
            'uploaded_at': doc.uploaded_at,
            'is_verified': doc.is_verified,
        })
    
    return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def test_forgot_password(request):
    """Test endpoint for forgot password"""
    print(f"Test endpoint received data: {request.data}")
    
    identifier = request.data.get('identifier')
    if not identifier:
        return Response({'error': 'No identifier provided'}, status=400)
    
    user = None
    
    # Check if identifier is email
    if '@' in identifier:
        try:
            user = User.objects.get(email=identifier)
            print(f"Found user by email: {user.email}")
        except User.DoesNotExist:
            print(f"No user found with email: {identifier}")
    
    # Check if identifier is ID number
    if not user and identifier.isdigit() and len(identifier) in [7, 8]:
        try:
            user = User.objects.get(id_number=identifier)
            print(f"Found user by ID number: {user.id_number}")
        except User.DoesNotExist:
            print(f"No user found with ID number: {identifier}")
    
    # Check if identifier is phone number
    if not user:
        try:
            # Clean phone number
            import re
            clean_phone = re.sub(r'[\s\-\(\)]', '', identifier)
            if clean_phone.startswith('0'):
                clean_phone = '254' + clean_phone[1:]
            elif clean_phone.startswith('7'):
                clean_phone = '254' + clean_phone
            elif clean_phone.startswith('+254'):
                clean_phone = clean_phone[1:]
            
            user = User.objects.get(phone_no__contains=clean_phone[-9:])
            print(f"Found user by phone: {user.phone_no}")
        except User.DoesNotExist:
            print(f"No user found with phone: {identifier}")
    
    if not user:
        return Response({
            'error': f'No user found with identifier: {identifier}'
        }, status=404)
    
    return Response({
        'success': True,
        'message': f'Found user: {user.email}',
        'email': user.email,
        'id_number': user.id_number,
        'phone_no': user.phone_no
    }, status=200)
