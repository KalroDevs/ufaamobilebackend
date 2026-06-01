# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

from apps.api.views import (
    resend_verification,
    verify_email,
    check_verification_status
)

from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView

from django.views.generic import TemplateView
from apps.oidc.views import (
    InitiateECitizenLoginView, 
    ECitizenCallbackView, 
    ECitizenFailView,
    TestDeepLinkView,
    CallbackHtmlView
)

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'staff/assets', StaffAssetTrackerViewSet, basename='staff-asset')

urlpatterns = [
    path('', include(router.urls)),
    
    # eCitizen OIDC endpoints
    path('auth/oidc/authenticate/', InitiateECitizenLoginView.as_view(), name='oidc_authentication'),
    path('auth/oidc/callback/', ECitizenCallbackView.as_view(), name='oidc_callback'),
    path('auth/oidc/fail/', ECitizenFailView.as_view(), name='ecitizen_fail'),
    path('auth/oidc/test/', TestDeepLinkView.as_view(), name='oidc_test'),
    path('auth/oidc/callback.html/', CallbackHtmlView.as_view(), name='callback_html'),
    path('.well-known/assetlinks.json', 
         TemplateView.as_view(template_name='assetlinks.json', content_type='application/json'),
         name='assetlinks'),


    path('auth/resend-verification/', resend_verification, name='resend_verification'),
    path('auth/verify-email/', verify_email, name='verify_email'),
    path('auth/check-verification/', check_verification_status, name='check_verification_status'),


    # JWT Token endpoints
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),


]
