from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.views import TokenRefreshView

from apps.api.views import AuthViewSet, AssetViewSet, ClaimViewSet, StaffAssetTrackerViewSet



# Create router with basenames
router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'staff/assets', StaffAssetTrackerViewSet, basename='staff-asset')



admin.site.site_header = "UFAA Reunify Mobile Admin"  
admin.site.site_title = "UFAA Reunify Mobile Admin"         
admin.site.index_title = "Welcome to the UFAA Mobile Dashboard" 





schema_view = get_schema_view(
    openapi.Info(
        title="Unclaimed Fiancial Assets Authority - Online Claims API",
        default_version='v1',
        description="API for UFAA Kenya Mobile App with SOAP Integration",
        terms_of_service="https://ufaa.go.ke/terms-of-use",
        contact=openapi.Contact(email="info@ufaa.go.ke"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
)


urlpatterns = [
    path('', include('guest_portal.urls')),
    path('admin/logout/', auth_views.LogoutView.as_view(), name='admin_logout'),
    path('admin/', admin.site.urls),
    path('api-live/', include('apps.live_operations.urls')),

     # REST API endpoints
    path('api/', include(router.urls)),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Claims REST API endpoints
    path('claims/', include('apps.claims.urls')),
    
    # SOAP Web Services (Microsoft Dynamics BC compatible)
    path('soap/', include('apps.soap.urls')),
    
    # API Documentation
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


