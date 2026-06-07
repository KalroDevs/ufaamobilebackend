# apps/claims/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClaimViewSet, 
    StaffClaimViewSet, 
    download_document_by_id, 
    view_document_by_id
)

router = DefaultRouter()
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'staff/claims', StaffClaimViewSet, basename='staff-claim')

urlpatterns = [
    path('', include(router.urls)),
    
    # Standalone document endpoints
    path('documents/<int:document_id>/download/', download_document_by_id, name='download_document'),
    path('documents/<int:document_id>/view/', view_document_by_id, name='view_document'),
]
