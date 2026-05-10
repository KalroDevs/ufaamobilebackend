from zeep import Client
from zeep.transports import Transport
import requests
from django.conf import settings

class UFAAWebServiceClient:
    """SOAP Client for UFAA Web Services"""
    
    def __init__(self, wsdl_url=None):
        self.wsdl_url = wsdl_url or f"{settings.BASE_URL}/soap/wsdl/"
        self.client = Client(self.wsdl_url)
    
    def submit_claim(self, claim_data):
        """Submit a claim via SOAP"""
        try:
            response = self.client.service.submit_claim(claim_data)
            return {
                'success': response.success,
                'claim_number': response.claim_number,
                'message': response.message,
                'tracking_url': response.tracking_url
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def search_assets(self, identifier, search_type='id'):
        """Search for assets via SOAP"""
        try:
            response = self.client.service.search_assets(identifier, search_type)
            return {
                'success': response.success,
                'assets': [
                    {
                        'asset_id': asset.asset_id,
                        'holder_name': asset.holder_name,
                        'asset_type': asset.asset_type,
                        'amount': str(asset.amount),
                        'source': asset.source
                    }
                    for asset in response.assets
                ],
                'message': response.message
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def get_claim_status(self, claim_number, identifier):
        """Get claim status via SOAP"""
        try:
            response = self.client.service.get_claim_status(claim_number, identifier)
            return {
                'success': response.success,
                'claim_number': response.claim_number,
                'status': response.status,
                'total_amount': str(response.total_amount),
                'message': response.message,
                'next_step': response.next_step
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def staff_login(self, employee_id, password, device_fingerprint):
        """Staff login via SOAP"""
        try:
            response = self.client.service.staff_login(employee_id, password, device_fingerprint)
            return {
                'success': response.success,
                'session_token': response.session_token,
                'staff_name': response.staff_name,
                'department': response.department,
                'message': response.message
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def update_asset_location(self, asset_id, status, notes, staff_id, latitude=None, longitude=None):
        """Update asset location status via SOAP"""
        try:
            response = self.client.service.update_asset_location(
                asset_id, status, notes, staff_id, latitude, longitude
            )
            return {
                'success': response.success,
                'asset_id': response.asset_id,
                'status': response.status,
                'message': response.message
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}