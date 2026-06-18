# apps/api/exceptions.py - Update this file

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that always returns JSON responses.
    This prevents HTML error pages from being sent to mobile apps.
    """
    
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Ensure we have a dict response
        if not isinstance(response.data, dict):
            return Response(
                {
                    'success': False,
                    'error': str(response.data),
                    'detail': 'An error occurred'
                },
                status=response.status_code
            )
        
        # Standardize the response format
        error_data = {
            'success': False,
            'error': response.data.get('detail', response.data.get('error', 'An error occurred')),
            'detail': response.data.get('detail', ''),
        }
        
        # Include status code in response
        error_data['status_code'] = response.status_code
        
        return Response(error_data, status=response.status_code)
    
    # Handle Django's Http404 (Not Found)
    if isinstance(exc, Http404):
        return Response(
            {
                'success': False,
                'error': 'Resource not found',
                'detail': 'The requested resource does not exist',
                'status_code': 404
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Handle PermissionDenied (403)
    if isinstance(exc, PermissionDenied):
        return Response(
            {
                'success': False,
                'error': 'Permission denied',
                'detail': 'You do not have permission to perform this action',
                'status_code': 403
            },
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Handle CSRF errors
    if 'CSRF' in str(exc):
        return Response(
            {
                'success': False,
                'error': 'CSRF validation failed',
                'detail': 'CSRF token missing or invalid. Please refresh and try again.',
                'status_code': 403
            },
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Handle Authentication errors
    if 'Authentication' in str(exc) or 'authenticated' in str(exc).lower():
        return Response(
            {
                'success': False,
                'error': 'Authentication required',
                'detail': 'Please login to continue',
                'status_code': 401
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Log unexpected errors
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    from django.conf import settings
    error_detail = str(exc) if settings.DEBUG else 'An unexpected error occurred. Please try again later.'
    
    return Response(
        {
            'success': False,
            'error': 'Internal server error',
            'detail': error_detail,
            'status_code': 500
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
