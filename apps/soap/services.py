from spyne import ServiceBase, rpc, Integer, Unicode, Boolean, Date, Decimal, DateTime, AnyXml
from spyne.model.complex import ComplexModel, Array
from spyne.model.primitive import String
from django.utils import timezone
from django.db import models as django_models

from apps.claims.models import Claim, ClaimAsset
from apps.assets.models import Asset
from apps.accounts.models import User, StaffProfile


class UFAAWebService(ServiceBase):
    """Main UFAA SOAP Web Service"""
    
    @rpc(Unicode, _returns=Unicode)
    def hello_world(ctx, name):
        return f"Hello {name}, welcome to UFAA Kenya SOAP Service!"
    
    @rpc(Unicode, _returns=Unicode)
    def get_claim_status(ctx, claim_number):
        """Get claim status by claim number"""
        try:
            claim = Claim.objects.get(no=claim_number)
            return f"Claim {claim.no} status: {claim.status}"
        except Claim.DoesNotExist:
            return "Claim not found"
    
    @rpc(Unicode, Unicode, _returns=Unicode)
    def search_assets(ctx, identifier, search_type):
        """Search assets by identifier"""
        try:
            if search_type == 'id':
                assets = Asset.objects.filter(id_number=identifier)
            elif search_type == 'passport':
                assets = Asset.objects.filter(passport_no=identifier)
            elif search_type == 'account':
                assets = Asset.objects.filter(account_no=identifier)
            else:
                assets = Asset.objects.none()
            
            count = assets.count()
            return f"Found {count} asset(s) for {identifier}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    @rpc(Unicode, Unicode, Unicode, _returns=Unicode)
    def create_claim(ctx, claim_number, claimant_id, asset_ids):
        """Create a new claim"""
        try:
            # Parse asset IDs
            asset_id_list = [int(x.strip()) for x in asset_ids.split(',')]
            
            # Get or create claimant
            claimant, _ = User.objects.get_or_create(
                id_number=claimant_id,
                defaults={'username': claimant_id, 'phone_no': claimant_id}
            )
            
            # Create claim
            claim = Claim.objects.create(
                no=claim_number,
                claimant=claimant,
                status='Open',
                id_number=claimant_id
            )
            
            # Add assets
            for asset_id in asset_id_list:
                asset = Asset.objects.get(id=asset_id)
                ClaimAsset.objects.create(claim=claim, asset=asset)
            
            return f"Claim {claim_number} created successfully with {len(asset_id_list)} assets"
        except Exception as e:
            return f"Error creating claim: {str(e)}"


