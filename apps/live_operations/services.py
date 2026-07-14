# apps/live_operations/services.py
import traceback
import time
import random
from django.db import connections, transaction
from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid
from .models import LiveUnclaimedAsset, LiveOnlineClaim, LiveOnlineClaimLine
import logging
from apps.claims.models import Claim, ClaimAsset, JointOwner

logger = logging.getLogger(__name__)

class LiveDatabaseService:
    """Service for live database operations (Read and Write)"""
    
    # ==================== MAPPINGS ====================
    
    CATEGORY_MAPPING = {
        'Original_Owner': 1,
        'Beneficiary': 2,
        'Business_Entity': 3,
        'Agent_of_the_Owner': 4,
        '': 0,
    }

    CLAIM_TYPE_MAPPING = {
        'Cash': 1,
        'Non_Cash': 2,
        'Both': 3,
        '': 1,
    }

    SUB_CATEGORY_MAPPING = {
        'administrator': 1,
        'public_trustee': 2,
        'nominee': 3,
        'executor': 4,
        'guardian': 5,
        'legal_representative': 6,
        'Adult': 10,
        'Minor': 11,
        'sole_proprietorship': 20,
        'partnership': 21,
        'limited_liability': 22,
        'sacco': 23,
        'self_help_group': 24,
        'none': 0,
        'not_applicable': 0,
        '': 0,
    }

    STATUS_MAPPING = {
        'Draft': 0,
        'Pending': 1,
        'Under_Review': 2,
        'In_Progress': 3,
        'Processing': 4,
        'Approved': 5,
        'Rejected': 6,
        'Paid': 7,
        'Completed': 8,
        'Archived': 9,
        'Cancelled': 10,
    }

    PAYMENT_CATEGORY_MAPPING = {
        'Mpesa': 1,
        'Local_Bank': 2,
        'International': 3,
        'Bank Transfer': 4,
        'Cheque': 5,
        '': 1,
    }

    CLAIM_ORIGIN_MAPPING = {
        'OnlinePortal': 1,
        'Android_Mobile_App': 2,
        'iOS_Mobile_App': 3,
        'Reception': 4,
        'Emails': 5,
        'Reunification_Clinics': 6,
        'Huduma': 7,
        'Registrars': 8,
        '': 0,
    }

    GENDER_MAPPING = {
        'Male': 1,
        'Female': 2,
        'Other': 3,
        'M': 1,
        'F': 2,
        'O': 3,
        '': 0,
    }

    NATIONALITY_MAPPING = {
        'Kenyan': 'Kenyan',
        'Non_Kenyan': 'Non_Kenyan',
        'Non-Kenyan': 'Non_Kenyan',
        '': '',
    }

    # ==================== HELPER METHODS ====================
    
    @staticmethod
    def safe_string(value, max_length=255):
        """Safely truncate a string to max_length"""
        if value is None:
            return ''
        value = str(value).strip()
        if len(value) > max_length:
            return value[:max_length]
        return value

    @staticmethod
    def get_safe_date(date_value, fallback=None):
        """Get a safe date, never return None"""
        if date_value is not None:
            return date_value
        if fallback is not None:
            return fallback
        return timezone.now().date()

    @staticmethod
    def generate_claim_number():
        """Generate a unique claim number for MSSQL table"""
        # Format: CM{timestamp_milliseconds}{random}
        # Max 15 characters (SQL Server No_ column limit)
        timestamp = str(int(time.time() * 1000))[-10:]  # Last 10 digits of timestamp
        random_suffix = str(random.randint(100, 99999))
        claim_no = f"CLM-{random_suffix}"
        
        # Ensure it's not too long (max 15 chars)
        if len(claim_no) > 15:
            claim_no = claim_no[:15]
        
        # Ensure uniqueness in live database
        retries = 5
        while retries > 0:
            existing = LiveOnlineClaim.objects.filter(claim_no=claim_no).first()
            if not existing:
                break
            # Generate new number
            timestamp = str(int(time.time() * 1000))[-10:]
            random_suffix = str(random.randint(100, 99999))
            claim_no = f"CLM-{random_suffix}"
            if len(claim_no) > 15:
                claim_no = claim_no[:15]
            retries -= 1
        
        return claim_no

    # ==================== SEARCH METHODS ====================
    
    @staticmethod
    def search_unclaimed_assets(identifier, search_type='id'):
        """Search for unclaimed assets by ID, Passport, CDS, or Name"""
        print(f"{'━'*40}")
        print(f"🔍 LiveDatabaseService.search_unclaimed_assets")
        print(f"📝 Identifier: {identifier}")
        print(f"📝 Search Type: {search_type}")
        print(f"{'━'*40}")
        
        try:
            if search_type == 'id':
                print(f"🔍 Searching by ID Number: {identifier}")
                assets = LiveUnclaimedAsset.objects.filter(id_number=identifier)
            elif search_type == 'passport':
                print(f"🔍 Searching by Passport: {identifier}")
                assets = LiveUnclaimedAsset.objects.filter(passport_no=identifier)
            elif search_type == 'cds':
                print(f"🔍 Searching by CDS Account: {identifier}")
                assets = LiveUnclaimedAsset.objects.filter(cds_account_no=identifier)
            elif search_type == 'name':
                print(f"🔍 Searching by Name: {identifier}")
                assets = LiveUnclaimedAsset.objects.filter(
                    models.Q(name__icontains=identifier) |
                    models.Q(middle_name__icontains=identifier) |
                    models.Q(last_name__icontains=identifier) |
                    models.Q(holder_name__icontains=identifier)
                )
            else:
                print(f"❌ Invalid search type: {search_type}")
                return []
            
            print(f"📊 Found {assets.count()} assets")
            
            results = []
            for asset in assets:
                try:
                    owner_name_parts = []
                    if asset.name:
                        owner_name_parts.append(asset.name)
                    if asset.middle_name:
                        owner_name_parts.append(asset.middle_name)
                    if asset.last_name:
                        owner_name_parts.append(asset.last_name)
                    
                    owner_name = ' '.join(owner_name_parts).strip() if owner_name_parts else asset.holder_name or "N/A"
                    is_cash = asset.asset_type == 1
                    
                    result = {
                        'id': asset.no,
                        'asset_no': asset.no,
                        'holder_name': asset.holder_name or "",
                        'owner_name': owner_name,
                        'id_number': asset.id_number or "",
                        'passport_no': asset.passport_no or "",
                        'cds_account_no': asset.cds_account_no or "",
                        'asset_type': asset.get_asset_type_display_name(),
                        'is_cash': is_cash,
                        'source': asset.get_source_display_name(),
                        'source_code': asset.source,
                        'amount': str(asset.amount_due_to_owner) if asset.amount_due_to_owner else "0",
                        'numeric_amount': float(asset.amount_due_to_owner) if asset.amount_due_to_owner else 0.0,
                        'status': asset.get_status_display_name(),
                        'status_code': asset.status,
                        'description': asset.description or "",
                        'date_of_birth': str(asset.date_of_birth) if asset.date_of_birth else "",
                        'postal_address': asset.owners_postal_address or "",
                        'city_town': asset.owners_city_town or "",
                        'telephone': asset.owners_telephone_no or "",
                        'county': asset.county_name or "",
                        'is_claimable': asset.is_claimable(),
                    }
                    results.append(result)
                    print(f"  ✅ Processed asset: {asset.no} - {asset.holder_name}")
                    
                except Exception as e:
                    print(f"⚠️ Error processing asset {asset.no}: {str(e)}")
                    traceback.print_exc()
                    continue
            
            print(f"📊 Successfully processed {len(results)} assets")
            return results
            
        except Exception as e:
            print(f"❌ Error searching assets: {str(e)}")
            traceback.print_exc()
            return []
    
    @staticmethod
    def search_existing_claims(identifier, search_type):
        """Search for existing claims by National ID, Passport, or Claim Number"""
        try:
            print(f"🔍 LiveDatabaseService.search_existing_claims")
            print(f"📝 Identifier: {identifier}, Type: {search_type}")
            
            if search_type == 'id':
                claims = LiveOnlineClaim.objects.filter(
                    models.Q(id_number=identifier) |
                    models.Q(id_number_alt=identifier)
                ).distinct()
                
                if claims.count() == 0:
                    stripped_id = identifier.lstrip('0')
                    if stripped_id != identifier:
                        claims = LiveOnlineClaim.objects.filter(
                            models.Q(id_number=stripped_id) |
                            models.Q(id_number_alt=stripped_id)
                        ).distinct()
            elif search_type == 'passport':
                claims = LiveOnlineClaim.objects.filter(
                    models.Q(passport_no=identifier) |
                    models.Q(passport_no__icontains=identifier)
                )
            elif search_type == 'claim_no':
                claims = LiveOnlineClaim.objects.filter(
                    models.Q(claim_no=identifier) |
                    models.Q(claim_no__icontains=identifier)
                )
            else:
                return []
            
            print(f"📊 Found {claims.count()} claims")
            
            results = []
            for claim in claims:
                results.append({
                    'claim_no': claim.claim_no,
                    'claimant_name': claim.claimant_name,
                    'id_number': claim.id_number,
                    'id_number_alt': claim.id_number_alt,
                    'passport_no': claim.passport_no,
                    'claimant_phone': claim.claimant_phone,
                    'claimant_email': claim.claimant_email,
                    'amount': float(claim.amount) if claim.amount else 0,
                    'status': claim.status,
                    'payment_category': claim.payment_category,
                    'bank_name': claim.bank_name,
                    'bank_account_no': claim.bank_account_no,
                    'mpesa_mobile_no': claim.mpesa_mobile_no,
                    'category': claim.category,
                    'sub_category': claim.sub_category,
                    'claim_type': claim.claim_type,
                    'agent_name': claim.agent_name,
                    'asset_no': claim.asset_no,
                    'asset_type': claim.asset_type,
                    'created_at': claim.created_at.isoformat() if claim.created_at else None,
                    'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
                })
            
            return results
            
        except Exception as e:
            print(f"❌ Error searching claims: {e}")
            traceback.print_exc()
            return []
    
    @staticmethod
    def search_claims_universal(identifier):
        """Universal search for claims by National ID, Passport, or Claim Number"""
        try:
            print(f"🔍 LiveDatabaseService.search_claims_universal")
            print(f"📝 Identifier: {identifier}")
            
            claims = LiveOnlineClaim.objects.filter(
                models.Q(id_number=identifier) |
                models.Q(id_number_alt=identifier) |
                models.Q(id_number__contains=identifier) |
                models.Q(id_number_alt__contains=identifier) |
                models.Q(claim_no=identifier) |
                models.Q(claim_no__icontains=identifier) |
                models.Q(passport_no=identifier) |
                models.Q(passport_no__icontains=identifier)
            ).distinct()
            
            if claims.count() == 0:
                stripped_id = identifier.lstrip('0')
                if stripped_id != identifier:
                    claims = LiveOnlineClaim.objects.filter(
                        models.Q(id_number=stripped_id) |
                        models.Q(id_number_alt=stripped_id)
                    ).distinct()
            
            print(f"📊 Universal search found {claims.count()} claims")
            
            results = []
            for claim in claims:
                results.append({
                    'claim_no': claim.claim_no,
                    'claimant_name': claim.claimant_name,
                    'id_number': claim.id_number,
                    'id_number_alt': claim.id_number_alt,
                    'passport_no': claim.passport_no,
                    'claimant_phone': claim.claimant_phone,
                    'claimant_email': claim.claimant_email,
                    'amount': float(claim.amount) if claim.amount else 0,
                    'status': claim.status,
                    'payment_category': claim.payment_category,
                    'bank_name': claim.bank_name,
                    'bank_account_no': claim.bank_account_no,
                    'mpesa_mobile_no': claim.mpesa_mobile_no,
                    'category': claim.category,
                    'sub_category': claim.sub_category,
                    'claim_type': claim.claim_type,
                    'agent_name': claim.agent_name,
                    'asset_no': claim.asset_no,
                    'asset_type': claim.asset_type,
                    'description': claim.description,
                    'created_at': claim.created_at.isoformat() if claim.created_at else None,
                    'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
                })
            
            return results
            
        except Exception as e:
            print(f"❌ Error in universal search: {e}")
            traceback.print_exc()
            return []

    # ==================== PUSH TO LIVE METHODS ====================
    
    @staticmethod
    def push_claim_to_live(claim_id):
        """
        Push a single claim from the default database to the live MSSQL database
        
        Args:
            claim_id: The ID of the claim in the default database
            
        Returns:
            dict: Success status and message
        """
        try:
            logger.info(f"Pushing claim {claim_id} to live database")
            
            # Get the claim from default database
            claim = Claim.objects.filter(id=claim_id, status__in=['Pending', 'Under_Review']).first()
            
            if not claim:
                return {
                    'success': False,
                    'message': f'Claim {claim_id} not found or not in review status'
                }
            
            original_claim_no = claim.no
            
            # Generate a new claim number for MSSQL
            new_claim_no = LiveDatabaseService.generate_claim_number()
            logger.info(f"Generated new claim number: {new_claim_no} (original: {original_claim_no})")
            
            # Prepare claim data with new number
            claim_data = {
                'claim_no': new_claim_no,
                'document_date': claim.document_date or timezone.now().date(),
                'processing_date': claim.processing_date or timezone.now().date(),
                'category': claim.category or 'Original_Owner',
                'sub_category': claim.sub_category or '',
                'agent_name': claim.agent_name or '',
                'claim_type': claim.claim_type or 'Cash',
                'claimant_name': claim.name or '',
                'claimant_id': claim.id_number or '',
                'claimant_phone': claim.phone_no or '',
                'claimant_email': claim.e_mail or '',
                'amount': float(claim.amount) if claim.amount else 0,
                'status': 'Pending',
                'payment_category': claim.payment_category or '',
                'bank_name': claim.bank_name or '',
                'bank_account_no': claim.bank_account_no or '',
                'mpesa_mobile_no': claim.mpesa_mobile_no or '',
                'claimant_passport': claim.passport_no or '',
                'gender': claim.gender or '',
                'claim_origin': claim.claim_origin or '',
                'residence': claim.residence or '',
                'address': claim.address or '',
                'post_code': claim.post_code or '',
                'county': claim.county or '',
                'city': claim.city or '',
                'internal_remarks': claim.internal_remarks or '',
            }
            
            # Get claim assets
            claim_assets = ClaimAsset.objects.filter(claim=claim)
            claim_lines_data = []
            for asset in claim_assets:
                claim_lines_data.append({
                    'asset_no': asset.asset_no or '',
                    'asset_type': asset.asset_type or '',
                    'description': asset.description or '',
                    'holder_name': asset.holder_name or '',
                    'value': float(asset.value) if asset.value else 0,
                })
            
            # Check if claim already exists in live database with original or new number
            existing_claim = LiveOnlineClaim.objects.filter(claim_no=new_claim_no).first()
            if existing_claim:
                # If new number exists, generate another one
                new_claim_no = LiveDatabaseService.generate_claim_number()
                claim_data['claim_no'] = new_claim_no
                logger.info(f"Generated another new claim number: {new_claim_no}")
            
            # Create the claim in live database
            result = LiveDatabaseService.create_new_claim(claim_data, claim_lines_data)
            
            if result['success']:
                # Update the claim with the new number
                claim.no = new_claim_no
                claim.status = 'Under_Review'
                claim.save(update_fields=['no', 'status'])
                
                return {
                    'success': True,
                    'claim_no': new_claim_no,
                    'original_claim_no': original_claim_no,
                    'message': f'Claim {original_claim_no} pushed with new number {new_claim_no}'
                }
            else:
                # If insertion fails, try with a different format
                logger.warning(f"First attempt failed: {result.get('message')}")
                
                # Try with CLM prefix (alternate format)
                import time
                timestamp = str(int(time.time()))[-8:]
                random_suffix = str(random.randint(100, 999))
                alt_claim_no = f"CLM-{timestamp}-{random_suffix}"
                
                # Ensure uniqueness
                while LiveOnlineClaim.objects.filter(claim_no=alt_claim_no).exists():
                    random_suffix = str(random.randint(100, 999))
                    alt_claim_no = f"CLM-{timestamp}-{random_suffix}"
                
                claim_data['claim_no'] = alt_claim_no
                result = LiveDatabaseService.create_new_claim(claim_data, claim_lines_data)
                
                if result['success']:
                    claim.no = alt_claim_no
                    claim.status = 'Under_Review'
                    claim.save(update_fields=['no', 'status'])
                    
                    return {
                        'success': True,
                        'claim_no': alt_claim_no,
                        'original_claim_no': original_claim_no,
                        'message': f'Claim {original_claim_no} pushed with new number {alt_claim_no} (CLM format)'
                    }
                
                return {
                    'success': False,
                    'claim_no': original_claim_no,
                    'message': f'Failed to push claim: {result.get("message", "Unknown error")}'
                }
            
        except Exception as e:
            error_msg = str(e)
            error_traceback = traceback.format_exc()
            logger.error(f"Error pushing claim to live database: {error_msg}")
            logger.error(f"Traceback: {error_traceback}")
            return {
                'success': False,
                'message': error_msg
            }
    
    @staticmethod
    def create_new_claim(claim_data, claim_lines_data):
        """Insert a new claim into the live online claims table"""
        
        claim_no = claim_data.get('claim_no')
        
        if not claim_no:
            return {
                'success': False,
                'message': 'Claim number is required'
            }
        
        # Check if claim number already exists in live database
        existing = LiveOnlineClaim.objects.filter(claim_no=claim_no).first()
        if existing:
            try:
                status_value = claim_data.get('status', 'Pending')
                status_id = LiveDatabaseService.STATUS_MAPPING.get(status_value, 1)
                
                with connections['ereunify'].cursor() as cursor:
                    cursor.execute("""
                        UPDATE [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                        SET [Status] = %s, [$systemModifiedAt] = %s
                        WHERE [No_] = %s
                    """, [status_id, timezone.now(), claim_no])
                    
                    if cursor.rowcount > 0:
                        return {
                            'success': True,
                            'claim_no': claim_no,
                            'message': 'Claim status updated successfully'
                        }
            except Exception as e:
                logger.warning(f"Could not update existing claim: {e}")
            
            return {
                'success': False,
                'claim_no': claim_no,
                'message': f'Claim {claim_no} already exists in live database'
            }
        
        # Convert mappings
        category_id = LiveDatabaseService.CATEGORY_MAPPING.get(
            claim_data.get('category', 'Original_Owner'), 1
        )
        claim_type_id = LiveDatabaseService.CLAIM_TYPE_MAPPING.get(
            claim_data.get('claim_type', 'Cash'), 1
        )
        status_id = LiveDatabaseService.STATUS_MAPPING.get(
            claim_data.get('status', 'Pending'), 1
        )
        payment_category_id = LiveDatabaseService.PAYMENT_CATEGORY_MAPPING.get(
            claim_data.get('payment_category', ''), 1
        )
        gender_value = LiveDatabaseService.GENDER_MAPPING.get(
            claim_data.get('gender', ''), 0
        )
        
        # Map claim origin
        claim_origin_value = claim_data.get('claim_origin', '')
        if isinstance(claim_origin_value, str):
            claim_origin_id = LiveDatabaseService.CLAIM_ORIGIN_MAPPING.get(claim_origin_value, 0)
        else:
            claim_origin_id = int(claim_origin_value) if claim_origin_value else 0
        
        # Sub category
        sub_category_value = claim_data.get('sub_category', '')
        if isinstance(sub_category_value, str):
            sub_category_id = LiveDatabaseService.SUB_CATEGORY_MAPPING.get(sub_category_value, 0)
        elif isinstance(sub_category_value, int):
            sub_category_id = sub_category_value
        else:
            sub_category_id = 0
        
        # Dates
        document_date = LiveDatabaseService.get_safe_date(claim_data.get('document_date'))
        processing_date = LiveDatabaseService.get_safe_date(claim_data.get('processing_date'))
        
        # Truncate claim number to 15 characters (SQL Server No_ column limit)
        claim_no_truncated = LiveDatabaseService.safe_string(claim_no, 15)
        
        with connections['ereunify'].cursor() as cursor:
            try:
                with transaction.atomic(using='ereunify'):
                    insert_claim_sql = """
                        INSERT INTO [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1] (
                            [No_],
                            [Document Date],
                            [Processing Date],
                            [Category],
                            [Sub Category],
                            [Agent Name],
                            [Claim Type],
                            [Name],
                            [ID Number],
                            [Phone No_],
                            [E-Mail],
                            [Value],
                            [Status],
                            [Payment Category],
                            [Bank Name],
                            [Bank Account No_],
                            [Mpesa Mobile No_],
                            [Passport No_],
                            [$systemCreatedAt],
                            [$systemModifiedAt]
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """
                    
                    cursor.execute(insert_claim_sql, [
                        claim_no_truncated,
                        document_date,
                        processing_date,
                        category_id,
                        sub_category_id,
                        LiveDatabaseService.safe_string(claim_data.get('agent_name', ''), 100),
                        claim_type_id,
                        LiveDatabaseService.safe_string(claim_data.get('claimant_name', ''), 200),
                        LiveDatabaseService.safe_string(claim_data.get('claimant_id', ''), 20),
                        LiveDatabaseService.safe_string(claim_data.get('claimant_phone', ''), 20),
                        LiveDatabaseService.safe_string(claim_data.get('claimant_email', ''), 100),
                        float(claim_data.get('amount', 0)),
                        status_id,
                        payment_category_id,
                        LiveDatabaseService.safe_string(claim_data.get('bank_name', ''), 100),
                        LiveDatabaseService.safe_string(claim_data.get('bank_account_no', ''), 30),
                        LiveDatabaseService.safe_string(claim_data.get('mpesa_mobile_no', ''), 20),
                        LiveDatabaseService.safe_string(claim_data.get('claimant_passport', ''), 20),
                        timezone.now(),
                        timezone.now(),
                    ])
                    
                    # Insert claim lines
                    for idx, line in enumerate(claim_lines_data, 1):
                        insert_line_sql = """
                            INSERT INTO [UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1] (
                                [No_],
                                [Line No_],
                                [Asset No_],
                                [Asset Type],
                                [Description],
                                [Holder Name]
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s
                            )
                        """
                        
                        cursor.execute(insert_line_sql, [
                            claim_no_truncated,
                            idx,
                            LiveDatabaseService.safe_string(line.get('asset_no', ''), 50),
                            LiveDatabaseService.safe_string(line.get('asset_type', ''), 50),
                            LiveDatabaseService.safe_string(line.get('description', ''), 500),
                            LiveDatabaseService.safe_string(line.get('holder_name', ''), 200),
                        ])
                    
                    return {
                        'success': True,
                        'claim_no': claim_no_truncated,
                        'message': 'Claim created successfully'
                    }
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Error creating claim: {error_msg}")
                traceback.print_exc()
                
                # If the error is about duplicate key, try with a different number
                if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                    # Generate a new number and retry
                    new_no = LiveDatabaseService.generate_claim_number()
                    logger.info(f"Retrying with new claim number: {new_no}")
                    claim_data['claim_no'] = new_no
                    return LiveDatabaseService.create_new_claim(claim_data, claim_lines_data)
                
                return {
                    'success': False,
                    'message': error_msg
                }
    
    @staticmethod
    def push_pending_claims_to_live():
        """
        Push all pending claims from the default database to the live MSSQL database
        
        Returns:
            dict: Summary of pushed claims
        """
        try:
            logger.info("Starting push of pending claims to live database")
            
            claims = Claim.objects.filter(status__in=['Pending', 'Under_Review'])
            
            if not claims.exists():
                return {
                    'success': True,
                    'message': 'No pending claims to push',
                    'pushed': 0,
                    'failed': 0,
                    'skipped': 0,
                    'details': []
                }
            
            results = []
            pushed_count = 0
            failed_count = 0
            skipped_count = 0
            
            for claim in claims:
                # Check if already exists in live database
                existing = LiveOnlineClaim.objects.filter(claim_no=claim.no).first()
                if existing:
                    skipped_count += 1
                    results.append({
                        'claim_no': claim.no,
                        'status': 'skipped',
                        'message': 'Already exists in live database'
                    })
                    continue
                
                # Push the claim
                result = LiveDatabaseService.push_claim_to_live(claim.id)
                
                if result['success']:
                    pushed_count += 1
                else:
                    failed_count += 1
                
                results.append({
                    'claim_no': claim.no,
                    'status': 'success' if result['success'] else 'failed',
                    'message': result.get('message', '')
                })
            
            return {
                'success': True,
                'message': f'Push completed: {pushed_count} pushed, {failed_count} failed, {skipped_count} skipped',
                'pushed': pushed_count,
                'failed': failed_count,
                'skipped': skipped_count,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"Error pushing pending claims: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'message': str(e),
                'pushed': 0,
                'failed': 0,
                'skipped': 0,
                'details': []
            }
    
    @staticmethod
    def push_claims_by_ids(claim_ids):
        """
        Push specific claims by their IDs to the live database
        
        Args:
            claim_ids: List of claim IDs to push
            
        Returns:
            dict: Summary of pushed claims
        """
        try:
            logger.info(f"Pushing claims by IDs: {claim_ids}")
            
            claims = Claim.objects.filter(id__in=claim_ids)
            
            if not claims.exists():
                return {
                    'success': False,
                    'message': 'No claims found with the provided IDs',
                    'pushed': 0,
                    'failed': 0,
                    'details': []
                }
            
            results = []
            pushed_count = 0
            failed_count = 0
            skipped_count = 0
            
            for claim in claims:
                # Check if already exists in live database
                existing = LiveOnlineClaim.objects.filter(claim_no=claim.no).first()
                if existing:
                    skipped_count += 1
                    results.append({
                        'claim_no': claim.no,
                        'status': 'skipped',
                        'message': 'Already exists in live database'
                    })
                    continue
                
                result = LiveDatabaseService.push_claim_to_live(claim.id)
                
                if result['success']:
                    pushed_count += 1
                else:
                    failed_count += 1
                
                results.append({
                    'claim_no': claim.no,
                    'status': 'success' if result['success'] else 'failed',
                    'message': result.get('message', '')
                })
            
            return {
                'success': True,
                'message': f'Push completed: {pushed_count} pushed, {failed_count} failed, {skipped_count} skipped',
                'pushed': pushed_count,
                'failed': failed_count,
                'skipped': skipped_count,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"Error pushing claims by IDs: {e}")
            return {
                'success': False,
                'message': str(e),
                'pushed': 0,
                'failed': 0,
                'details': []
            }
    
    @staticmethod
    def sync_claim_status(claim_no, live_status):
        """
        Sync claim status from live database back to default database
        
        Args:
            claim_no: The claim number
            live_status: The status in the live database
        
        Returns:
            dict: Success status and message
        """
        try:
            claim = Claim.objects.filter(no=claim_no).first()
            if not claim:
                return {
                    'success': False,
                    'message': f'Claim {claim_no} not found in default database'
                }
            
            # Update the claim status
            claim.status = live_status
            claim.save(update_fields=['status'])
            
            return {
                'success': True,
                'claim_no': claim_no,
                'status': live_status,
                'message': f'Claim {claim_no} status synced to {live_status}'
            }
            
        except Exception as e:
            logger.error(f"Error syncing claim status: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    @staticmethod
    def get_claim_status(claim_no):
        """Get claim status from the database"""
        with connections['ereunify'].cursor() as cursor:
            try:
                cursor.execute("""
                    SELECT [Status], [$systemModifiedAt], [Processing Date]
                    FROM [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    WHERE [No_] = %s
                """, [claim_no])
                
                row = cursor.fetchone()
                
                if row:
                    # Convert status integer back to string for response
                    status_map = {v: k for k, v in LiveDatabaseService.STATUS_MAPPING.items()}
                    status_string = status_map.get(row[0], 'Pending')
                    
                    return {
                        'success': True,
                        'claim_no': claim_no,
                        'status': status_string,
                        'updated_at': row[1],
                        'processing_date': row[2],
                        'message': 'Status retrieved successfully'
                    }
                else:
                    return {
                        'success': False,
                        'message': f'Claim {claim_no} not found'
                    }
            except Exception as e:
                logger.error(f"Error getting claim status: {e}")
                return {
                    'success': False,
                    'message': str(e)
                }

    @staticmethod
    def get_asset_by_no(asset_no):
        """Get a single asset by its asset number"""
        try:
            asset = LiveUnclaimedAsset.objects.filter(no=asset_no).first()
            if not asset:
                return None
            
            return {
                'asset_no': asset.no,
                'holder_name': asset.holder_name,
                'owner_name': asset.get_full_name(),
                'id_number': asset.id_number,
                'asset_type': asset.get_asset_type_display_name(),
                'source': asset.get_source_display_name(),
                'amount': str(asset.amount_due_to_owner) if asset.amount_due_to_owner else "0",
                'status': asset.get_status_display_name(),
                'is_claimable': asset.is_claimable(),
            }
        except Exception as e:
            logger.error(f"Error getting asset: {e}")
            return None
    
    @staticmethod
    def get_claim_by_no(claim_no):
        """Get a claim by its claim number"""
        try:
            claim = LiveOnlineClaim.objects.filter(claim_no=claim_no).first()
            if not claim:
                return None
            
            claim_lines = LiveOnlineClaimLine.objects.filter(claim=claim)
            
            return {
                'claim_no': claim.claim_no,
                'claimant_name': claim.claimant_name,
                'id_number': claim.id_number,
                'id_number_alt': claim.id_number_alt,
                'passport_no': claim.passport_no,
                'claimant_phone': claim.claimant_phone,
                'claimant_email': claim.claimant_email,
                'amount': float(claim.amount) if claim.amount else 0,
                'status': claim.status,
                'payment_category': claim.payment_category,
                'bank_name': claim.bank_name,
                'bank_account_no': claim.bank_account_no,
                'mpesa_mobile_no': claim.mpesa_mobile_no,
                'category': claim.category,
                'sub_category': claim.sub_category,
                'claim_type': claim.claim_type,
                'agent_name': claim.agent_name,
                'asset_no': claim.asset_no,
                'asset_type': claim.asset_type,
                'description': claim.description,
                'created_at': claim.created_at.isoformat() if claim.created_at else None,
                'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
                'lines': [
                    {
                        'line_no': line.line_no,
                        'asset_no': line.asset_no,
                        'asset_type': line.asset_type,
                        'asset_value': float(line.asset_value) if line.asset_value else 0,
                        'description': line.description,
                        'holder_name': line.holder_name,
                    }
                    for line in claim_lines
                ]
            }
        except Exception as e:
            logger.error(f"Error getting claim: {e}")
            return None

    @staticmethod
    def update_claim_status(claim_no, status, remarks=''):
        """Update claim status in the live database"""
        if isinstance(status, str):
            status_id = LiveDatabaseService.STATUS_MAPPING.get(status)
            if status_id is None:
                return {
                    'success': False,
                    'message': f'Invalid status: {status}'
                }
        else:
            status_id = status
        
        with connections['ereunify'].cursor() as cursor:
            try:
                update_sql = """
                    UPDATE [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    SET [Status] = %s, 
                        [$systemModifiedAt] = %s,
                        [Internal Remarks] = CASE 
                            WHEN %s IS NOT NULL AND %s != '' 
                            THEN CONCAT([Internal Remarks], CHAR(13), CHAR(10), %s)
                            ELSE [Internal Remarks]
                        END
                    WHERE [No_] = %s
                """
                
                cursor.execute(update_sql, [
                    status_id,
                    timezone.now(),
                    remarks, remarks, remarks,
                    claim_no
                ])
                
                if cursor.rowcount > 0:
                    # Also sync back to default database if status is 'Rejected' or 'Approved'
                    if status in ['Rejected', 'Approved', 'Paid', 'Completed']:
                        LiveDatabaseService.sync_claim_status(claim_no, status)
                    
                    return {
                        'success': True,
                        'claim_no': claim_no,
                        'status': status,
                        'message': f'Claim status updated to {status}'
                    }
                else:
                    return {
                        'success': False,
                        'message': f'Claim {claim_no} not found'
                    }
                    
            except Exception as e:
                logger.error(f"Error updating claim status: {e}")
                return {
                    'success': False,
                    'message': str(e)
                }
