# apps/oidc/urls.py
from django.urls import path
from .views import InitiateECitizenLoginView, ECitizenCallbackView, ECitizenFailView

urlpatterns = [
    path('authenticate/', InitiateECitizenLoginView.as_view(), name='oidc_authentication'),
    path('callback/', ECitizenCallbackView.as_view(), name='oidc_callback'),
    path('fail/', ECitizenFailView.as_view(), name='ecitizen_fail'),
]
