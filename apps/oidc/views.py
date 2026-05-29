# apps/oidc/views.py
import hashlib
import base64
import secrets
import requests
from urllib.parse import urlencode
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import login
from django.views.generic import View
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework_simplejwt.tokens import RefreshToken
from django.views.generic import TemplateView

class InitiateECitizenLoginView(View):
    """Initiate eCitizen OAuth2 login with PKCE (required for API v2.0.0)"""
    
    def get(self, request):
        # Generate code verifier and challenge for PKCE (required by eCitizen)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = self._generate_code_challenge(code_verifier)
        
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Store in session for callback verification
        request.session['code_verifier'] = code_verifier
        request.session['oauth_state'] = state
        
        # Build authorization URL according to eCitizen API v2.0.0
        params = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'redirect_uri': request.build_absolute_uri(reverse('oidc_callback')),
            'response_type': 'code',
            'scope': settings.OIDC_RP_SCOPES,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',  # Required by eCitizen
        }
        
        auth_url = f"{settings.OIDC_OP_AUTHORIZATION_URL}?{urlencode(params)}"
        print(f"🔐 Redirecting to eCitizen: {auth_url}")
        return redirect(auth_url)
    
    def _generate_code_challenge(self, code_verifier):
        """Generate code challenge using S256 method as per eCitizen API v2.0.0"""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')


