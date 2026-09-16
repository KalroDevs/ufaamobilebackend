from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from apps.soap.client import UFAAWebServiceClient

class SOAPClaimView(APIView):
    """Proxy REST endpoint to SOAP service for claims"""
    
    def post(self, request):
        client = UFAAWebServiceClient()
        result = client.submit_claim(request.data)
        
        if result['success']:
            return Response(result, status=status.HTTP_201_CREATED)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

class SOAPAssetSearchView(APIView):
    """Proxy REST endpoint to SOAP service for asset search"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        identifier = request.data.get('identifier')
        search_type = request.data.get('search_type', 'id')
        
        client = UFAAWebServiceClient()
        result = client.search_assets(identifier, search_type)
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_404_NOT_FOUND)

class SOAPClaimStatusView(APIView):
    """Proxy REST endpoint to SOAP service for claim status"""
    permission_classes = [AllowAny]
    
    def get(self, request, claim_number):
        identifier = request.query_params.get('identifier')
        
        client = UFAAWebServiceClient()
        result = client.get_claim_status(claim_number, identifier)
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_404_NOT_FOUND)

class SOAPStaffLoginView(APIView):
    """Proxy REST endpoint to SOAP service for staff login"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        employee_id = request.data.get('employee_id')
        password = request.data.get('password')
        device_fingerprint = request.data.get('device_fingerprint', '')
        
        client = UFAAWebServiceClient()
        result = client.staff_login(employee_id, password, device_fingerprint)
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_401_UNAUTHORIZED)

class SOAPAssetLocationUpdateView(APIView):
    """Proxy REST endpoint to SOAP service for asset location update"""
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, asset_id):
        status_val = request.data.get('status')
        notes = request.data.get('notes', '')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        client = UFAAWebServiceClient()
        result = client.update_asset_location(
            asset_id, status_val, notes, request.user.id, latitude, longitude
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)