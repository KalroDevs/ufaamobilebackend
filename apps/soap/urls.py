from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import (
    SOAPServiceView, 
    SOAPWSDLView, 
    OnlineInitiatorClaimsView,
    OnlineInitiatorClaimsWSDLView
)

urlpatterns = [
    # Main SOAP endpoint - WSDL and service
    path('wsdl/', SOAPWSDLView.as_view(), name='soap_wsdl'),
    path('service/', csrf_exempt(SOAPServiceView.as_view()), name='soap_service'),
    
    # Microsoft Dynamics compatible endpoint (for BC integration)
    path('onlineinitiatorclaims/', csrf_exempt(OnlineInitiatorClaimsView.as_view()), name='online_initiator_claims'),
    path('onlineinitiatorclaims/wsdl/', OnlineInitiatorClaimsWSDLView.as_view(), name='online_initiator_claims_wsdl'),
]