class OnlineInitiatorClaimsService(ServiceBase):
    """Microsoft Dynamics Business Central compatible SOAP Service"""
    
    @rpc(Unicode, _returns=Unicode)
    def Read(ctx, no):
        """Read a single claim by number (BC compatible)"""
        try:
            claim = Claim.objects.get(no=no)
            return _serialize_claim_to_xml(claim)
        except Claim.DoesNotExist:
            return "<OnlineInitiatorClaims />"
    
    @rpc(Unicode, _returns=Unicode)
    def ReadByRecId(ctx, recId):
        """Read claim by record ID (BC compatible)"""
        try:
            claim = Claim.objects.get(id=recId)
            return _serialize_claim_to_xml(claim)
        except Claim.DoesNotExist:
            return "<OnlineInitiatorClaims />"
    
    @rpc(AnyXml, Unicode, Integer, _returns=Unicode)
    def ReadMultiple(ctx, filter, bookmarkKey, setSize):
        """Read multiple claims with filters (BC compatible)"""
        claims = Claim.objects.all()[:setSize]
        return _serialize_claims_list_to_xml(claims)
    
    @rpc(Unicode, _returns=Unicode)
    def IsUpdated(ctx, key):
        """Check if claim has been updated (BC compatible)"""
        try:
            claim = Claim.objects.get(no=key)
            # Check if updated within last minute
            from django.utils import timezone
            from datetime import timedelta
            time_threshold = timezone.now() - timedelta(minutes=1)
            is_updated = claim.updated_at > time_threshold
            return f"<IsUpdated_Result>{str(is_updated).lower()}</IsUpdated_Result>"
        except Claim.DoesNotExist:
            return "<IsUpdated_Result>false</IsUpdated_Result>"
    
    @rpc(Unicode, _returns=Unicode)
    def GetRecIdFromKey(ctx, key):
        """Get record ID from claim number (BC compatible)"""
        try:
            claim = Claim.objects.get(no=key)
            return f"<GetRecIdFromKey_Result>{claim.id}</GetRecIdFromKey_Result>"
        except Claim.DoesNotExist:
            return "<GetRecIdFromKey_Result></GetRecIdFromKey_Result>"
    
    @rpc(AnyXml, _returns=AnyXml)
    def Create(ctx, onlineInitiatorClaims):
        """Create a new claim (BC compatible)"""
        try:
            # Parse XML and create claim
            # This is simplified - you'd need proper XML parsing
            claim = Claim.objects.create(
                no="AUTO_" + str(timezone.now().timestamp()),
                status='Open'
            )
            return _serialize_claim_to_xml(claim)
        except Exception as e:
            return f"<OnlineInitiatorClaims><Error>{str(e)}</Error></OnlineInitiatorClaims>"
    
    @rpc(AnyXml, _returns=AnyXml)
    def Update(ctx, onlineInitiatorClaims):
        """Update an existing claim (BC compatible)"""
        try:
            # Parse XML and update claim
            # This is simplified - you'd need proper XML parsing
            return onlineInitiatorClaims
        except Exception as e:
            return f"<OnlineInitiatorClaims><Error>{str(e)}</Error></OnlineInitiatorClaims>"
    
    @rpc(Unicode, _returns=Unicode)
    def Delete_Control169(ctx, control169_key):
        """Delete a subpage record (BC compatible)"""
        try:
            # Delete claim asset
            claim_asset = ClaimAsset.objects.filter(key=control169_key).first()
            if claim_asset:
                claim_asset.delete()
                return "<Delete_Control169_Result>true</Delete_Control169_Result>"
            return "<Delete_Control169_Result>false</Delete_Control169_Result>"
        except Exception:
            return "<Delete_Control169_Result>false</Delete_Control169_Result>"


