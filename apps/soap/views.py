from django.http import HttpResponse, HttpResponseBadRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
import xml.etree.ElementTree as ET
from xml.dom import minidom
import json

from apps.claims.models import Claim, ClaimAsset
from apps.assets.models import Asset
from apps.accounts.models import User


class SOAPWSDLView(View):
    """Generate WSDL dynamically"""
    
    def get(self, request):
        wsdl_content = '''<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:tns="urn:ufaa:wsdl"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             targetNamespace="urn:ufaa:wsdl">
    <types>
        <xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                    targetNamespace="urn:ufaa:wsdl">
            <xsd:element name="GetClaimStatusRequest">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="claim_number" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="GetClaimStatusResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="status" type="xsd:string"/>
                        <xsd:element name="message" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="SearchAssetsRequest">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="identifier" type="xsd:string"/>
                        <xsd:element name="search_type" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="SearchAssetsResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="count" type="xsd:int"/>
                        <xsd:element name="message" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
        </xsd:schema>
    </types>
    
    <message name="GetClaimStatusRequest">
        <part name="parameters" element="tns:GetClaimStatusRequest"/>
    </message>
    <message name="GetClaimStatusResponse">
        <part name="parameters" element="tns:GetClaimStatusResponse"/>
    </message>
    <message name="SearchAssetsRequest">
        <part name="parameters" element="tns:SearchAssetsRequest"/>
    </message>
    <message name="SearchAssetsResponse">
        <part name="parameters" element="tns:SearchAssetsResponse"/>
    </message>
    
    <portType name="UFAAWebServicePortType">
        <operation name="GetClaimStatus">
            <input message="tns:GetClaimStatusRequest"/>
            <output message="tns:GetClaimStatusResponse"/>
        </operation>
        <operation name="SearchAssets">
            <input message="tns:SearchAssetsRequest"/>
            <output message="tns:SearchAssetsResponse"/>
        </operation>
    </portType>
    
    <binding name="UFAAWebServiceBinding" type="tns:UFAAWebServicePortType">
        <soap:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
        <operation name="GetClaimStatus">
            <soap:operation soapAction="getClaimStatus"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="SearchAssets">
            <soap:operation soapAction="searchAssets"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
    </binding>
    
    <service name="UFAAWebService">
        <port name="UFAAWebServicePort" binding="tns:UFAAWebServiceBinding">
            <soap:address location="http://{}/soap/service/"/>
        </port>
    </service>
</definitions>'''.format(request.get_host())
        
        return HttpResponse(wsdl_content, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class SOAPServiceView(View):
    """Handle SOAP requests"""
    
    def post(self, request):
        try:
            # Parse SOAP envelope
            soap_body = request.body
            
            # Extract operation from SOAP action header
            soap_action = request.headers.get('SOAPAction', '').strip('"')
            
            if 'getClaimStatus' in soap_action or 'GetClaimStatus' in soap_action:
                return self._handle_get_claim_status(soap_body)
            elif 'searchAssets' in soap_action or 'SearchAssets' in soap_action:
                return self._handle_search_assets(soap_body)
            else:
                # Try to parse from body
                return self._handle_get_claim_status(soap_body)
                
        except Exception as e:
            return self._soap_error_response(str(e))
    
    def _handle_get_claim_status(self, soap_body):
        """Handle GetClaimStatus SOAP request"""
        try:
            # Parse XML
            root = ET.fromstring(soap_body)
            
            # Extract claim_number (handle namespaces)
            claim_number = None
            for elem in root.iter():
                if 'claim_number' in elem.tag or elem.tag.endswith('claim_number'):
                    claim_number = elem.text
                    break
            
            if not claim_number:
                return self._soap_error_response("Missing claim_number")
            
            # Get claim from database
            try:
                claim = Claim.objects.get(no=claim_number)
                status = claim.status
                message = f"Claim {claim.no} is {claim.status}"
            except Claim.DoesNotExist:
                status = "Not Found"
                message = f"Claim {claim_number} not found"
            
            # Build SOAP response
            response = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="urn:ufaa:wsdl">
    <soap:Body>
        <tns:GetClaimStatusResponse>
            <status>{status}</status>
            <message>{message}</message>
        </tns:GetClaimStatusResponse>
    </soap:Body>
</soap:Envelope>'''
            
            return HttpResponse(response, content_type='text/xml')
            
        except ET.ParseError as e:
            return self._soap_error_response(f"XML Parse Error: {str(e)}")
        except Exception as e:
            return self._soap_error_response(str(e))
    
    def _handle_search_assets(self, soap_body):
        """Handle SearchAssets SOAP request"""
        try:
            # Parse XML
            root = ET.fromstring(soap_body)
            
            # Extract parameters
            identifier = None
            search_type = 'id'
            
            for elem in root.iter():
                if 'identifier' in elem.tag or elem.tag.endswith('identifier'):
                    identifier = elem.text
                if 'search_type' in elem.tag or elem.tag.endswith('search_type'):
                    search_type = elem.text
            
            if not identifier:
                return self._soap_error_response("Missing identifier")
            
            # Search assets
            if search_type == 'id':
                assets = Asset.objects.filter(id_number=identifier)
            elif search_type == 'passport':
                assets = Asset.objects.filter(passport_no=identifier)
            elif search_type == 'account':
                assets = Asset.objects.filter(account_no=identifier)
            else:
                assets = Asset.objects.none()
            
            count = assets.count()
            message = f"Found {count} asset(s) for {identifier}"
            
            # Build SOAP response
            response = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="urn:ufaa:wsdl">
    <soap:Body>
        <tns:SearchAssetsResponse>
            <count>{count}</count>
            <message>{message}</message>
        </tns:SearchAssetsResponse>
    </soap:Body>
</soap:Envelope>'''
            
            return HttpResponse(response, content_type='text/xml')
            
        except ET.ParseError as e:
            return self._soap_error_response(f"XML Parse Error: {str(e)}")
        except Exception as e:
            return self._soap_error_response(str(e))
    
    def _soap_error_response(self, error_message):
        """Generate SOAP fault response"""
        response = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Server</faultcode>
            <faultstring>{error_message}</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>'''
        return HttpResponse(response, content_type='text/xml', status=500)


class OnlineInitiatorClaimsWSDLView(View):
    """Generate WSDL for Microsoft Dynamics BC compatibility"""
    
    def get(self, request):
        wsdl_content = '''<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:tns="urn:microsoft-dynamicsschemas/page/onlineinitiatorclaims"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             targetNamespace="urn:microsoft-dynamicsschemas/page/onlineinitiatorclaims">
    <types>
        <xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                    targetNamespace="urn:microsoft-dynamicsschemas/page/onlineinitiatorclaims"
                    elementFormDefault="qualified">
            <xsd:element name="Read">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="No" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="Read_Result">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="OnlineInitiatorClaims" type="tns:OnlineInitiatorClaims"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:complexType name="OnlineInitiatorClaims">
                <xsd:sequence>
                    <xsd:element name="No" type="xsd:string"/>
                    <xsd:element name="Status" type="xsd:string"/>
                    <xsd:element name="ID_Number" type="xsd:string"/>
                    <xsd:element name="Name" type="xsd:string"/>
                    <xsd:element name="Phone_No" type="xsd:string"/>
                    <xsd:element name="Amount" type="xsd:decimal"/>
                </xsd:sequence>
            </xsd:complexType>
        </xsd:schema>
    </types>
    
    <message name="Read">
        <part name="parameters" element="tns:Read"/>
    </message>
    <message name="Read_Result">
        <part name="parameters" element="tns:Read_Result"/>
    </message>
    
    <portType name="OnlineInitiatorClaims_Port">
        <operation name="Read">
            <input message="tns:Read"/>
            <output message="tns:Read_Result"/>
        </operation>
    </portType>
    
    <binding name="OnlineInitiatorClaims_Binding" type="tns:OnlineInitiatorClaims_Port">
        <soap:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
        <operation name="Read">
            <soap:operation soapAction="urn:microsoft-dynamicsschemas/page/onlineinitiatorclaims:Read"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
    </binding>
    
    <service name="OnlineInitiatorClaims_Service">
        <port name="OnlineInitiatorClaims_Port" binding="tns:OnlineInitiatorClaims_Binding">
            <soap:address location="http://{}/soap/onlineinitiatorclaims/"/>
        </port>
    </service>
</definitions>'''.format(request.get_host())
        
        return HttpResponse(wsdl_content, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class OnlineInitiatorClaimsView(View):
    """Microsoft Dynamics Business Central compatible SOAP endpoint"""
    
    def post(self, request):
        try:
            soap_body = request.body
            
            # Parse XML
            root = ET.fromstring(soap_body)
            
            # Check for Read operation
            for elem in root.iter():
                if 'Read' in elem.tag:
                    return self._handle_read(soap_body)
            
            # Default response
            return self._soap_response("", "")
            
        except Exception as e:
            return self._soap_error_response(str(e))
    
    def _handle_read(self, soap_body):
        """Handle Read operation for BC compatibility"""
        try:
            # Parse claim number from request
            root = ET.fromstring(soap_body)
            claim_number = None
            
            for elem in root.iter():
                if 'No' in elem.tag and elem.tag.endswith('No'):
                    claim_number = elem.text
                    break
            
            if claim_number:
                try:
                    claim = Claim.objects.get(no=claim_number)
                    response_xml = self._serialize_claim(claim)
                except Claim.DoesNotExist:
                    response_xml = self._serialize_empty_claim()
            else:
                response_xml = self._serialize_empty_claim()
            
            return self._soap_response(response_xml, "Read_Result")
            
        except Exception as e:
            return self._soap_error_response(str(e))
    
    def _serialize_claim(self, claim):
        """Serialize claim to XML for BC response"""
        return f'''<OnlineInitiatorClaims>
    <No>{claim.no or ''}</No>
    <Status>{claim.status or 'Open'}</Status>
    <ID_Number>{claim.id_number or ''}</ID_Number>
    <Name>{claim.name or ''}</Name>
    <Phone_No>{claim.phone_no or ''}</Phone_No>
    <Amount>{str(claim.amount) if claim.amount else '0'}</Amount>
</OnlineInitiatorClaims>'''
    
    def _serialize_empty_claim(self):
        """Serialize empty claim response"""
        return '''<OnlineInitiatorClaims>
    <No></No>
    <Status></Status>
    <ID_Number></ID_Number>
    <Name></Name>
    <Phone_No></Phone_No>
    <Amount>0</Amount>
</OnlineInitiatorClaims>'''
    
    def _soap_response(self, content, operation):
        """Generate SOAP response"""
        response = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="urn:microsoft-dynamicsschemas/page/onlineinitiatorclaims">
    <soap:Body>
        <tns:{operation}>
            {content}
        </tns:{operation}>
    </soap:Body>
</soap:Envelope>'''
        return HttpResponse(response, content_type='text/xml')
    
    def _soap_error_response(self, error_message):
        """Generate SOAP fault response"""
        response = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Server</faultcode>
            <faultstring>{error_message}</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>'''
        return HttpResponse(response, content_type='text/xml', status=500)