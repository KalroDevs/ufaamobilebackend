from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AuthViewSet, AssetViewSet, ClaimViewSet, StaffAssetTrackerViewSet

from .views import InitiateECitizenLoginView, ECitizenCallbackView

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'assets', AssetViewSet, basename='asset')
router.register(r'claims', ClaimViewSet, basename='claim')
router.register(r'staff/assets', StaffAssetTrackerViewSet, basename='staff-asset')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/ecitizen/initiate/', InitiateECitizenLoginView.as_view(), name='ecitizen_initiate'),
    path('auth/ecitizen/callback/', ECitizenCallbackView.as_view(), name='ecitizen_callback'),
]