class ECitizenCallbackView(View):
    """Handle eCitizen OAuth2 callback with PKCE verification"""
    
    def get(self, request):
        print(f"📱 eCitizen callback received: {request.GET}")
        
        # Verify state parameter to prevent CSRF
        stored_state = request.session.get('oauth_state')
        received_state = request.GET.get('state')
        
        if not stored_state or stored_state != received_state:
            print(f"❌ State mismatch: stored={stored_state}, received={received_state}")
            return redirect('/api/auth/oidc/fail/?error=invalid_state')
        
        # Check for error response from eCitizen
        error = request.GET.get('error')
        if error:
            error_desc = request.GET.get('error_description', '')
            print(f"❌ eCitizen error: {error} - {error_desc}")
            return redirect(f'/api/auth/oidc/fail/?error={error}&error_description={error_desc}')
        
        # Get authorization code
        code = request.GET.get('code')
        if not code:
            print("❌ No authorization code received")
            return redirect('/api/auth/oidc/fail/?error=no_code')
        
        print(f"✅ Authorization code received: {code[:20]}...")
        
        # Exchange code for tokens using PKCE
        token_data = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'client_secret': settings.OIDC_RP_CLIENT_SECRET,
            'code': code,
            'redirect_uri': request.build_absolute_uri(reverse('oidc_callback')),
            'grant_type': 'authorization_code',
            'code_verifier': request.session.get('code_verifier'),  # Required for PKCE
        }
        
        try:
            # Exchange authorization code for access token
            print("🔄 Exchanging code for access token...")
            token_response = requests.post(
                settings.OIDC_OP_TOKEN_URL,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            print(f"📥 Token response status: {token_response.status_code}")
            
            if token_response.status_code != 200:
                print(f"❌ Token exchange failed: {token_response.text}")
                return redirect(f'/api/auth/oidc/fail/?error=token_exchange_failed')
            
            token_data_response = token_response.json()
            access_token = token_data_response.get('access_token')
            
            if not access_token:
                print("❌ No access token in response")
                return redirect('/api/auth/oidc/fail/?error=no_access_token')
            
            print("✅ Access token received")
            
            # Fetch user information from eCitizen
            print("🔄 Fetching user info from eCitizen...")
            user_info_response = requests.get(
                settings.OIDC_OP_USERINFO_URL,
                params={'access_token': access_token}
            )
            
            if user_info_response.status_code != 200:
                print(f"❌ User info fetch failed: {user_info_response.status_code}")
                return redirect('/api/auth/oidc/fail/?error=user_info_failed')
            
            user_info = user_info_response.json()
            print(f"✅ User info received: {user_info.get('email', 'No email')}")
            
            # Create or update user in your system
            user = self._get_or_create_user(user_info)
            
            # Log the user into Django session
            login(request, user)
            
            # Generate JWT tokens for mobile app
            refresh = RefreshToken.for_user(user)
            
            # Prepare data for mobile app deep link
            success_data = {
                'success': 'true',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'id_number': user_info.get('id_number', ''),
                'phone_number': user_info.get('mobile_number', ''),
                'kra_pin': user_info.get('Kra_pin_number', ''),
            }
            
            # Clear session data
            request.session.pop('code_verifier', None)
            request.session.pop('oauth_state', None)
            
            # Encode the data
            encoded_data = urlencode(success_data)
            
            # Use intent:// scheme for Android (more reliable than custom schemes)
            package_name = "com.ufaa.ereunify_mobile"
            intent_url = f"intent://callback?{encoded_data}#Intent;scheme=ufaareunite;package={package_name};end"
            
            print(f"🔗 Redirecting via intent: {intent_url}")
            
            # Return HTML page with multiple fallback methods
            html_content = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Redirecting to UFAA Reunite...</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #262561 0%, #1a1a4f 100%);
                        color: white;
                        text-align: center;
                    }}
                    .container {{
                        padding: 20px;
                    }}
                    .spinner {{
                        width: 50px;
                        height: 50px;
                        border: 4px solid rgba(255,255,255,0.3);
                        border-radius: 50%;
                        border-top-color: #E4B355;
                        animation: spin 1s ease-in-out infinite;
                        margin: 20px auto;
                    }}
                    @keyframes spin {{
                        to {{ transform: rotate(360deg); }}
                    }}
                    .button {{
                        display: inline-block;
                        margin-top: 20px;
                        padding: 12px 24px;
                        background-color: #E4B355;
                        color: #262561;
                        text-decoration: none;
                        border-radius: 8px;
                        font-weight: bold;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>UFAA Reunite</h2>
                    <div class="spinner"></div>
                    <p>Redirecting you back to the app...</p>
                    <a href="{intent_url}" class="button">Open UFAA Reunite App</a>
                </div>
                <script>
                    // Try multiple methods to open the app
                    setTimeout(function() {{
                        window.location.href = "{intent_url}";
                    }}, 100);
                    
                    // Also try iframe method
                    var iframe = document.createElement('iframe');
                    iframe.style.display = 'none';
                    iframe.src = "{intent_url}";
                    document.body.appendChild(iframe);
                    
                    // Fallback to show button if app doesn't open
                    setTimeout(function() {{
                        document.querySelector('.button').style.display = 'inline-block';
                    }}, 2000);
                </script>
            </body>
            </html>
            '''
            
            return HttpResponse(html_content, content_type='text/html')
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Request exception: {e}")
            return redirect(f'/api/auth/oidc/fail/?error=network_error')
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return redirect(f'/api/auth/oidc/fail/?error={str(e)}')
    
    def _get_or_create_user(self, user_info):
        """Get or create user from eCitizen user info"""
        id_number = user_info.get('id_number')
        email = user_info.get('email')
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        mobile_number = user_info.get('mobile_number', '')
        kra_pin = user_info.get('Kra_pin_number', '')
        
        # Try to find existing user by email
        user = None
        if email:
            try:
                user = User.objects.get(email=email)
                print(f"✅ Found existing user by email: {email}")
            except User.DoesNotExist:
                pass
        
        # If not found by email, try by username (using ID number)
        if not user and id_number:
            username = f"ecitizen_{id_number}"
            try:
                user = User.objects.get(username=username)
                print(f"✅ Found existing user by username: {username}")
            except User.DoesNotExist:
                pass
        
        # Create new user if not found
        if not user:
            username = id_number if id_number else email.split('@')[0] if email else mobile_number
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1
            
            # Create new user
            user = User.objects.create_user(
                username=username,
                email=email or '',
                first_name=first_name,
                last_name=last_name,
            )
            print(f"✅ Created new user: {username}")
            
            # Create user profile if UserProfile model exists
            try:
                from your_app.models import UserProfile
                UserProfile.objects.create(
                    user=user,
                    id_number=id_number,
                    phone_number=mobile_number,
                    kra_pin=kra_pin,
                )
                print("✅ User profile created")
            except ImportError:
                print("⚠️ UserProfile model not found, skipping profile creation")
        
        return user


class ECitizenFailView(View):
    """Handle eCitizen authentication failure"""
    
    def get(self, request):
        error = request.GET.get('error', 'unknown_error')
        error_desc = request.GET.get('error_description', '')
        
        print(f"❌ eCitizen failure: {error} - {error_desc}")
        
        # Clean session data
        request.session.pop('code_verifier', None)
        request.session.pop('oauth_state', None)
        
        # Redirect to mobile app with error via intent
        error_data = {
            'success': 'false',
            'error': error,
            'error_description': error_desc,
        }
        encoded_data = urlencode(error_data)
        package_name = "com.ufaa.ereunify_mobile"
        intent_url = f"intent://callback?{encoded_data}#Intent;scheme=ufaareunite;package={package_name};end"
        
        return redirect(intent_url)


class TestDeepLinkView(View):
    """Test view to verify deep link functionality"""
    
    def get(self, request):
        test_data = {
            'success': 'true',
            'access': 'test_access_token_12345',
            'refresh': 'test_refresh_token_67890',
            'user_id': '1',
            'username': 'test_user',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'id_number': '12345678',
            'phone_number': '254700000000',
        }
        encoded_data = urlencode(test_data)
        package_name = "com.ufaa.ereunify_mobile"
        intent_url = f"intent://callback?{encoded_data}#Intent;scheme=ufaareunite;package={package_name};end"
        
        # Return HTML page with the intent
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Deep Link</title>
            <meta http-equiv="refresh" content="0; url={intent_url}">
        </head>
        <body>
            <p>Redirecting to app...</p>
            <a href="{intent_url}">Click here if not redirected</a>
        </body>
        </html>
        '''
        return HttpResponse(html_content, content_type='text/html')



class CallbackHtmlView(TemplateView):
    """Serve the callback HTML page for deep link redirection"""
    template_name = 'callback.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the query parameters to the template
        context['params'] = self.request.GET.urlencode()
        return context
