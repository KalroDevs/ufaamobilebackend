# apps/api/urls.py (Alternative - Organized by functionality)

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from apps.api.views import (
    resend_verification,
    verify_email,
    check_verification_status,
    upload_claim_document,
    get_claim_documents,
    test_forgot_password,
)
from apps.claims.views import (
    download_document_by_id, 
    view_document_by_id,
    ClaimViewSet,
    ClaimViewSetDeleteView,
    StaffClaimViewSet
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

# Create routers
router = DefaultRouter()

# API Viewsets
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'staff/assets', StaffAssetTrackerViewSet, basename='staff-asset')

# Claims Viewsets
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'claims-delete', ClaimViewSetDeleteView, basename='claim-delete')
router.register(r'staff/claims', StaffClaimViewSet, basename='staff-claim')

urlpatterns = [
    # API root
    path('', include(router.urls)),
    
    # ============================================================
    # AUTHENTICATION ENDPOINTS
    # ============================================================
    
    # JWT Authentication
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Email Verification
    path('auth/verify-email/', verify_email, name='verify_email'),
    path('auth/resend-verification/', resend_verification, name='resend_verification'),
    path('auth/check-verification/', check_verification_status, name='check_verification_status'),
    
    # Password Management
    path('auth/forgot-password/', AuthViewSet.as_view({'post': 'forgot_password'}), name='forgot_password'),
    path('auth/reset-password/', AuthViewSet.as_view({'post': 'reset_password'}), name='reset_password'),
    path('auth/test/forgot-password/', test_forgot_password, name='test_forgot_password'),  # Remove in production
    
    # ============================================================
    # ECITIZEN OIDC ENDPOINTS
    # ============================================================
    path('auth/oidc/authenticate/', InitiateECitizenLoginView.as_view(), name='oidc_authentication'),
    path('auth/oidc/callback/', ECitizenCallbackView.as_view(), name='oidc_callback'),
    path('auth/oidc/fail/', ECitizenFailView.as_view(), name='ecitizen_fail'),
    path('auth/oidc/test/', TestDeepLinkView.as_view(), name='oidc_test'),
    path('auth/oidc/callback.html/', CallbackHtmlView.as_view(), name='callback_html'),
    path('.well-known/assetlinks.json', 
         TemplateView.as_view(template_name='assetlinks.json', content_type='application/json'),
         name='assetlinks'),
    
    # ============================================================
    # DOCUMENT MANAGEMENT ENDPOINTS
    # ============================================================
    
    # Claim-specific document operations (legacy, kept for compatibility)
    path('claims/<int:claim_id>/documents/upload/', upload_claim_document, name='upload_claim_document'),
    path('claims/<int:claim_id>/documents/', get_claim_documents, name='get_claim_documents'),
    
    # Standalone document access by ID (primary endpoints)
    # These URLs are used in admin.py and provide direct document access
    path('documents/<int:document_id>/', view_document_by_id, name='view_document_by_id'),
    path('documents/<int:document_id>/download/', download_document_by_id, name='download_document'),
    path('documents/<int:document_id>/view/', view_document_by_id, name='view_document'),
    
    # Alternative short URLs for convenience
    path('docs/<int:document_id>/', view_document_by_id, name='doc_view'),
    path('docs/<int:document_id>/download/', download_document_by_id, name='doc_download'),
]

# ============================================================
# STATIC AND MEDIA FILE SERVING (Development Only)
# ============================================================
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Optional: Add debug toolbar if installed
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