def _serialize_claim_to_xml(claim):
    """Serialize a single claim to XML format matching BC WSDL"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<OnlineInitiatorClaims>
    <No>{claim.no or ''}</No>
    <Document_Date>{claim.document_date.isoformat() if claim.document_date else ''}</Document_Date>
    <Processing_Date>{claim.processing_date.isoformat() if claim.processing_date else ''}</Processing_Date>
    <Category>{claim.category or ''}</Category>
    <Sub_Category>{claim.sub_category or ''}</Sub_Category>
    <Agent_Name>{claim.agent_name or ''}</Agent_Name>
    <Claim_Type>{claim.claim_type or ''}</Claim_Type>
    <Currency>{claim.currency or ''}</Currency>
    <Asset_No>{claim.asset_no or ''}</Asset_No>
    <Residence>{claim.residence or ''}</Residence>
    <ID_Number>{claim.id_number or ''}</ID_Number>
    <Name>{claim.name or ''}</Name>
    <IPRS_Name>{claim.iprs_name or ''}</IPRS_Name>
    <Claimant_Birth_Date>{claim.claimant_birth_date.isoformat() if claim.claimant_birth_date else ''}</Claimant_Birth_Date>
    <Gender>{claim.gender or ''}</Gender>
    <Person_Living_with_Disability>{str(claim.person_living_with_disability).lower()}</Person_Living_with_Disability>
    <Passport_No>{claim.passport_no or ''}</Passport_No>
    <Claim_Origin>{claim.claim_origin or ''}</Claim_Origin>
    <County_Code>{claim.county_code or ''}</County_Code>
    <County_Name>{claim.county_name or ''}</County_Name>
    <KRA_P_I_N>{claim.kra_pin or ''}</KRA_P_I_N>
    <Business_Registration_No>{claim.business_registration_no or ''}</Business_Registration_No>
    <Address>{claim.address or ''}</Address>
    <Address_2>{claim.address_2 or ''}</Address_2>
    <Phone_No>{claim.phone_no or ''}</Phone_No>
    <Secondary_Phone_No>{claim.secondary_phone_no or ''}</Secondary_Phone_No>
    <Post_Code>{claim.post_code or ''}</Post_Code>
    <County>{claim.county or ''}</County>
    <City>{claim.city or ''}</City>
    <Home_County>{claim.home_county or ''}</Home_County>
    <E_Mail>{claim.e_mail or ''}</E_Mail>
    <Posting_Date>{claim.posting_date.isoformat() if claim.posting_date else ''}</Posting_Date>
    <Amount>{str(claim.amount) if claim.amount else ''}</Amount>
    <Amount_LCY>{str(claim.amount_lcy) if claim.amount_lcy else ''}</Amount_LCY>
    <Shares>{claim.shares or 0}</Shares>
    <Safe_Deposit>{claim.safe_deposit or 0}</Safe_Deposit>
    <Location>{claim.location or ''}</Location>
    <Location_Sent_To>{claim.location_sent_to or ''}</Location_Sent_To>
    <Location_Sent_To_Name>{claim.location_sent_to_name or ''}</Location_Sent_To_Name>
    <Location_Source>{claim.location_source or ''}</Location_Source>
    <Profile_Id>{claim.profile_id or ''}</Profile_Id>
    <Submit>{str(claim.submit).lower()}</Submit>
    <Claimant_Action_Required>{str(claim.claimant_action_required).lower()}</Claimant_Action_Required>
    <Created_BY>{claim.created_by or ''}</Created_BY>
    <Customer_Care_ID>{claim.customer_care_id or ''}</Customer_Care_ID>
    <Status>{claim.status or 'Open'}</Status>
    <Rejected>{str(claim.rejected).lower()}</Rejected>
    <Send_Remarks_to_Claimant>{claim.send_remarks_to_claimant or ''}</Send_Remarks_to_Claimant>
    <Portal_Comments>{claim.portal_comments or ''}</Portal_Comments>
    <Internal_Remarks>{claim.internal_remarks or ''}</Internal_Remarks>
    <Internal_Comments>{claim.internal_comments or ''}</Internal_Comments>
    <Draft_Remarks>{claim.draft_remarks or ''}</Draft_Remarks>
    <Payment_Category>{claim.payment_category or ''}</Payment_Category>
    <Bank_Code>{claim.bank_code or ''}</Bank_Code>
    <Bank_Account_No>{claim.bank_account_no or ''}</Bank_Account_No>
    <Bank_Account_Name>{claim.bank_account_name or ''}</Bank_Account_Name>
    <Bank_Name>{claim.bank_name or ''}</Bank_Name>
    <Branch_Code>{claim.branch_code or ''}</Branch_Code>
    <Branch_Name>{claim.branch_name or ''}</Branch_Name>
    <Account_Currency>{claim.account_currency or ''}</Account_Currency>
    <Swift_Code>{claim.swift_code or ''}</Swift_Code>
    <International_Payment>{str(claim.international_payment).lower()}</International_Payment>
    <International_Bank_Name>{claim.international_bank_name or ''}</International_Bank_Name>
    <International_Branch_Name>{claim.international_branch_name or ''}</International_Branch_Name>
    <Sort_Code>{claim.sort_code or ''}</Sort_Code>
    <Country_Region_Code>{claim.country_region_code or ''}</Country_Region_Code>
    <Mpesa_Mobile_No>{claim.mpesa_mobile_no or ''}</Mpesa_Mobile_No>
    <Type>{claim.type_field or ''}</Type>
    <Type_Description>{claim.type_description or ''}</Type_Description>
    <Date_Signed_By_HOD>{claim.date_signed_by_hod.isoformat() if claim.date_signed_by_hod else ''}</Date_Signed_By_HOD>
    <Title>{claim.title or ''}</Title>
    <Title_Description>{claim.title_description or ''}</Title_Description>
    <Institution>{claim.institution or ''}</Institution>
    <Organization_Name>{claim.organization_name or ''}</Organization_Name>
    <Postal_Address>{claim.postal_address or ''}</Postal_Address>
    <Address_to_City>{claim.address_to_city or ''}</Address_to_City>
    <Verication_Region>{claim.verification_region or ''}</Verication_Region>
    <Address_To>{claim.address_to or ''}</Address_To>
    <Address_To_2>{claim.address_to_2 or ''}</Address_To_2>
    <Estate_Name>{claim.estate_name or ''}</Estate_Name>
    <Citizenship>{claim.citizenship or ''}</Citizenship>
    <Doc_verification_remarks>{claim.doc_verification_remarks or ''}</Doc_verification_remarks>
    <Name_of_Deceased>{claim.name_of_deceased or ''}</Name_of_Deceased>
    <District>{claim.district or ''}</District>
    <Entry_No>{claim.entry_no or ''}</Entry_No>
    <Serial_No>{claim.serial_no or ''}</Serial_No>
    <Issuing_No>{claim.issuing_no or ''}</Issuing_No>
    <Cause_No>{claim.cause_no or ''}</Cause_No>
    <Business_Owner>{claim.business_owner or ''}</Business_Owner>
    <Cheque_No>{claim.cheque_no or ''}</Cheque_No>
    <Cheque_Date>{claim.cheque_date.isoformat() if claim.cheque_date else ''}</Cheque_Date>
    <Drawee>{claim.drawee or ''}</Drawee>
    <Donor>{claim.donor or ''}</Donor>
    <Donee>{claim.donee or ''}</Donee>
    <RPA_IPA_No>{claim.rpa_ipa_no or ''}</RPA_IPA_No>
    <Asset_Type>{claim.claim_type or ''}</Asset_Type>
    <Source>{claim.source or ''}</Source>
    <Class_Code>{claim.class_code or ''}</Class_Code>
    <Class>{claim.class_field or ''}</Class>
    <Asset_Code>{claim.asset_code or ''}</Asset_Code>
    <Description>{claim.description or ''}</Description>
    <Description_>{claim.description_field or ''}</Description_>
    <First_Name>{claim.first_name or ''}</First_Name>
    <Middle_Name>{claim.middle_name or ''}</Middle_Name>
    <Last_Name>{claim.last_name or ''}</Last_Name>
    <Date_of_Birth>{claim.date_of_birth.isoformat() if claim.date_of_birth else ''}</Date_of_Birth>
    <ID_Number>{claim.id_number or ''}</ID_Number>
    <Passport_No2>{claim.passport_no or ''}</Passport_No2>
    <Currency>{claim.currency or ''}</Currency>
    <Quantity>{claim.quantity or 0}</Quantity>
    <Value>{str(claim.value) if claim.value else ''}</Value>
    <Owners_Postal_Address>{claim.owners_postal_address or ''}</Owners_Postal_Address>
    <Owners_City_Town>{claim.owners_city_town or ''}</Owners_City_Town>
    <Owners_Telephnone_No>{claim.owners_telephone_no or ''}</Owners_Telephnone_No>
    <Holder_No>{claim.holder_no or ''}</Holder_No>
    <Holder_Name>{claim.holder_name or ''}</Holder_Name>
    <User_ID>{claim.user_id or ''}</User_ID>
</OnlineInitiatorClaims>"""


def _serialize_claims_list_to_xml(claims):
    """Serialize multiple claims to XML format"""
    claims_xml = "\n".join([_serialize_claim_to_xml(c) for c in claims])
    return f"""<?xml version="1.0" encoding="utf-8"?>
<OnlineInitiatorClaims_List>
{claims_xml}
</OnlineInitiatorClaims_List>"""