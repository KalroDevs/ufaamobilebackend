# apps/live_operations/services.py
import logging
import random
import time
import traceback

from django.db import connections, transaction
from django.utils import timezone

from apps.claims.models import Claim, ClaimAsset

logger = logging.getLogger(__name__)


class LiveDatabaseService:
    """Service for live database operations using raw SQL only."""

    # ==================== DATABASE CONFIGURATION ====================

    DATABASE_NAME = "UFAAv24"
    DATABASE_SCHEMA = "dbo"

    ONLINE_CLAIM_TABLE_NAME = (
        "UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )
    UNCLAIMED_ASSET_TABLE_NAME = (
        "UFAA TRUST FUND$Unclaimed Asset$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )

    ONLINE_CLAIM_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ONLINE_CLAIM_TABLE_NAME}]"
    )
    UNCLAIMED_ASSET_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{UNCLAIMED_ASSET_TABLE_NAME}]"
    )

    # ==================== MAPPINGS ====================

    CATEGORY_MAPPING = {
        "Original_Owner": 1,
        "Beneficiary": 2,
        "Business_Entity": 3,
        "Agent_of_the_Owner": 4,
        "": 0,
    }

    CLAIM_TYPE_MAPPING = {
        "Cash": 1,
        "Non_Cash": 2,
        "Both": 3,
        "": 1,
    }

    SUB_CATEGORY_MAPPING = {
        "administrator": 1,
        "public_trustee": 2,
        "nominee": 3,
        "executor": 4,
        "guardian": 5,
        "legal_representative": 6,
        "Adult": 10,
        "Minor": 11,
        "sole_proprietorship": 20,
        "partnership": 21,
        "limited_liability": 22,
        "sacco": 23,
        "self_help_group": 24,
        "none": 0,
        "not_applicable": 0,
        "": 0,
    }

    STATUS_MAPPING = {
        "Draft": 0,
        "Pending": 1,
        "Under_Review": 2,
        "In_Progress": 3,
        "Processing": 4,
        "Approved": 5,
        "Rejected": 6,
        "Paid": 7,
        "Completed": 8,
        "Archived": 9,
        "Cancelled": 10,
    }

    PAYMENT_CATEGORY_MAPPING = {
        "Mpesa": 1,
        "Local_Bank": 2,
        "International": 3,
        "Bank Transfer": 4,
        "Cheque": 5,
        "": 1,
    }

    CLAIM_ORIGIN_MAPPING = {
        "OnlinePortal": 1,
        "Android_Mobile_App": 2,
        "iOS_Mobile_App": 3,
        "Reception": 4,
        "Emails": 5,
        "Reunification_Clinics": 6,
        "Huduma": 7,
        "Registrars": 8,
        "": 0,
    }

    GENDER_MAPPING = {
        "Male": 1,
        "Female": 2,
        "Other": 3,
        "M": 1,
        "F": 2,
        "O": 3,
        "": 0,
    }

    # ==================== HELPER METHODS ====================

    @staticmethod
    def safe_string(value, max_length=255):
        if value is None:
            return ""

        value = str(value).strip()

        if len(value) > max_length:
            return value[:max_length]

        return value

    @staticmethod
    def get_safe_date(date_value, fallback=None):
        if date_value is not None:
            return date_value

        if fallback is not None:
            return fallback

        return timezone.now().date()

    @staticmethod
    def quote_identifier(identifier):
        """Quote a SQL Server identifier safely."""
        return f"[{str(identifier).replace(']', ']]')}]"

    @staticmethod
    def get_table_columns(table_name):
        """Return the actual SQL Server column names for a table."""
        sql = f"""
            SELECT COLUMN_NAME
            FROM [{LiveDatabaseService.DATABASE_NAME}].INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """

        with connections["ereunify"].cursor() as cursor:
            cursor.execute(
                sql,
                [
                    LiveDatabaseService.DATABASE_SCHEMA,
                    table_name,
                ],
            )
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def resolve_column(table_name, candidates, required=True):
        """Return the first candidate column found in the target table."""
        columns = LiveDatabaseService.get_table_columns(table_name)
        lookup = {column.lower(): column for column in columns}

        for candidate in candidates:
            matched = lookup.get(candidate.lower())
            if matched:
                return matched

        if required:
            raise ValueError(
                f"None of the expected columns {list(candidates)} exist in "
                f"{LiveDatabaseService.DATABASE_NAME}."
                f"{LiveDatabaseService.DATABASE_SCHEMA}."
                f"{table_name}. Available columns: {columns}"
            )

        return None

    @staticmethod
    def validate_live_schema():
        """Validate all columns required for inserting a claim."""
        header_columns = LiveDatabaseService.get_table_columns(
            LiveDatabaseService.ONLINE_CLAIM_TABLE_NAME
        )

        if "No_" not in header_columns:
            raise ValueError(
                "The Online Claim table does not contain the expected [No_] "
                f"column. Available columns: {header_columns}"
            )

        return {
            "header_claim_no_column": "No_",
            "claim_line_columns": {},
        }

    @staticmethod
    def claim_exists_in_live(claim_no):
        """Check whether a claim number exists in the live database."""
        if not claim_no:
            return False

        claim_no = LiveDatabaseService.safe_string(claim_no, 15)

        try:
            with connections["ereunify"].cursor() as cursor:
                cursor.execute(
                    f"""
                        SELECT COUNT(*)
                        FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                        WHERE [No_] = %s
                    """,
                    [claim_no],
                )

                return cursor.fetchone()[0] > 0

        except Exception:
            logger.exception(
                "Error checking whether claim %s exists in the live database",
                claim_no,
            )
            raise

    # ==================== SEARCH METHODS ====================

    @staticmethod
    def search_unclaimed_assets(identifier, search_type="id"):
        """Search for unclaimed assets in the live Business Central table."""
        identifier = LiveDatabaseService.safe_string(identifier, 255)
        search_type = LiveDatabaseService.safe_string(search_type, 20).lower()

        if not identifier:
            raise ValueError("Search identifier is required")

        logger.info(
            "Searching live unclaimed assets. Identifier=%r, search_type=%s",
            identifier,
            search_type,
        )

        try:
            with connections["ereunify"].cursor() as cursor:
                selected_columns = """
                    [No_],
                    [Name],
                    [Middle Name],
                    [Last Name],
                    [Holder Name],
                    [Owner Name],
                    [ID Number],
                    [Passport No_],
                    [CDS Account No_],
                    [CDS No_],
                    [Asset Type],
                    [Source],
                    [Status],
                    [Description_],
                    [Amount Due to Owner],
                    [Amount LCY],
                    [Date of Birth],
                    [Owners Postal Address],
                    [Owners City_Town],
                    [Owners Telephnone No_],
                    [County Name]
                """

                if search_type == "id":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE LTRIM(
                            RTRIM(CAST([ID Number] AS VARCHAR(100)))
                        ) = %s
                    """
                    params = [identifier]

                elif search_type == "passport":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE LTRIM(
                            RTRIM(CAST([Passport No_] AS VARCHAR(100)))
                        ) = %s
                    """
                    params = [identifier]

                elif search_type == "cds":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE LTRIM(
                            RTRIM(CAST([CDS Account No_] AS VARCHAR(100)))
                        ) = %s
                           OR LTRIM(
                               RTRIM(CAST([CDS No_] AS VARCHAR(100)))
                           ) = %s
                    """
                    params = [identifier, identifier]

                elif search_type in {"name", "owner", "holder"}:
                    search_pattern = f"%{identifier}%"
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE [Name] LIKE %s
                           OR [Middle Name] LIKE %s
                           OR [Last Name] LIKE %s
                           OR [Holder Name] LIKE %s
                           OR [Owner Name] LIKE %s
                           OR [Search Name] LIKE %s
                    """
                    params = [search_pattern] * 6

                else:
                    raise ValueError(
                        "Unsupported search type. Expected one of: "
                        "id, passport, cds, name, owner, holder"
                    )

                cursor.execute(sql, params)

                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                results = []

                for row in rows:
                    asset = dict(zip(columns, row))

                    owner_parts = [
                        asset.get("Name"),
                        asset.get("Middle Name"),
                        asset.get("Last Name"),
                    ]
                    owner_name = " ".join(
                        str(part).strip()
                        for part in owner_parts
                        if part
                    ).strip()

                    if not owner_name:
                        owner_name = (
                            asset.get("Owner Name")
                            or asset.get("Holder Name")
                            or "N/A"
                        )

                    asset_type = asset.get("Asset Type")
                    is_cash = asset_type == 1

                    source_map = {
                        1: "Cash",
                        2: "Shares",
                        3: "Safe Deposit",
                    }

                    status_map = {
                        1: "Unclaimed",
                        2: "In Process",
                        3: "Claimed",
                        4: "Archived",
                    }

                    amount = (
                        asset.get("Amount Due to Owner")
                        or asset.get("Amount LCY")
                        or 0
                    )

                    results.append(
                        {
                            "id": asset.get("No_"),
                            "asset_no": asset.get("No_"),
                            "holder_name": asset.get("Holder Name") or "",
                            "owner_name": owner_name,
                            "id_number": asset.get("ID Number") or "",
                            "passport_no": asset.get("Passport No_") or "",
                            "cds_account_no": (
                                asset.get("CDS Account No_")
                                or asset.get("CDS No_")
                                or ""
                            ),
                            "asset_type": "Cash" if is_cash else "Non-Cash",
                            "asset_type_code": asset_type,
                            "is_cash": is_cash,
                            "source": source_map.get(
                                asset.get("Source"),
                                "Other",
                            ),
                            "source_code": asset.get("Source"),
                            "amount": str(amount),
                            "numeric_amount": float(amount),
                            "status": status_map.get(
                                asset.get("Status"),
                                "Unknown",
                            ),
                            "status_code": asset.get("Status"),
                            "description": asset.get("Description_") or "",
                            "date_of_birth": (
                                str(asset.get("Date of Birth"))
                                if asset.get("Date of Birth")
                                else ""
                            ),
                            "postal_address": (
                                asset.get("Owners Postal Address") or ""
                            ),
                            "city_town": asset.get("Owners City_Town") or "",
                            "telephone": (
                                asset.get("Owners Telephnone No_") or ""
                            ),
                            "county": asset.get("County Name") or "",
                            "is_claimable": asset.get("Status") == 1,
                        }
                    )

                logger.info("Found %s unclaimed asset(s)", len(results))
                return results

        except ValueError:
            logger.exception(
                "Invalid live asset search request. Identifier=%r, "
                "search_type=%s",
                identifier,
                search_type,
            )
            raise

        except Exception as exc:
            logger.exception(
                "Error searching live assets. Identifier=%r, search_type=%s",
                identifier,
                search_type,
            )
            raise RuntimeError(
                f"Live asset database search failed: {exc}"
            ) from exc

    # ==================== PUSH TO LIVE METHODS ====================

    @staticmethod
    def push_claim_to_live(claim_id):
        """
        Push one pending or under-review claim to the live database.
        Uses the existing claim number and sets Location Source = 1.
        """
        try:
            logger.info("Pushing claim ID %s to the live database", claim_id)

            claim = (
                Claim.objects.filter(
                    id=claim_id,
                    status__in=["Pending", "Under_Review"],
                )
                .first()
            )

            if not claim:
                return {
                    "success": False,
                    "message": (
                        f"Claim {claim_id} was not found or is not in a "
                        "pushable status"
                    ),
                }

            # Use the existing claim number
            claim_no = claim.no

            if not claim_no:
                return {
                    "success": False,
                    "message": f"Claim {claim_id} does not have a claim number",
                }

            logger.info(
                "Pushing claim %s to live database using existing claim number",
                claim_no,
            )

            # Check if claim already exists in live database
            if LiveDatabaseService.claim_exists_in_live(claim_no):
                return {
                    "success": False,
                    "message": f"Claim {claim_no} already exists in live database",
                    "claim_no": claim_no,
                    "status": "already_exists",
                }

            # Prepare claim data
            claim_data = {
                "claim_no": claim_no,
                "document_date": (
                    claim.document_date or timezone.now().date()
                ),
                "processing_date": (
                    claim.processing_date or timezone.now().date()
                ),
                "category": claim.category or "Original_Owner",
                "sub_category": claim.sub_category or "",
                "agent_name": claim.agent_name or "",
                "claim_type": claim.claim_type or "Cash",
                "claimant_name": claim.name or "",
                "claimant_id": claim.id_number or "",
                "claimant_phone": claim.phone_no or "",
                "claimant_email": claim.e_mail or "",
                "amount": float(claim.amount) if claim.amount else 0,
                "status": "Pending",
                "payment_category": claim.payment_category or "",
                "bank_name": claim.bank_name or "",
                "bank_account_no": claim.bank_account_no or "",
                "mpesa_mobile_no": claim.mpesa_mobile_no or "",
                "claimant_passport": claim.passport_no or "",
                "gender": claim.gender or "",
                "claim_origin": claim.claim_origin or "",
                "residence": claim.residence or "",
                "address": claim.address or "",
                "post_code": claim.post_code or "",
                "county": claim.county or "",
                "city": claim.city or "",
                "internal_remarks": claim.internal_remarks or "",
                "location_source": 1,  # Set Location Source to 1
            }

            # Get claim assets
            claim_assets = ClaimAsset.objects.filter(claim=claim)
            claim_lines_data = []

            for asset in claim_assets:
                claim_lines_data.append(
                    {
                        "asset_no": asset.asset_no or "",
                        "asset_type": asset.asset_type or "",
                        "description": asset.description or "",
                        "holder_name": asset.holder_name or "",
                        "value": float(asset.value) if asset.value else 0,
                    }
                )

            # Create the claim in live database
            result = LiveDatabaseService.create_new_claim(
                claim_data,
                claim_lines_data,
            )

            if result.get("success"):
                # Update local claim status
                claim.status = "Under_Review"
                claim.save(update_fields=["status"])

                return {
                    "success": True,
                    "claim_no": claim.no,
                    "message": (
                        f"Claim {claim.no} was successfully pushed to live"
                    ),
                }
            else:
                return {
                    "success": False,
                    "claim_no": claim.no,
                    "stage": result.get("stage"),
                    "message": (
                        f"Failed to push claim: "
                        f"{result.get('message', 'Unknown error')}"
                    ),
                }

        except Exception as exc:
            logger.exception(
                "Error pushing claim ID %s to the live database",
                claim_id,
            )

            return {
                "success": False,
                "message": str(exc),
            }

    @staticmethod
    def create_new_claim(claim_data, claim_lines_data):
        """
        Insert a claim and its lines into the live database.
        Uses existing claim number and sets Location Source = 1.
        """
        claim_no = claim_data.get("claim_no")

        if not claim_no:
            return {
                "success": False,
                "message": "Claim number is required",
            }

        claim_no_truncated = LiveDatabaseService.safe_string(
            claim_no,
            15,
        )

        # Check if claim already exists
        try:
            with connections["ereunify"].cursor() as cursor:
                cursor.execute(
                    f"""
                        SELECT COUNT(*)
                        FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                        WHERE [No_] = %s
                    """,
                    [claim_no_truncated],
                )
                exists = cursor.fetchone()[0] > 0

                if exists:
                    return {
                        "success": False,
                        "claim_no": claim_no_truncated,
                        "message": f"Claim {claim_no_truncated} already exists in live database",
                        "status": "already_exists",
                    }
        except Exception as e:
            return {
                "success": False,
                "claim_no": claim_no_truncated,
                "message": f"Error checking claim existence: {str(e)}",
            }

        # Map values
        category_id = LiveDatabaseService.CATEGORY_MAPPING.get(
            claim_data.get("category", "Original_Owner"),
            1,
        )

        claim_type_id = LiveDatabaseService.CLAIM_TYPE_MAPPING.get(
            claim_data.get("claim_type", "Cash"),
            1,
        )

        status_id = LiveDatabaseService.STATUS_MAPPING.get(
            claim_data.get("status", "Pending"),
            1,
        )

        payment_category_id = (
            LiveDatabaseService.PAYMENT_CATEGORY_MAPPING.get(
                claim_data.get("payment_category", ""),
                1,
            )
        )

        gender_value = LiveDatabaseService.GENDER_MAPPING.get(
            claim_data.get("gender", ""),
            0,
        )

        claim_origin_value = claim_data.get("claim_origin", "")
        if isinstance(claim_origin_value, str):
            claim_origin_id = (
                LiveDatabaseService.CLAIM_ORIGIN_MAPPING.get(
                    claim_origin_value,
                    0,
                )
            )
        else:
            claim_origin_id = (
                int(claim_origin_value)
                if claim_origin_value
                else 0
            )

        sub_category_value = claim_data.get("sub_category", "")
        if isinstance(sub_category_value, str):
            sub_category_id = (
                LiveDatabaseService.SUB_CATEGORY_MAPPING.get(
                    sub_category_value,
                    0,
                )
            )
        elif isinstance(sub_category_value, int):
            sub_category_id = sub_category_value
        else:
            sub_category_id = 0

        document_date = LiveDatabaseService.get_safe_date(
            claim_data.get("document_date")
        )
        processing_date = LiveDatabaseService.get_safe_date(
            claim_data.get("processing_date")
        )

        # Location Source - always set to 1
        location_source = claim_data.get("location_source", 1)

        operation_stage = "schema validation"
        try:
            LiveDatabaseService.validate_live_schema()

            with transaction.atomic(using="ereunify"):
                with connections["ereunify"].cursor() as cursor:
                    operation_stage = "inserting claim header"

                    insert_claim_sql = f"""
                        INSERT INTO
                            {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                        (
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
                            [Gender],
                            [Claim Origin],
                            [Residence],
                            [Address],
                            [Post Code],
                            [County],
                            [City],
                            [Internal Remarks],
                            [Location Source],
                            [$systemCreatedAt],
                            [$systemModifiedAt]
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """

                    cursor.execute(
                        insert_claim_sql,
                        [
                            claim_no_truncated,
                            document_date,
                            processing_date,
                            category_id,
                            sub_category_id,
                            LiveDatabaseService.safe_string(
                                claim_data.get("agent_name", ""),
                                100,
                            ),
                            claim_type_id,
                            LiveDatabaseService.safe_string(
                                claim_data.get("claimant_name", ""),
                                200,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("claimant_id", ""),
                                50,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("claimant_phone", ""),
                                20,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("claimant_email", ""),
                                100,
                            ),
                            float(claim_data.get("amount", 0) or 0),
                            status_id,
                            payment_category_id,
                            LiveDatabaseService.safe_string(
                                claim_data.get("bank_name", ""),
                                100,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("bank_account_no", ""),
                                50,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("mpesa_mobile_no", ""),
                                20,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("claimant_passport", ""),
                                50,
                            ),
                            gender_value,
                            claim_origin_id,
                            LiveDatabaseService.safe_string(
                                claim_data.get("residence", ""),
                                50,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("address", ""),
                                255,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("post_code", ""),
                                20,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("county", ""),
                                50,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("city", ""),
                                50,
                            ),
                            LiveDatabaseService.safe_string(
                                claim_data.get("internal_remarks", ""),
                                500,
                            ),
                            location_source,  # Location Source = 1
                            timezone.now(),
                            timezone.now(),
                        ],
                    )

                    logger.info(
                        "Inserted live claim header %s with Location Source = %s",
                        claim_no_truncated,
                        location_source,
                    )

            # Note: Claim lines are disabled for now
            return {
                "success": True,
                "claim_no": claim_no_truncated,
                "message": (
                    f"Claim created successfully with Location Source = {location_source}"
                ),
            }

        except Exception as exc:
            error_message = str(exc)

            logger.exception(
                "Error creating live claim %s during %s: %s",
                claim_no_truncated,
                operation_stage,
                error_message,
            )

            return {
                "success": False,
                "claim_no": claim_no_truncated,
                "stage": operation_stage,
                "message": (
                    f"Database operation failed during "
                    f"{operation_stage}: {error_message}"
                ),
            }

    @staticmethod
    def push_pending_claims_to_live():
        """Push all pending and under-review claims to the live database."""
        try:
            logger.info(
                "Starting push of pending claims to the live database"
            )

            # Validate once before processing the batch
            LiveDatabaseService.validate_live_schema()

            claims = Claim.objects.filter(
                status__in=["Pending", "Under_Review"]
            )

            if not claims.exists():
                return {
                    "success": True,
                    "message": "No pending claims to push",
                    "pushed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "already_exists": 0,
                    "details": [],
                }

            results = []
            pushed_count = 0
            failed_count = 0
            skipped_count = 0
            already_exists_count = 0

            for claim in claims.iterator():
                logger.info(
                    "Processing claim: %s (ID: %s)",
                    claim.no,
                    claim.id,
                )

                # Check if claim exists in live database
                try:
                    exists = (
                        LiveDatabaseService.claim_exists_in_live(
                            claim.no
                        )
                    )
                except Exception as exc:
                    failed_count += 1
                    results.append(
                        {
                            "claim_no": claim.no,
                            "status": "failed",
                            "message": (
                                "Could not check whether claim exists in "
                                f"live database: {exc}"
                            ),
                        }
                    )
                    continue

                if exists:
                    already_exists_count += 1
                    results.append(
                        {
                            "claim_no": claim.no,
                            "status": "already_exists",
                            "message": (
                                "Already exists in live database"
                            ),
                        }
                    )
                    continue

                # Skip claims without a claim number
                if not claim.no:
                    skipped_count += 1
                    results.append(
                        {
                            "claim_no": "N/A",
                            "claim_id": claim.id,
                            "status": "skipped",
                            "message": "Claim does not have a claim number",
                        }
                    )
                    continue

                # Push the claim
                result = LiveDatabaseService.push_claim_to_live(
                    claim.id
                )

                if result.get("success"):
                    pushed_count += 1
                    status = "success"
                else:
                    failed_count += 1
                    status = "failed"

                detail = {
                    "claim_no": claim.no,
                    "status": status,
                    "message": result.get("message", ""),
                }

                if result.get("stage"):
                    detail["stage"] = result["stage"]

                if result.get("claim_no"):
                    detail["live_claim_no"] = result["claim_no"]

                results.append(detail)

            # Prepare summary
            summary = {
                "success": True,
                "message": (
                    f"Push completed: {pushed_count} pushed, "
                    f"{failed_count} failed, "
                    f"{skipped_count} skipped, "
                    f"{already_exists_count} already exist"
                ),
                "pushed": pushed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "already_exists": already_exists_count,
                "details": results,
            }

            # Log failed claims
            if failed_count > 0:
                failed_claims = [d for d in results if d.get("status") == "failed"]
                logger.warning(
                    "Failed claims (%d): %s",
                    len(failed_claims),
                    [d.get("claim_no") for d in failed_claims]
                )

            # Log already existing claims
            if already_exists_count > 0:
                existing_claims = [d for d in results if d.get("status") == "already_exists"]
                logger.warning(
                    "Claims already exist in live (%d): %s",
                    len(existing_claims),
                    [d.get("claim_no") for d in existing_claims]
                )

            return summary

        except Exception as exc:
            logger.exception(
                "Error pushing pending claims to the live database"
            )

            return {
                "success": False,
                "message": str(exc),
                "pushed": 0,
                "failed": 0,
                "skipped": 0,
                "already_exists": 0,
                "details": [],
            }

    @staticmethod
    def push_claims_by_ids(claim_ids):
        """Push specific claims by their IDs."""
        try:
            logger.info(
                "Starting push of %s claims by IDs",
                len(claim_ids)
            )

            results = []
            pushed_count = 0
            failed_count = 0
            skipped_count = 0
            already_exists_count = 0

            for claim_id in claim_ids:
                try:
                    claim = Claim.objects.filter(id=claim_id).first()

                    if not claim:
                        failed_count += 1
                        results.append({
                            "claim_id": claim_id,
                            "status": "failed",
                            "message": "Claim not found",
                        })
                        continue

                    if claim.status not in ["Pending", "Under_Review"]:
                        skipped_count += 1
                        results.append({
                            "claim_no": claim.no,
                            "claim_id": claim.id,
                            "status": "skipped",
                            "message": f"Not in pushable status: {claim.status}",
                        })
                        continue

                    if not claim.no:
                        skipped_count += 1
                        results.append({
                            "claim_no": "N/A",
                            "claim_id": claim.id,
                            "status": "skipped",
                            "message": "Claim does not have a claim number",
                        })
                        continue

                    # Check if already exists
                    if LiveDatabaseService.claim_exists_in_live(claim.no):
                        already_exists_count += 1
                        results.append({
                            "claim_no": claim.no,
                            "status": "already_exists",
                            "message": "Already exists in live database",
                        })
                        continue

                    result = LiveDatabaseService.push_claim_to_live(claim_id)

                    if result.get("success"):
                        pushed_count += 1
                    else:
                        failed_count += 1

                    results.append({
                        "claim_no": claim.no,
                        "claim_id": claim.id,
                        "status": "success" if result.get("success") else "failed",
                        "message": result.get("message", ""),
                    })

                except Exception as e:
                    failed_count += 1
                    results.append({
                        "claim_id": claim_id,
                        "status": "failed",
                        "message": str(e),
                    })

            return {
                "success": True,
                "message": (
                    f"Push completed: {pushed_count} pushed, "
                    f"{failed_count} failed, "
                    f"{skipped_count} skipped, "
                    f"{already_exists_count} already exist"
                ),
                "pushed": pushed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "already_exists": already_exists_count,
                "details": results,
            }

        except Exception as exc:
            logger.exception("Error pushing claims by IDs")
            return {
                "success": False,
                "message": str(exc),
                "pushed": 0,
                "failed": len(claim_ids),
                "skipped": 0,
                "already_exists": 0,
                "details": [],
            }

    @staticmethod
    def sync_claim_status(claim_no, new_status):
        """Sync claim status from live database back to default database."""
        try:
            logger.info(
                "Syncing claim %s status to %s",
                claim_no,
                new_status
            )

            claim = Claim.objects.filter(no=claim_no).first()

            if not claim:
                return {
                    "success": False,
                    "message": f"Claim {claim_no} not found",
                }

            claim.status = new_status
            claim.save(update_fields=["status"])

            return {
                "success": True,
                "message": f"Claim {claim_no} status synced to {new_status}",
            }

        except Exception as e:
            logger.exception("Error syncing claim status")
            return {
                "success": False,
                "message": str(e),
            }
