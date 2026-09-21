# apps/live_operations/services.py
import logging
import re
from decimal import Decimal, InvalidOperation

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
    ONLINE_CLAIM_LINE_TABLE_NAME = (
        "UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )
    ATTACHED_DOCUMENT_TABLE_NAME = (
        "UFAA TRUST FUND$Attached Documents - Claims$2636ffcf-1aea-4b3a-808a-c1da12e824c1"
    )

    ONLINE_CLAIM_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ONLINE_CLAIM_TABLE_NAME}]"
    )
    UNCLAIMED_ASSET_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{UNCLAIMED_ASSET_TABLE_NAME}]"
    )
    ONLINE_CLAIM_LINE_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ONLINE_CLAIM_LINE_TABLE_NAME}]"
    )
    ATTACHED_DOCUMENT_TABLE = (
        f"[{DATABASE_NAME}].[{DATABASE_SCHEMA}].[{ATTACHED_DOCUMENT_TABLE_NAME}]"
    )

    CREATED_BY_VALUE = "UFAA_Reunite_Mobile"

    # Assets with a Status below this value are considered searchable /
    # available to be claimed. On the live table:
    #   1 = Unclaimed
    #   2 = In Process
    #   3 = Claimed
    #   4 = Archived
    MAX_SEARCHABLE_ASSET_STATUS = 2

    # Columns managed by SQL Server / Business Central. Never include
    # these in an INSERT — the target system writes them.
    SYSTEM_MANAGED_COLUMNS = (
        "timestamp",
        "$systemId",
        "$systemCreatedAt",
        "$systemCreatedBy",
        "$systemModifiedAt",
        "$systemModifiedBy",
    )

    # Keys that should never receive None. If a None sneaks through,
    # the sweep in push_* methods replaces it with a default.
    BOOLEAN_LIKE_KEYS = (
        "Rejected",
        "Posted",
        "Synchronized",
        "Interest Bearing Account",
        "More than one owner",
        "Attached",
        "Mandatory",
        "Verification Completed",
    )
    INTEGER_LIKE_KEYS = (
        "Document Line No_",
        "No of Remitted Shares",
        "Quantity",
    )
    DECIMAL_LIKE_KEYS = (
        "Value of the Content",
        "Amount Due to Owner",
        "Value",
        "Value LCY",
    )

    # Maps ClaimDocument.document_type choice keys to the [Code] value
    # written on the live Attached Documents table.
    DOCUMENT_TYPE_CODE_MAPPING = {
        "combined": "COMBINED",
        "form4a": "FORM4A",
        "form4b": "FORM4B",
        "form4c": "FORM4C",
        "form4d": "FORM4D",
        "form5": "FORM5",
        "id_copy": "ID_COPY",
        "kra_pin": "KRA_PIN",
        "death_certificate": "DEATH_CERTIFICATE",
        "grant_certificate": "GRANT_CERTIFICATE",
        "holder_letter": "HOLDER_LETTER",
        "bank_statement": "BANK_STATEMENT",
        "affidavit": "AFFIDAVIT",
        "policy_document": "POLICY_DOCUMENT",
        "power_of_attorney": "POWER_OF_ATTORNEY",
        "guardianship_deed": "GUARDIANSHIP_DEED",
        "cr12": "CR12",
        "incorporation": "INCORPORATION",
        "directors_ids": "DIRECTORS_IDS",
        "payment_form": "PAYMENT_FORM",
        "other": "OTHER",
    }

    # ==================== EMOJI / NON-BMP SANITIZER ====================

    _NON_BMP_AND_EMOJI_RE = re.compile(
        "["
        "\U0001F000-\U0001FAFF"   # emoji, symbols, pictographs
        "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
        "\U00002600-\U000027BF"   # misc symbols + dingbats
        "\uFE00-\uFE0F"           # variation selectors
        "\u200D"                  # zero-width joiner
        "]"
    )

    @staticmethod
    def sanitize_for_sql(value):
        """
        Strip characters that break ODBC binding on SQL Server.

        Removes emoji, non-BMP characters, and C0/C1 control chars
        except tab, newline, carriage return.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        cleaned = "".join(ch for ch in value if ord(ch) <= 0xFFFF)
        cleaned = LiveDatabaseService._NON_BMP_AND_EMOJI_RE.sub("", cleaned)
        cleaned = "".join(
            ch for ch in cleaned
            if ch in "\t\n\r" or ord(ch) >= 0x20
        )
        return cleaned

    @staticmethod
    def sanitize_payload_strings(payload):
        """Apply sanitize_for_sql to every string value in a payload dict."""
        for k, v in list(payload.items()):
            if isinstance(v, str):
                payload[k] = LiveDatabaseService.sanitize_for_sql(v)
        return payload

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
        "WhatsApp": 9,
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

    ASSET_TYPE_MAPPING = {
        "Cash": 1,
        "Non_Cash": 2,
        "Non-Cash": 2,
        "NonCash": 2,
        "": 0,
    }

    SOURCE_MAPPING = {
        "Cash": 1,
        "Shares": 2,
        "Safe Deposit": 3,
        "Safe_Deposit": 3,
        "SafeDeposit": 3,
        "": 0,
    }

    # ==================== HELPER METHODS ====================

    @staticmethod
    def safe_string(value, max_length=255):
        if value is None:
            return ""

        value = str(value).strip()
        value = LiveDatabaseService.sanitize_for_sql(value)

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
        return f"[{str(identifier).replace(']', ']]')}]"

    @staticmethod
    def get_table_columns(table_name):
        sql = f"""
            SELECT COLUMN_NAME
            FROM [{LiveDatabaseService.DATABASE_NAME}].INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        with connections["ereunify"].cursor() as cursor:
            cursor.execute(sql, [
                LiveDatabaseService.DATABASE_SCHEMA,
                table_name,
            ])
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def resolve_column(table_name, candidates, required=True):
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
    def _resolve_claim_amount(claim):
        if claim.amount is not None:
            try:
                header_amount = Decimal(str(claim.amount))
                if header_amount > 0:
                    return header_amount
            except (InvalidOperation, TypeError, ValueError):
                logger.warning(
                    "Claim %s has non-numeric amount %r; falling back to assets",
                    getattr(claim, "no", claim.pk),
                    claim.amount,
                )

        total = Decimal("0")
        for asset in ClaimAsset.objects.filter(claim=claim):
            if asset.value is None:
                continue
            try:
                total += Decimal(str(asset.value))
            except (InvalidOperation, TypeError, ValueError):
                logger.warning(
                    "Claim %s asset %s has non-numeric value %r; skipping",
                    getattr(claim, "no", claim.pk),
                    getattr(asset, "asset_no", asset.pk),
                    asset.value,
                )
                continue

        return total if total > 0 else Decimal("0")

    @staticmethod
    def claim_exists_in_live(claim_no):
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
        """
        Search for unclaimed assets in the live Business Central table.

        Only assets whose [Status] is strictly less than
        MAX_SEARCHABLE_ASSET_STATUS (default 2) are returned.
        """
        identifier = LiveDatabaseService.safe_string(identifier, 255)
        search_type = LiveDatabaseService.safe_string(search_type, 20).lower()

        if not identifier:
            raise ValueError("Search identifier is required")

        logger.info(
            "Searching live unclaimed assets. Identifier=%r, search_type=%s, "
            "max_status=%s",
            identifier,
            search_type,
            LiveDatabaseService.MAX_SEARCHABLE_ASSET_STATUS,
        )

        max_status = LiveDatabaseService.MAX_SEARCHABLE_ASSET_STATUS

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
                          AND [Status] < %s
                    """
                    params = [identifier, max_status]

                elif search_type == "passport":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE LTRIM(
                            RTRIM(CAST([Passport No_] AS VARCHAR(100)))
                        ) = %s
                          AND [Status] < %s
                    """
                    params = [identifier, max_status]

                elif search_type == "cds":
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE (
                                LTRIM(
                                    RTRIM(
                                        CAST([CDS Account No_] AS VARCHAR(100))
                                    )
                                ) = %s
                             OR LTRIM(
                                    RTRIM(
                                        CAST([CDS No_] AS VARCHAR(100))
                                    )
                                ) = %s
                              )
                          AND [Status] < %s
                    """
                    params = [identifier, identifier, max_status]

                elif search_type in {"name", "owner", "holder"}:
                    search_pattern = f"%{identifier}%"
                    sql = f"""
                        SELECT {selected_columns}
                        FROM {LiveDatabaseService.UNCLAIMED_ASSET_TABLE}
                        WHERE (
                                [Name] LIKE %s
                             OR [Middle Name] LIKE %s
                             OR [Last Name] LIKE %s
                             OR [Holder Name] LIKE %s
                             OR [Owner Name] LIKE %s
                             OR [Search Name] LIKE %s
                              )
                          AND [Status] < %s
                    """
                    params = [search_pattern] * 6 + [max_status]

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
                        str(part).strip() for part in owner_parts if part
                    ).strip()

                    if not owner_name:
                        owner_name = (
                            asset.get("Owner Name")
                            or asset.get("Holder Name")
                            or "N/A"
                        )

                    asset_type = asset.get("Asset Type")
                    is_cash = asset_type == 1

                    source_map = {1: "Cash", 2: "Shares", 3: "Safe Deposit"}
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

                    results.append({
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
                        "source": source_map.get(asset.get("Source"), "Other"),
                        "source_code": asset.get("Source"),
                        "amount": str(amount),
                        "numeric_amount": float(amount),
                        "status": status_map.get(
                            asset.get("Status"), "Unknown"
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
                    })

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

            claim_no = claim.no
            if not claim_no:
                return {
                    "success": False,
                    "message": f"Claim {claim_id} does not have a claim number",
                }

            if LiveDatabaseService.claim_exists_in_live(claim_no):
                return {
                    "success": False,
                    "message": f"Claim {claim_no} already exists in live database",
                    "claim_no": claim_no,
                    "status": "already_exists",
                }

            resolved_amount = LiveDatabaseService._resolve_claim_amount(claim)

            claim_data = {
                "claim_no": claim_no,
                "document_date": claim.document_date or timezone.now().date(),
                "processing_date": claim.processing_date or timezone.now().date(),
                "category": claim.category or "Original_Owner",
                "sub_category": claim.sub_category or "",
                "agent_name": claim.agent_name or "",
                "claim_type": claim.claim_type or "Cash",
                "claimant_name": claim.name or "",
                "claimant_id": claim.id_number or "",
                "claimant_phone": claim.phone_no or "",
                "claimant_email": claim.e_mail or "",
                "amount": resolved_amount,
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
                "location_source": 1,
                "created_by": LiveDatabaseService.CREATED_BY_VALUE,
            }

            claim_assets = ClaimAsset.objects.filter(claim=claim)
            claim_lines_data = []
            for asset in claim_assets:
                claim_lines_data.append({
                    "asset_no": asset.asset_no or "",
                    "asset_type": asset.asset_type or "",
                    "description": asset.description or "",
                    "holder_name": asset.holder_name or "",
                    "value": (
                        Decimal(str(asset.value))
                        if asset.value is not None
                        else Decimal("0")
                    ),
                })

            result = LiveDatabaseService.create_new_claim(
                claim_data, claim_lines_data,
            )

            if result.get("success"):
                claim.status = "Under_Review"
                claim.save(update_fields=["status"])

                try:
                    line_result = LiveDatabaseService.push_claim_lines_to_live(
                        claim.id
                    )
                    if line_result.get("failed", 0) > 0:
                        logger.warning(
                            "Claim %s pushed but %d line(s) failed: %s",
                            claim.no,
                            line_result.get("failed", 0),
                            line_result.get("message"),
                        )
                except Exception:
                    logger.exception(
                        "Header pushed for %s but line push raised",
                        claim.no,
                    )

                return {
                    "success": True,
                    "claim_no": claim.no,
                    "message": f"Claim {claim.no} was successfully pushed to live",
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
                "Error pushing claim ID %s to the live database", claim_id,
            )
            return {"success": False, "message": str(exc)}

    @staticmethod
    def create_new_claim(claim_data, claim_lines_data):
        claim_no = claim_data.get("claim_no")
        if not claim_no:
            return {"success": False, "message": "Claim number is required"}

        claim_no_truncated = LiveDatabaseService.safe_string(claim_no, 15)

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
                if cursor.fetchone()[0] > 0:
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

        category_id = LiveDatabaseService.CATEGORY_MAPPING.get(
            claim_data.get("category", "Original_Owner"), 1,
        )
        claim_type_id = LiveDatabaseService.CLAIM_TYPE_MAPPING.get(
            claim_data.get("claim_type", "Cash"), 1,
        )
        status_id = LiveDatabaseService.STATUS_MAPPING.get(
            claim_data.get("status", "Pending"), 1,
        )
        payment_category_id = LiveDatabaseService.PAYMENT_CATEGORY_MAPPING.get(
            claim_data.get("payment_category", ""), 1,
        )
        gender_value = LiveDatabaseService.GENDER_MAPPING.get(
            claim_data.get("gender", ""), 0,
        )

        claim_origin_value = claim_data.get("claim_origin", "")
        if isinstance(claim_origin_value, str):
            claim_origin_id = LiveDatabaseService.CLAIM_ORIGIN_MAPPING.get(
                claim_origin_value, 0,
            )
        else:
            claim_origin_id = int(claim_origin_value) if claim_origin_value else 0

        sub_category_value = claim_data.get("sub_category", "")
        if isinstance(sub_category_value, str):
            sub_category_id = LiveDatabaseService.SUB_CATEGORY_MAPPING.get(
                sub_category_value, 0,
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

        location_source = claim_data.get("location_source", 1)

        created_by_value = LiveDatabaseService.safe_string(
            claim_data.get("created_by", LiveDatabaseService.CREATED_BY_VALUE),
            100,
        )

        raw_amount = claim_data.get("amount", Decimal("0"))
        try:
            resolved_amount = (
                Decimal(str(raw_amount))
                if raw_amount is not None
                else Decimal("0")
            )
        except (InvalidOperation, TypeError, ValueError):
            logger.warning(
                "Invalid amount %r for claim %s; inserting 0",
                raw_amount, claim_no_truncated,
            )
            resolved_amount = Decimal("0")

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
                            [No_], [Document Date], [Processing Date],
                            [Category], [Sub Category], [Agent Name],
                            [Claim Type], [Name], [ID Number],
                            [Phone No_], [E-Mail], [Value],
                            [Status], [Payment Category], [Bank Name],
                            [Bank Account No_], [Mpesa Mobile No_],
                            [Passport No_], [Gender], [Claim Origin],
                            [Residence], [Address], [Post Code],
                            [County], [City], [Internal Remarks],
                            [Location Source], [Created BY],
                            [$systemCreatedAt], [$systemModifiedAt]
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s
                        )
                    """

                    cursor.execute(insert_claim_sql, [
                        claim_no_truncated,
                        document_date,
                        processing_date,
                        category_id,
                        sub_category_id,
                        LiveDatabaseService.safe_string(
                            claim_data.get("agent_name", ""), 100,
                        ),
                        claim_type_id,
                        LiveDatabaseService.safe_string(
                            claim_data.get("claimant_name", ""), 200,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("claimant_id", ""), 50,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("claimant_phone", ""), 20,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("claimant_email", ""), 100,
                        ),
                        resolved_amount,
                        status_id,
                        payment_category_id,
                        LiveDatabaseService.safe_string(
                            claim_data.get("bank_name", ""), 100,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("bank_account_no", ""), 50,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("mpesa_mobile_no", ""), 20,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("claimant_passport", ""), 50,
                        ),
                        gender_value,
                        claim_origin_id,
                        LiveDatabaseService.safe_string(
                            claim_data.get("residence", ""), 50,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("address", ""), 255,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("post_code", ""), 20,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("county", ""), 50,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("city", ""), 50,
                        ),
                        LiveDatabaseService.safe_string(
                            claim_data.get("internal_remarks", ""), 500,
                        ),
                        location_source,
                        created_by_value,
                        timezone.now(),
                        timezone.now(),
                    ])

            return {
                "success": True,
                "claim_no": claim_no_truncated,
                "message": (
                    f"Claim header created successfully. "
                    f"Value={resolved_amount}, "
                    f"Created BY={created_by_value}, "
                    f"Location Source={location_source}"
                ),
            }

        except Exception as exc:
            error_message = str(exc)
            logger.exception(
                "Error creating live claim %s during %s: %s",
                claim_no_truncated, operation_stage, error_message,
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

    # ==================== PUSH CLAIM LINES TO LIVE ====================

    @staticmethod
    def _next_line_no(cursor, batch_no):
        cursor.execute(
            f"""
                SELECT ISNULL(MAX([Line No_]), 9999)
                FROM {LiveDatabaseService.ONLINE_CLAIM_LINE_TABLE}
                WHERE [Batch No_] = %s
            """,
            [batch_no],
        )
        current_max = cursor.fetchone()[0] or 9999
        return int(current_max) + 10000

    @staticmethod
    def _build_line_payload(claim, asset, line_no, batch_no):
        asset_type_raw = (asset.asset_type or "").strip()
        asset_type_code = LiveDatabaseService.ASSET_TYPE_MAPPING.get(
            asset_type_raw, 0,
        )

        source_raw = (asset.source or "").strip()
        source_code = LiveDatabaseService.SOURCE_MAPPING.get(source_raw, 0)

        snap = asset.asset_snapshot or {}

        def _snap(key, default=""):
            return snap.get(key, default) if isinstance(snap, dict) else default

        value = asset.value if asset.value is not None else Decimal("0")

        dob = (
            _snap("date_of_birth")
            or claim.document_date
            or timezone.now().date()
        )
        cheque_date = (
            _snap("cheque_date")
            or claim.document_date
            or timezone.now().date()
        )

        return {
            "Batch No_": LiveDatabaseService.safe_string(batch_no, 50),
            "Line No_": line_no,
            "Asset No_": LiveDatabaseService.safe_string(asset.asset_no, 100),
            "Asset Type": asset_type_code,
            "Source": source_code,
            "Class Code": LiveDatabaseService.safe_string(
                asset.class_code or _snap("class_code"), 50,
            ),
            "Class": LiveDatabaseService.safe_string(
                asset.class_field or _snap("class"), 100,
            ),
            "Asset Code": LiveDatabaseService.safe_string(
                asset.asset_code or _snap("asset_code"), 100,
            ),
            "Description": LiveDatabaseService.safe_string(
                asset.description or _snap("description"), 500,
            ),
            "Description_": LiveDatabaseService.safe_string(
                _snap("description_"), 500,
            ),
            "Name": LiveDatabaseService.safe_string(
                asset.name or claim.name, 200,
            ),
            "Middle Name": LiveDatabaseService.safe_string(
                _snap("middle_name"), 100,
            ),
            "Last Name": LiveDatabaseService.safe_string(
                _snap("last_name"), 100,
            ),
            "Date of Birth": dob,
            "ID Number": LiveDatabaseService.safe_string(
                asset.id_number or claim.id_number, 50,
            ),
            "Passport No_": LiveDatabaseService.safe_string(
                claim.passport_no, 50,
            ),
            "Owners Postal Address": LiveDatabaseService.safe_string(
                _snap("owners_postal_address") or claim.postal_address, 255,
            ),
            "Owners City_Town": LiveDatabaseService.safe_string(
                _snap("owners_city_town") or claim.city, 100,
            ),
            "County Code": LiveDatabaseService.safe_string(
                _snap("county_code") or claim.county_code, 50,
            ),
            "County Name": LiveDatabaseService.safe_string(
                _snap("county_name") or claim.county_name or claim.county, 100,
            ),
            "Owners Telephnone No_": LiveDatabaseService.safe_string(
                _snap("owners_telephone_no") or claim.phone_no, 50,
            ),
            "Currency": LiveDatabaseService.safe_string(
                claim.currency or "KES", 10,
            ),
            "Currency Code": LiveDatabaseService.safe_string(
                claim.currency or "KES", 10,
            ),
            "Amount Due to Owner": value,
            "Value": value,
            "Value LCY": value,
            "Quantity": 1,
            "Holder No_": LiveDatabaseService.safe_string(
                _snap("holder_no"), 50,
            ),
            "Holder Name": LiveDatabaseService.safe_string(
                asset.holder_name or _snap("holder_name"), 200,
            ),
            "Asset Appl_ No_": LiveDatabaseService.safe_string(
                _snap("asset_appl_no"), 50,
            ),
            "Document Line No_": _snap("document_line_no") or 0,
            "CDS Account No_": LiveDatabaseService.safe_string(
                asset.cds_account_no or _snap("cds_account_no"), 100,
            ),
            "No of Remitted Shares": _snap("no_of_remitted_shares") or 0,
            "Interest Bearing Account": bool(
                _snap("interest_bearing_account", False)
            ),
            "More than one owner": bool(
                _snap("more_than_one_owner", False)
            ),
            "Item No_": LiveDatabaseService.safe_string(_snap("item_no"), 50),
            "Description of the Content": LiveDatabaseService.safe_string(
                _snap("description_of_content"), 500,
            ),
            "Value of the Content": _snap("value_of_content") or Decimal("0"),
            "Safe Deposit No_": LiveDatabaseService.safe_string(
                _snap("safe_deposit_no"), 50,
            ),
            "Cheque No_": LiveDatabaseService.safe_string(
                _snap("cheque_no"), 50,
            ),
            "Cheque Date": cheque_date,
            "Drawee": LiveDatabaseService.safe_string(_snap("drawee"), 200),
            "Drawee ID Number": LiveDatabaseService.safe_string(
                _snap("drawee_id_number"), 50,
            ),
            "Cheque Number": LiveDatabaseService.safe_string(
                _snap("cheque_number"), 50,
            ),
            "Account No_": LiveDatabaseService.safe_string(
                _snap("account_no"), 50,
            ),
            "Laptrust No_": LiveDatabaseService.safe_string(
                _snap("laptrust_no"), 50,
            ),
            "Policy No_": LiveDatabaseService.safe_string(
                _snap("policy_no"), 50,
            ),
            "Rejected": bool(asset.rejected),
            "Posted": True,
            "Synchronized": True,
            "Base Unit of Measure": LiveDatabaseService.safe_string(
                _snap("base_unit_of_measure"), 50,
            ),
        }

    @staticmethod
    def push_claim_lines_to_live(claim_id):
        try:
            claim = Claim.objects.filter(id=claim_id).first()
            if not claim:
                return {
                    "success": False, "claim_no": None,
                    "message": f"Claim {claim_id} not found",
                }
            if not claim.no:
                return {
                    "success": False, "claim_no": None,
                    "message": f"Claim {claim_id} does not have a claim number",
                }
            if not LiveDatabaseService.claim_exists_in_live(claim.no):
                return {
                    "success": False, "claim_no": claim.no,
                    "message": (
                        f"Claim header {claim.no} is not in the live "
                        "database. Push the claim header first."
                    ),
                }

            assets = (
                ClaimAsset.objects
                .filter(claim=claim)
                .select_related("claim")
                .order_by("id")
            )
            if not assets.exists():
                return {
                    "success": True, "claim_no": claim.no,
                    "message": "No claim assets to push",
                    "pushed": 0, "failed": 0, "skipped": 0,
                    "already_exists": 0, "details": [],
                }

            results = []
            pushed = failed = skipped = already_exists = 0

            with transaction.atomic(using="ereunify"):
                with connections["ereunify"].cursor() as cursor:
                    for asset in assets:
                        asset_claim_no = (
                            LiveDatabaseService.safe_string(asset.claim.no, 50)
                            if asset.claim and asset.claim.no else ""
                        )

                        try:
                            if not asset.asset_no:
                                skipped += 1
                                results.append({
                                    "asset_id": asset.id, "asset_no": None,
                                    "status": "skipped",
                                    "message": "Asset has no asset_no",
                                })
                                continue

                            if not asset_claim_no:
                                skipped += 1
                                results.append({
                                    "asset_id": asset.id,
                                    "asset_no": asset.asset_no,
                                    "status": "skipped",
                                    "message": "Parent claim has no claim number",
                                })
                                continue

                            cursor.execute(
                                f"""
                                    SELECT COUNT(*)
                                    FROM {LiveDatabaseService.ONLINE_CLAIM_LINE_TABLE}
                                    WHERE [Batch No_] = %s
                                      AND [Asset No_] = %s
                                """,
                                [
                                    asset_claim_no,
                                    LiveDatabaseService.safe_string(
                                        asset.asset_no, 100,
                                    ),
                                ],
                            )
                            if cursor.fetchone()[0] > 0:
                                already_exists += 1
                                results.append({
                                    "asset_id": asset.id,
                                    "asset_no": asset.asset_no,
                                    "status": "already_exists",
                                    "message": "Line already exists in live",
                                })
                                continue

                            line_no = LiveDatabaseService._next_line_no(
                                cursor, asset_claim_no,
                            )

                            payload = LiveDatabaseService._build_line_payload(
                                asset.claim, asset, line_no, asset_claim_no,
                            )

                            LiveDatabaseService.sanitize_payload_strings(payload)

                            fallback_date = (
                                asset.claim.document_date
                                or timezone.now().date()
                            )
                            for k, v in list(payload.items()):
                                if v is not None:
                                    continue
                                if k in LiveDatabaseService.BOOLEAN_LIKE_KEYS:
                                    payload[k] = False
                                elif k in LiveDatabaseService.INTEGER_LIKE_KEYS:
                                    payload[k] = 0
                                elif k in LiveDatabaseService.DECIMAL_LIKE_KEYS:
                                    payload[k] = Decimal("0")
                                elif "Date" in k:
                                    payload[k] = fallback_date
                                else:
                                    payload[k] = ""

                            for system_col in LiveDatabaseService.SYSTEM_MANAGED_COLUMNS:
                                payload.pop(system_col, None)

                            cols = list(payload.keys())
                            col_sql = ", ".join(f"[{c}]" for c in cols)
                            placeholders = ", ".join(["%s"] * len(cols))
                            values = [payload[c] for c in cols]

                            cursor.execute(
                                f"""
                                    INSERT INTO
                                        {LiveDatabaseService.ONLINE_CLAIM_LINE_TABLE}
                                    ({col_sql})
                                    VALUES ({placeholders})
                                """,
                                values,
                            )

                            pushed += 1
                            results.append({
                                "asset_id": asset.id,
                                "asset_no": asset.asset_no,
                                "line_no": line_no,
                                "value": float(asset.value or 0),
                                "status": "success",
                                "message": "Line pushed",
                            })

                        except Exception as e:
                            failed += 1
                            logger.exception(
                                "Failed to push line for asset %s on claim %s",
                                asset.id, asset_claim_no or claim.no,
                            )
                            try:
                                logger.error(
                                    "SQL (line push for %s): INSERT INTO %s (%s) VALUES (%s)",
                                    asset_claim_no or claim.no,
                                    LiveDatabaseService.ONLINE_CLAIM_LINE_TABLE,
                                    col_sql,
                                    ", ".join(["?"] * len(cols)),
                                )
                                logger.error("PARAMS: %r", values)
                            except Exception:
                                pass

                            results.append({
                                "asset_id": asset.id,
                                "asset_no": asset.asset_no,
                                "status": "failed",
                                "message": str(e),
                            })

            logger.info(
                "Line push for claim %s: %d pushed, %d failed, %d skipped, %d already existed",
                claim.no, pushed, failed, skipped, already_exists,
            )

            return {
                "success": failed == 0,
                "claim_no": claim.no,
                "message": (
                    f"Pushed {pushed} line(s). "
                    f"Failed: {failed}, Skipped: {skipped}, "
                    f"Already exists: {already_exists}"
                ),
                "pushed": pushed,
                "failed": failed,
                "skipped": skipped,
                "already_exists": already_exists,
                "details": results,
            }

        except Exception as exc:
            logger.exception(
                "Error pushing claim lines for claim_id=%s", claim_id,
            )
            return {"success": False, "claim_no": None, "message": str(exc)}

    # ==================== PUSH CLAIM DOCUMENTS TO LIVE ====================

    @staticmethod
    def push_claim_documents_to_live(claim_id):
        from apps.claims.models import ClaimDocument

        try:
            claim = Claim.objects.filter(id=claim_id).first()
            if not claim:
                return {
                    "success": False, "claim_no": None,
                    "message": f"Claim {claim_id} not found",
                }
            if not claim.no:
                return {
                    "success": False, "claim_no": None,
                    "message": f"Claim {claim_id} does not have a claim number",
                }
            if not LiveDatabaseService.claim_exists_in_live(claim.no):
                return {
                    "success": False, "claim_no": claim.no,
                    "message": (
                        f"Claim header {claim.no} is not in the live "
                        "database. Push the claim header first."
                    ),
                }

            documents = (
                ClaimDocument.objects
                .filter(claim=claim)
                .select_related("claim")
                .order_by("id")
            )
            if not documents.exists():
                return {
                    "success": True, "claim_no": claim.no,
                    "message": "No claim documents to push",
                    "pushed": 0, "failed": 0, "skipped": 0,
                    "already_exists": 0, "details": [],
                }

            results = []
            pushed = failed = skipped = already_exists = 0

            with transaction.atomic(using="ereunify"):
                with connections["ereunify"].cursor() as cursor:
                    for doc in documents:
                        try:
                            document_no = LiveDatabaseService.safe_string(
                                doc.claim.no, 50,
                            )
                            doc_type = LiveDatabaseService.safe_string(
                                doc.document_type, 50,
                            )

                            if not document_no or not doc_type:
                                skipped += 1
                                results.append({
                                    "document_id": doc.id,
                                    "status": "skipped",
                                    "message": (
                                        "Document missing claim number or type"
                                    ),
                                })
                                continue

                            code = LiveDatabaseService.safe_string(
                                LiveDatabaseService.DOCUMENT_TYPE_CODE_MAPPING.get(
                                    doc_type, doc_type.upper()
                                ),
                                50,
                            )

                            cursor.execute(
                                f"""
                                    SELECT COUNT(*)
                                    FROM {LiveDatabaseService.ATTACHED_DOCUMENT_TABLE}
                                    WHERE [Document No_] = %s
                                      AND [Code] = %s
                                """,
                                [document_no, code],
                            )
                            if cursor.fetchone()[0] > 0:
                                already_exists += 1
                                results.append({
                                    "document_id": doc.id,
                                    "code": code,
                                    "status": "already_exists",
                                    "message": "Document already exists in live",
                                })
                                continue

                            file_path = ""
                            if doc.file:
                                try:
                                    file_path = doc.file.url or ""
                                except Exception:
                                    file_path = ""

                            payload = {
                                "Document No_": document_no,
                                "Code": code,
                                "Description": LiveDatabaseService.safe_string(
                                    doc_type, 200,
                                ),
                                "Document MS Link": LiveDatabaseService.safe_string(
                                    file_path, 1000,
                                ),
                                "Path": LiveDatabaseService.safe_string(
                                    file_path, 1000,
                                ),
                                "Attached": True,
                                "Mandatory": False,
                                "Type": "",
                                "Sub Category": "",
                                "Synchronized": True,
                                "Verification Type Code": "",
                                "Verification Type Description": "",
                                "Verification Completed": bool(doc.is_verified),
                            }

                            LiveDatabaseService.sanitize_payload_strings(payload)

                            for k, v in list(payload.items()):
                                if v is not None:
                                    continue
                                if k in LiveDatabaseService.BOOLEAN_LIKE_KEYS:
                                    payload[k] = False
                                else:
                                    payload[k] = ""

                            for system_col in LiveDatabaseService.SYSTEM_MANAGED_COLUMNS:
                                payload.pop(system_col, None)

                            cols = list(payload.keys())
                            col_sql = ", ".join(f"[{c}]" for c in cols)
                            placeholders = ", ".join(["%s"] * len(cols))
                            values = [payload[c] for c in cols]

                            cursor.execute(
                                f"""
                                    INSERT INTO
                                        {LiveDatabaseService.ATTACHED_DOCUMENT_TABLE}
                                    ({col_sql})
                                    VALUES ({placeholders})
                                """,
                                values,
                            )

                            pushed += 1
                            results.append({
                                "document_id": doc.id,
                                "code": code,
                                "status": "success",
                                "message": "Document pushed",
                            })

                        except Exception as e:
                            failed += 1
                            logger.exception(
                                "Failed to push document %s on claim %s",
                                doc.id, claim.no,
                            )
                            try:
                                logger.error(
                                    "SQL (document push for %s): "
                                    "INSERT INTO %s (%s) VALUES (%s)",
                                    claim.no,
                                    LiveDatabaseService.ATTACHED_DOCUMENT_TABLE,
                                    col_sql,
                                    ", ".join(["?"] * len(cols)),
                                )
                                logger.error("PARAMS: %r", values)
                            except Exception:
                                pass

                            results.append({
                                "document_id": doc.id,
                                "status": "failed",
                                "message": str(e),
                            })

            logger.info(
                "Document push for claim %s: %d pushed, %d failed, "
                "%d skipped, %d already existed",
                claim.no, pushed, failed, skipped, already_exists,
            )

            return {
                "success": failed == 0,
                "claim_no": claim.no,
                "message": (
                    f"Pushed {pushed} document(s). "
                    f"Failed: {failed}, Skipped: {skipped}, "
                    f"Already exists: {already_exists}"
                ),
                "pushed": pushed,
                "failed": failed,
                "skipped": skipped,
                "already_exists": already_exists,
                "details": results,
            }

        except Exception as exc:
            logger.exception(
                "Error pushing claim documents for claim_id=%s", claim_id,
            )
            return {"success": False, "claim_no": None, "message": str(exc)}

    # ==================== REJECTED CLAIMS SYNC ====================

    @staticmethod
    def fetch_rejected_claims(only_after=None):
        """
        Return claims in the live Online Claim table where [Rejected] = 1.

        The claimant-facing reason is read from [Send Remarks], which is
        the column UFAA staff populate when they return a claim. The
        internal-notes column ([Internal Remarks]) is only visible to
        staff and is not surfaced to the mobile app.

        Optionally restrict to rows whose [$systemModifiedAt] is later
        than `only_after`, so the caller can process deltas on each run.

        Returned dict keys:
            no                     claim number
            rejected               always 1
            status                 live [Status]
            rejection_reason       live [Send Remarks]
            action_required        live [Claimant Action Required]
            modified_at            live [$systemModifiedAt]
            claim_type             live [Claim Type]
            claimant_name          live [Name]
        """
        params = []
        where = ["[Rejected] = 1"]

        if only_after is not None:
            where.append("[$systemModifiedAt] >= %s")
            params.append(only_after)

        sql = f"""
            SELECT
                [No_]                      AS no,
                [Rejected]                 AS rejected,
                [Status]                   AS status,
                [Send Remarks]             AS rejection_reason,
                [Claimant Action Required] AS action_required,
                [$systemModifiedAt]        AS modified_at,
                [Claim Type]               AS claim_type,
                [Name]                     AS claimant_name
            FROM {LiveDatabaseService.ONLINE_CLAIM_TABLE}
            WHERE {' AND '.join(where)}
            ORDER BY [$systemModifiedAt] DESC
        """

        try:
            with connections["ereunify"].cursor() as cursor:
                cursor.execute(sql, params)
                columns = [c[0] for c in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:
            logger.exception("Error fetching rejected live claims")
            raise

    # ==================== BULK PUSH HELPERS ====================

    @staticmethod
    def push_pending_claims_to_live():
        try:
            logger.info("Starting push of pending claims to the live database")
            LiveDatabaseService.validate_live_schema()

            claims = Claim.objects.filter(
                status__in=["Pending", "Under_Review"]
            )

            if not claims.exists():
                return {
                    "success": True, "message": "No pending claims to push",
                    "pushed": 0, "failed": 0, "skipped": 0,
                    "already_exists": 0, "details": [],
                }

            results = []
            pushed_count = failed_count = skipped_count = already_exists_count = 0

            for claim in claims.iterator():
                try:
                    exists = LiveDatabaseService.claim_exists_in_live(claim.no)
                except Exception as exc:
                    failed_count += 1
                    results.append({
                        "claim_no": claim.no,
                        "status": "failed",
                        "message": (
                            "Could not check whether claim exists in "
                            f"live database: {exc}"
                        ),
                    })
                    continue

                if exists:
                    already_exists_count += 1
                    results.append({
                        "claim_no": claim.no,
                        "status": "already_exists",
                        "message": "Already exists in live database",
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

                result = LiveDatabaseService.push_claim_to_live(claim.id)

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
            return summary

        except Exception as exc:
            logger.exception("Error pushing pending claims to the live database")
            return {
                "success": False, "message": str(exc),
                "pushed": 0, "failed": 0, "skipped": 0,
                "already_exists": 0, "details": [],
            }

    @staticmethod
    def push_claims_by_ids(claim_ids):
        try:
            logger.info("Starting push of %s claims by IDs", len(claim_ids))

            results = []
            pushed_count = failed_count = skipped_count = already_exists_count = 0

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
                "success": False, "message": str(exc),
                "pushed": 0, "failed": len(claim_ids),
                "skipped": 0, "already_exists": 0, "details": [],
            }

    @staticmethod
    def sync_claim_status(claim_no, new_status):
        try:
            logger.info("Syncing claim %s status to %s", claim_no, new_status)
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
            return {"success": False, "message": str(e)}
