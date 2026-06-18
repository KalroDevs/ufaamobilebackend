# apps/api/middleware.py - Create this file

import json
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger(__name__)


class APIJSONMiddleware(MiddlewareMixin):
    """
    Middleware to ensure all API endpoints return JSON responses.
    Converts HTML error pages to JSON for mobile apps.
    """
    
    def process_response(self, request, response):
        # Only process API endpoints
        if request.path.startswith('/api/'):
            content_type = response.get('Content-Type', '')
            
            # Check if response is HTML
            if 'text/html' in content_type or '<!DOCTYPE html>' in str(response.content)[:100]:
                try:
                    content = response.content.decode('utf-8')
                    
                    # Check if it's an HTML error page
                    if '<!DOCTYPE html>' in content or '<html' in content:
                        logger.warning(f"API endpoint {request.path} returned HTML. Status: {response.status_code}")
                        
                        # Determine error type from status and content
                        error_message = 'Invalid response from server'
                        status_code = response.status_code
                        
                        if 'CSRF' in content:
                            error_message = 'CSRF validation failed'
                            status_code = 403
                        elif '404' in content or 'Page not found' in content:
                            error_message = 'Endpoint not found'
                            status_code = 404
                        elif '403' in content or 'Forbidden' in content:
                            error_message = 'Access forbidden'
                            status_code = 403
                        elif '500' in content or 'Server Error' in content:
                            error_message = 'Internal server error'
                            status_code = 500
                        elif '401' in content or 'Unauthorized' in content:
                            error_message = 'Authentication required'
                            status_code = 401
                        elif 'Method Not Allowed' in content:
                            error_message = 'Method not allowed'
                            status_code = 405
                        
                        return JsonResponse({
                            'success': False,
                            'error': error_message,
                            'detail': 'The server returned HTML instead of JSON.',
                            'status_code': status_code
                        }, status=status_code)
                        
                except Exception as e:
                    logger.error(f"Error processing response: {e}")
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid response format',
                        'detail': str(e)
                    }, status=500)
        
        return response
    
    def process_exception(self, request, exception):
        """Handle exceptions and return JSON"""
        if request.path.startswith('/api/'):
            logger.error(f"API exception: {exception}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Internal server error',
                'detail': str(exception) if settings.DEBUG else 'An unexpected error occurred'
            }, status=500)
        return None
