# apps/claims/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClaimViewSet, 
    ClaimViewSetDeleteView,
    StaffClaimViewSet, 
    download_document_by_id, 
    view_document_by_id
)

# Create routers for different ViewSets
router = DefaultRouter()
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'claims-delete', ClaimViewSetDeleteView, basename='claim-delete')
router.register(r'staff/claims', StaffClaimViewSet, basename='staff-claim')

# Custom URL patterns
urlpatterns = [
    # Include all router URLs
    path('', include(router.urls)),
    
    # Standalone document endpoints (for both ViewSets)
    path('documents/<int:document_id>/download/', download_document_by_id, name='download_document'),
    path('documents/<int:document_id>/view/', view_document_by_id, name='view_document'),
    
    # Alternative document endpoints with different naming
    path('docs/<int:document_id>/download/', download_document_by_id, name='download_document_alt'),
    path('docs/<int:document_id>/view/', view_document_by_id, name='view_document_alt'),
]

# Optional: If you need to serve media files in development
# Uncomment this if you want to serve media files through Django (not recommended for production)
# from django.conf import settings
# from django.conf.urls.static import static
# 
# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
