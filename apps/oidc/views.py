# apps/oidc/views.py
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import login
from django.views.generic import View
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
import requests
import secrets
from urllib.parse import urlencode

class InitiateECitizenLoginView(View):
    """Initiate eCitizen OAuth2 login"""
    
    def get(self, request):
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)
        request.session['oauth_state'] = state
        
        # Build authorization URL
        params = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'redirect_uri': request.build_absolute_uri(reverse('oidc_callback')),
            'response_type': 'code',
            'scope': settings.OIDC_RP_SCOPES,
            'state': state,
        }
        
        # Add PKCE parameters if enabled
        if getattr(settings, 'OIDC_RP_USE_PKCE', True):
            code_verifier = secrets.token_urlsafe(64)
            request.session['code_verifier'] = code_verifier
            params['code_challenge'] = self._generate_code_challenge(code_verifier)
            params['code_challenge_method'] = 'S256'
        
        auth_url = f"{settings.OIDC_OP_AUTHORIZATION_URL}?{urlencode(params)}"
        return redirect(auth_url)
    
    def _generate_code_challenge(self, code_verifier):
        import hashlib
        import base64
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')

class ECitizenCallbackView(View):
    """Handle eCitizen OAuth2 callback"""
    
    def get(self, request):
        # Verify state parameter
        stored_state = request.session.get('oauth_state')
        received_state = request.GET.get('state')
        
        if not stored_state or stored_state != received_state:
            return redirect('/api/auth/ecitizen/fail/?error=invalid_state')
        
        # Get authorization code
        code = request.GET.get('code')
        if not code:
            return redirect('/api/auth/ecitizen/fail/?error=no_code')
        
        # Exchange code for tokens
        token_data = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'client_secret': settings.OIDC_RP_CLIENT_SECRET,
            'code': code,
            'redirect_uri': request.build_absolute_uri(reverse('oidc_callback')),
            'grant_type': 'authorization_code',
        }
        
        # Add PKCE verifier if used
        if getattr(settings, 'OIDC_RP_USE_PKCE', True):
            token_data['code_verifier'] = request.session.get('code_verifier')
        
        try:
            # Call eCitizen token endpoint
            token_response = requests.post(
                settings.OIDC_OP_TOKEN_URL,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            
            if token_response.status_code != 200:
                return redirect(f"/api/auth/ecitizen/fail/?error=token_exchange_failed&status={token_response.status_code}")
            
            tokens = token_response.json()
            
            # Get user info from eCitizen
            userinfo_response = requests.get(
                settings.OIDC_OP_USERINFO_URL,
                headers={'Authorization': f"Bearer {tokens['access_token']}"},
                timeout=30
            )
            
            if userinfo_response.status_code != 200:
                return redirect('/api/auth/ecitizen/fail/?error=userinfo_failed')
            
            userinfo = userinfo_response.json()
            
            # Create or update user in your database
            from django.contrib.auth import get_user_model
            from rest_framework_simplejwt.tokens import RefreshToken
            
            User = get_user_model()
            
            # Map eCitizen user info to your User model
            user, created = User.objects.get_or_create(
                username=userinfo.get('id_number', userinfo.get('email', '')),
                defaults={
                    'email': userinfo.get('email', ''),
                    'first_name': userinfo.get('given_name', ''),
                    'last_name': userinfo.get('family_name', ''),
                    'id_number': userinfo.get('id_number', ''),
                    'phone_no': userinfo.get('phone_number', ''),
                }
            )
            
            if not created:
                # Update existing user
                user.email = userinfo.get('email', user.email)
                user.first_name = userinfo.get('given_name', user.first_name)
                user.last_name = userinfo.get('family_name', user.last_name)
                user.save()
            
            # Log the user in
            login(request, user)
            
            # Generate JWT tokens for mobile app
            refresh = RefreshToken.for_user(user)
            
            # Build success URL for mobile app
            success_data = {
                'success': 'true',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
            
            # Encode data for mobile app
            encoded_data = urlencode(success_data)
            
            # Redirect to mobile app deep link
            return redirect(f"ufaareunite://callback?{encoded_data}")
            
        except Exception as e:
            return redirect(f"/api/auth/ecitizen/fail/?error={str(e)}")

class ECitizenFailView(View):
    """Handle eCitizen authentication failure"""
    
    def get(self, request):
        error = request.GET.get('error', 'unknown_error')
        return redirect(f"ufaareunite://callback?success=false&error={error}")
