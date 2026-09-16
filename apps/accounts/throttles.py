# apps/accounts/throttles.py
from rest_framework.throttling import SimpleRateThrottle

class LoginAttemptThrottle(SimpleRateThrottle):
    scope = 'login_attempt'
    
    def get_cache_key(self, request, view):
        identifier = request.data.get('identifier', '')
        return self.cache_format % {
            'scope': self.scope,
            'ident': identifier
        }
    
    def allow_request(self, request, view):
        # Allow only 5 login attempts per hour per identifier
        return super().allow_request(request, view)