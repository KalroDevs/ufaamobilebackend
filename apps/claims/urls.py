from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClaimViewSet, StaffClaimViewSet

router = DefaultRouter()
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'staff/claims', StaffClaimViewSet, basename='staff-claim')

urlpatterns = [
    path('', include(router.urls)),
]