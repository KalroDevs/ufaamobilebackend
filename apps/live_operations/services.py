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
    ONLINE_CLAIM_LINES_TABLE_NAME = (
        "UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )
    UNCLAIMED_ASSET_TABLE_NAME = (
        "UFAA TRUST FUND$Unclaimed Asset$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )

    ONLINE_CLAIM_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ONLINE_CLAIM_TABLE_NAME}]"
    )
    ONLINE_CLAIM_LINES_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ONLINE_CLAIM_LINES_TABLE_NAME}]"
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

    # Candidate names for the parent claim reference in the claim-lines table.
    CLAIM_LINE_PARENT_COLUMN_CANDIDATES = (
        "Document No_",
        "Claim No_",
        "Online Claim No_",
        "Header No_",
        "No_",
    )

    CLAIM_LINE_NUMBER_COLUMN_CANDIDATES = (
        "Line No_",
        "Document Line No_",
        "Line No",
    )

    CLAIM_LINE_ASSET_NO_COLUMN_CANDIDATES = (
        "Asset No_",
        "Unclaimed Asset No_",
        "Asset No",
    )

    CLAIM_LINE_ASSET_TYPE_COLUMN_CANDIDATES = (
        "Asset Type",
        "Asset Type Code",
    )

    CLAIM_LINE_DESCRIPTION_COLUMN_CANDIDATES = (
        "Description",
        "Description_",
    )

    CLAIM_LINE_HOLDER_NAME_COLUMN_CANDIDATES = (
        "Holder Name",
        "Name",
    )

    CLAIM_LINE_VALUE_COLUMN_CANDIDATES = (
        "Asset Value",
        "Value",
        "Amount",
    )

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
        """
        Quote a SQL Server identifier safely.

        Only identifiers read from INFORMATION_SCHEMA or fixed internal
        candidate lists should be passed to this method.
        """
        return f"[{str(identifier).replace(']', ']]')}]"

    @staticmethod
    def get_table_columns(table_name):
        """
        Return the actual SQL Server column names for a table.

        The query uses INFORMATION_SCHEMA because Business Central tables
        often contain spaces, punctuation and underscores in field names.
        """
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
        """
        Return the first candidate column found in the target table.

        Matching is case-insensitive. The exact database column name is
        returned for use in the generated SQL.
        """
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
        """
        Validate all columns required for inserting a claim and its lines.

        Returns exact claim-line column names so that no invalid-column
        assumptions are made.
        """
        header_columns = LiveDatabaseService.get_table_columns(
            LiveDatabaseService.ONLINE_CLAIM_TABLE_NAME
        )

        if "No_" not in header_columns:
            raise ValueError(
                "The Online Claim table does not contain the expected [No_] "
                f"column. Available columns: {header_columns}"
            )

        claim_line_columns = {
            "parent_claim": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_PARENT_COLUMN_CANDIDATES,
            ),
            "line_number": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_NUMBER_COLUMN_CANDIDATES,
            ),
            "asset_no": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_ASSET_NO_COLUMN_CANDIDATES,
            ),
            "asset_type": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_ASSET_TYPE_COLUMN_CANDIDATES,
                required=False,
            ),
            "description": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_DESCRIPTION_COLUMN_CANDIDATES,
                required=False,
            ),
            "holder_name": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_HOLDER_NAME_COLUMN_CANDIDATES,
                required=False,
            ),
            "asset_value": LiveDatabaseService.resolve_column(
                LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE_NAME,
                LiveDatabaseService.CLAIM_LINE_VALUE_COLUMN_CANDIDATES,
                required=False,
            ),
        }

        logger.info(
            "Validated live database schema. Claim-line columns: %s",
            claim_line_columns,
        )

        return {
            "header_claim_no_column": "No_",
            "claim_line_columns": claim_line_columns,
        }

    @staticmethod
    def generate_claim_number():
        """Generate a unique claim number for the SQL Server claims table."""
        formats = [
            lambda: f"CLM-{random.randint(10000, 99999)}",
            lambda: (
                f"CM{str(int(time.time() * 1000))[-10:]}"
                f"{random.randint(100, 999)}"
            ),
            lambda: (
                f"CLM-{str(int(time.time()))[-8:]}-"
                f"{random.randint(100, 999)}"
            ),
        ]

        for format_func in formats:
            for _attempt in range(5):
                claim_no = LiveDatabaseService.safe_string(
                    format_func(),
                    15,
                )

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

                        count = cursor.fetchone()[0]

                        if count == 0:
                            return claim_no

                except Exception as exc:
                    logger.warning(
                        "Error checking generated claim number %s: %s",
                        claim_no,
                        exc,
                    )

        fallback = f"CLM-{int(time.time())}"
        return LiveDatabaseService.safe_string(fallback, 15)

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
        """Search for unclaimed assets using raw SQL only."""
        logger.info(
            "Searching live unclaimed assets. Identifier=%s, search_type=%s",
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
                    [ID Number],
                    [Passport No_],
                    [CDS Account No_],
                    [Asset Type],
                    [Source],
                    [Status],
                    [Description_],
                    [Amount Due to Owner],
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
                        WHERE [ID Number] = %s
                           OR [ID Number_] = %s
                    """
                    params = [identifier, identifier]

                elif search_type == "passport":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE [Passport No_] = %s
                    """
                    params = [identifier]

                elif search_type == "cds":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE [CDS Account No_] = %s
                    """
                    params = [identifier]

                else:
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE [Name] LIKE %s
                           OR [Middle Name] LIKE %s
                           OR [Last Name] LIKE %s
                           OR [Holder Name] LIKE %s
                    """
                    search_pattern = f"%{identifier}%"
                    params = [
                        search_pattern,
                        search_pattern,
                        search_pattern,
                        search_pattern,
                    ]

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
                        owner_name = asset.get("Holder Name") or "N/A"

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

                    amount = asset.get("Amount Due to Owner") or 0

                    results.append(
                        {
                            "id": asset.get("No_"),
                            "asset_no": asset.get("No_"),
                            "holder_name": asset.get("Holder Name") or "",
                            "owner_name": owner_name,
                            "id_number": asset.get("ID Number") or "",
                            "passport_no": asset.get("Passport No_") or "",
                            "cds_account_no": asset.get("CDS Account No_") or "",
                            "asset_type": "Cash" if is_cash else "Non-Cash",
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
                            "city_town": (
                                asset.get("Owners City_Town") or ""
                            ),
                            "telephone": (
                                asset.get("Owners Telephnone No_") or ""
                            ),
                            "county": asset.get("County Name") or "",
                            "is_claimable": asset.get("Status") == 1,
                        }
                    )

                logger.info("Found %s unclaimed asset(s)", len(results))
                return results

        except Exception:
            logger.exception(
                "Error searching unclaimed assets for identifier %s",
                identifier,
            )
            return []

    # ==================== PUSH TO LIVE METHODS ====================

    @staticmethod
    def push_claim_to_live(claim_id):
        """Push one pending or under-review claim to the live database."""
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

            original_claim_no = claim.no
            new_claim_no = LiveDatabaseService.generate_claim_number()

            logger.info(
                "Generated live claim number %s for local claim %s",
                new_claim_no,
                original_claim_no,
            )

            if LiveDatabaseService.claim_exists_in_live(new_claim_no):
                new_claim_no = LiveDatabaseService.generate_claim_number()

                logger.info(
                    "Regenerated live claim number as %s",
                    new_claim_no,
                )

            claim_data = {
                "claim_no": new_claim_no,
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
            }

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

            result = LiveDatabaseService.create_new_claim(
                claim_data,
                claim_lines_data,
            )

            if result.get("success"):
                claim.no = result.get("claim_no", new_claim_no)
                claim.status = "Under_Review"
                claim.save(update_fields=["no", "status"])

                return {
                    "success": True,
                    "claim_no": claim.no,
                    "original_claim_no": original_claim_no,
                    "message": (
                        f"Claim {original_claim_no} was pushed with live "
                        f"number {claim.no}"
                    ),
                }

            return {
                "success": False,
                "claim_no": original_claim_no,
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

        Header and line inserts are executed in a single transaction. If
        any line fails, the header insert is rolled back.
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

        operation_stage = "schema validation"

        try:
            schema = LiveDatabaseService.validate_live_schema()
            line_columns = schema["claim_line_columns"]

            with transaction.atomic(using="ereunify"):
                with connections["ereunify"].cursor() as cursor:
                    operation_stage = "checking header claim existence"

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
                        operation_stage = "updating existing header claim"

                        cursor.execute(
                            f"""
                                UPDATE
                                    {LiveDatabaseService.ONLINE_CLAIM_TABLE}
                                SET
                                    [Status] = %s,
                                    [$systemModifiedAt] = %s
                                WHERE [No_] = %s
                            """,
                            [
                                status_id,
                                timezone.now(),
                                claim_no_truncated,
                            ],
                        )

                        if cursor.rowcount <= 0:
                            raise RuntimeError(
                                f"Claim {claim_no_truncated} exists but "
                                "could not be updated"
                            )

                        return {
                            "success": True,
                            "claim_no": claim_no_truncated,
                            "message": (
                                "Existing live claim status updated "
                                "successfully"
                            ),
                        }

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
                            [$systemCreatedAt],
                            [$systemModifiedAt]
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s
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
                            timezone.now(),
                            timezone.now(),
                        ],
                    )

                    logger.info(
                        "Inserted live claim header %s",
                        claim_no_truncated,
                    )

                    for index, line in enumerate(
                        claim_lines_data,
                        start=1,
                    ):
                        operation_stage = (
                            f"inserting claim line {index}"
                        )

                        line_field_values = [
                            (
                                line_columns["parent_claim"],
                                claim_no_truncated,
                            ),
                            (
                                line_columns["line_number"],
                                index,
                            ),
                            (
                                line_columns["asset_no"],
                                LiveDatabaseService.safe_string(
                                    line.get("asset_no", ""),
                                    50,
                                ),
                            ),
                        ]

                        if line_columns["asset_type"]:
                            line_field_values.append(
                                (
                                    line_columns["asset_type"],
                                    LiveDatabaseService.safe_string(
                                        line.get("asset_type", ""),
                                        50,
                                    ),
                                )
                            )

                        if line_columns["description"]:
                            line_field_values.append(
                                (
                                    line_columns["description"],
                                    LiveDatabaseService.safe_string(
                                        line.get("description", ""),
                                        500,
                                    ),
                                )
                            )

                        if line_columns["holder_name"]:
                            line_field_values.append(
                                (
                                    line_columns["holder_name"],
                                    LiveDatabaseService.safe_string(
                                        line.get("holder_name", ""),
                                        200,
                                    ),
                                )
                            )

                        if line_columns["asset_value"]:
                            line_field_values.append(
                                (
                                    line_columns["asset_value"],
                                    float(line.get("value", 0) or 0),
                                )
                            )

                        quoted_columns = ", ".join(
                            LiveDatabaseService.quote_identifier(column)
                            for column, _value in line_field_values
                        )
                        placeholders = ", ".join(
                            "%s" for _column, _value in line_field_values
                        )
                        params = [
                            value
                            for _column, value in line_field_values
                        ]

                        insert_line_sql = f"""
                            INSERT INTO
                                {LiveDatabaseService.ONLINE_CLAIM_LINES_TABLE}
                            (
                                {quoted_columns}
                            )
                            VALUES (
                                {placeholders}
                            )
                        """

                        logger.debug(
                            "Inserting claim line %s for claim %s using "
                            "columns: %s",
                            index,
                            claim_no_truncated,
                            [
                                column
                                for column, _value in line_field_values
                            ],
                        )

                        cursor.execute(insert_line_sql, params)

                    logger.info(
                        "Inserted %s line(s) for live claim %s",
                        len(claim_lines_data),
                        claim_no_truncated,
                    )

            return {
                "success": True,
                "claim_no": claim_no_truncated,
                "message": (
                    f"Claim created successfully with "
                    f"{len(claim_lines_data)} asset line(s)"
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

            duplicate_indicators = (
                "duplicate",
                "unique",
                "violation of primary key",
                "violation of unique key",
                "2627",
                "2601",
            )

            is_duplicate = any(
                indicator in error_message.lower()
                for indicator in duplicate_indicators
            )

            if is_duplicate:
                new_claim_no = (
                    LiveDatabaseService.generate_claim_number()
                )

                logger.info(
                    "Duplicate live claim number %s. Retrying as %s",
                    claim_no_truncated,
                    new_claim_no,
                )

                retry_data = dict(claim_data)
                retry_data["claim_no"] = new_claim_no

                return LiveDatabaseService.create_new_claim(
                    retry_data,
                    claim_lines_data,
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

            # Validate once before processing the batch so configuration
            # problems are reported immediately.
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
                    "details": [],
                }

            results = []
            pushed_count = 0
            failed_count = 0
            skipped_count = 0

            for claim in claims.iterator():
                logger.info(
                    "Processing claim: %s (ID: %s)",
                    claim.no,
                    claim.id,
                )

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
                    skipped_count += 1

                    results.append(
                        {
                            "claim_no": claim.no,
                            "status": "skipped",
                            "message": (
                                "Already exists in live database"
                            ),
                        }
                    )
                    continue

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

            return {
                "success": True,
                "message": (
                    f"Push completed: {pushed_count} pushed, "
                    f"{failed_count} failed, "
                    f"{skipped_count} skipped"
                ),
                "pushed": pushed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "details": results,
            }

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
                "details": [],
            }
