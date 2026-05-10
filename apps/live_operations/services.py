from django.db import connections, transaction
from django.utils import timezone
from decimal import Decimal
import uuid
from .models import LiveUnclaimedAsset, LiveOnlineClaim, LiveOnlineClaimLine

class LiveDatabaseService:
    """Service for live database operations (Read and Write)"""
    
    @staticmethod
    def search_unclaimed_assets(identifier, search_type):
        """Search for unclaimed assets by National ID, Passport, or CDS Account"""
        try:
            if search_type == 'id':
                assets = LiveUnclaimedAsset.objects.filter(owner_id=identifier, is_claimed=False)
            elif search_type == 'passport':
                assets = LiveUnclaimedAsset.objects.filter(passport_no=identifier, is_claimed=False)
            elif search_type == 'cds':
                assets = LiveUnclaimedAsset.objects.filter(cds_account_no=identifier, is_claimed=False)
            else:
                return []
            
            return [
                {
                    'asset_no': asset.asset_no,
                    'owner_name': asset.owner_name,
                    'owner_id': asset.owner_id,
                    'holder_name': asset.holder_name,
                    'asset_type': asset.asset_type,
                    'value': float(asset.value) if asset.value else 0,
                    'physical_address': asset.physical_address,
                    'status': asset.status,
                }
                for asset in assets
            ]
        except Exception as e:
            print(f"Error searching assets: {e}")
            return []
    
    @staticmethod
    def search_existing_claims(identifier, search_type):
        """Search for existing claims by National ID, Passport, or CDS Account"""
        try:
            if search_type == 'id':
                claims = LiveOnlineClaim.objects.filter(claimant_id=identifier)
            elif search_type == 'passport':
                claims = LiveOnlineClaim.objects.filter(claimant_passport=identifier)
            elif search_type == 'cds':
                claims = LiveOnlineClaim.objects.filter(cds_account_no=identifier)
            else:
                return []
            
            return [
                {
                    'claim_no': claim.claim_no,
                    'claimant_name': claim.claimant_name,
                    'claimant_id': claim.claimant_id,
                    'amount': float(claim.amount) if claim.amount else 0,
                    'status': claim.status,
                    'created_at': claim.created_at.isoformat() if claim.created_at else None,
                }
                for claim in claims
            ]
        except Exception as e:
            print(f"Error searching claims: {e}")
            return []
    
    @staticmethod
    def create_new_claim(claim_data, claim_lines_data):
        """Insert a new claim into the live online claims table"""
        
        # Generate a unique claim number if not provided
        claim_no = claim_data.get('claim_no') or f"CLM-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        with connections['ereunify'].cursor() as cursor:
            try:
                # Begin transaction
                with transaction.atomic(using='ereunify'):
                    # Insert into Online Claim table
                    insert_claim_sql = """
                        INSERT INTO [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1] (
                            [Claim No],
                            [Document Date],
                            [Processing Date],
                            [Category],
                            [Sub Category],
                            [Agent Name],
                            [Claim Type],
                            [Claimant Name],
                            [Claimant ID],
                            [Claimant Phone],
                            [Claimant Email],
                            [Amount],
                            [Status],
                            [Payment Category],
                            [Bank Name],
                            [Bank Account No],
                            [Mpesa Mobile No],
                            [CDS Account No],
                            [Claimant Passport],
                            [Created At],
                            [Updated At]
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """
                    
                    cursor.execute(insert_claim_sql, [
                        claim_no,
                        claim_data.get('document_date'),
                        claim_data.get('processing_date'),
                        claim_data.get('category', 'Original_Owner'),
                        claim_data.get('sub_category', ''),
                        claim_data.get('agent_name', ''),
                        claim_data.get('claim_type', 'Cash'),
                        claim_data.get('claimant_name'),
                        claim_data.get('claimant_id'),
                        claim_data.get('claimant_phone', ''),
                        claim_data.get('claimant_email', ''),
                        claim_data.get('amount', 0),
                        'Pending',
                        claim_data.get('payment_category', ''),
                        claim_data.get('bank_name', ''),
                        claim_data.get('bank_account_no', ''),
                        claim_data.get('mpesa_mobile_no', ''),
                        claim_data.get('cds_account_no', ''),
                        claim_data.get('claimant_passport', ''),
                        timezone.now(),
                        timezone.now(),
                    ])
                    
                    # Insert claim lines
                    for idx, line in enumerate(claim_lines_data, 1):
                        insert_line_sql = """
                            INSERT INTO [UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1] (
                                [Claim No],
                                [Line No],
                                [Asset No],
                                [Asset Type],
                                [Asset Value],
                                [Description],
                                [Holder Name],
                                [Document Path]
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s
                            )
                        """
                        
                        cursor.execute(insert_line_sql, [
                            claim_no,
                            line.get('line_no', idx),
                            line.get('asset_no'),
                            line.get('asset_type'),
                            line.get('asset_value', 0),
                            line.get('description', ''),
                            line.get('holder_name', ''),
                            line.get('document_path', ''),
                        ])
                    
                    return {
                        'success': True,
                        'claim_no': claim_no,
                        'message': 'Claim created successfully'
                    }
                    
            except Exception as e:
                print(f"Error creating claim: {e}")
                return {
                    'success': False,
                    'message': str(e)
                }
    
    @staticmethod
    def update_claim_status(claim_no, status, remarks=None):
        """Update claim status in live database"""
        with connections['ereunify'].cursor() as cursor:
            try:
                update_sql = """
                    UPDATE [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    SET [Status] = %s,
                        [Updated At] = %s,
                        [Remarks] = %s
                    WHERE [Claim No] = %s
                """
                
                cursor.execute(update_sql, [
                    status,
                    timezone.now(),
                    remarks or '',
                    claim_no
                ])
                
                return {
                    'success': True,
                    'message': f'Claim {claim_no} status updated to {status}'
                }
            except Exception as e:
                return {
                    'success': False,
                    'message': str(e)
                }
    
    @staticmethod
    def add_claim_document(claim_no, line_no, document_path, document_type):
        """Add document reference to claim line"""
        with connections['ereunify'].cursor() as cursor:
            try:
                update_sql = """
                    UPDATE [UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    SET [Document Path] = %s,
                        [Document Type] = %s
                    WHERE [Claim No] = %s AND [Line No] = %s
                """
                
                cursor.execute(update_sql, [
                    document_path,
                    document_type,
                    claim_no,
                    line_no
                ])
                
                return {
                    'success': True,
                    'message': 'Document attached successfully'
                }
            except Exception as e:
                return {
                    'success': False,
                    'message': str(e)
                }
            


@staticmethod
def add_claim_document(claim_no, document_type, sharepoint_url, file_name, file_size, uploaded_by):
    """Add document reference to MSSQL live database"""
    
    with connections['ereunify'].cursor() as cursor:
        try:
            insert_sql = """
                INSERT INTO [UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1] (
                    [Claim No],
                    [Document Type],
                    [Document URL],
                    [File Name],
                    [File Size],
                    [Uploaded By],
                    [Uploaded At]
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            cursor.execute(insert_sql, [
                claim_no,
                document_type,
                sharepoint_url,
                file_name,
                file_size,
                uploaded_by,
                timezone.now()
            ])
            
            return {'success': True, 'message': 'Document reference added to live system'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

@staticmethod
def get_claim_documents(claim_no):
    """Get document references from MSSQL live database"""
    
    with connections['ereunify'].cursor() as cursor:
        cursor.execute("""
            SELECT 
                [Document Type] as document_type,
                [Document URL] as file_url,
                [File Name] as file_name,
                [File Size] as file_size,
                [Uploaded By] as uploaded_by,
                [Uploaded At] as uploaded_at
            FROM [UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
            WHERE [Claim No] = %s AND [Document URL] IS NOT NULL
        """, [claim_no])
        
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]