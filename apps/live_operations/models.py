# apps/live_operations/models.py
from django.db import models


class LiveUnclaimedAsset(models.Model):
    """Model for unclaimed assets in the live database (SQL Server)"""
    
    ASSET_TYPE_CHOICES = [
        (1, 'Cash'),
        (2, 'Non-Cash'),
    ]
    
    SOURCE_CHOICES = [
        (1, 'Cash'),
        (2, 'Shares'),
        (3, 'Safe Deposit'),
    ]
    
    STATUS_CHOICES = [
        (1, 'Unclaimed'),
        (2, 'In Process'),
        (3, 'Claimed'),
        (4, 'Archived'),
    ]
    
    # Primary key and basic fields
    timestamp = models.CharField(db_column='timestamp', max_length=50, null=True, blank=True)
    no = models.CharField(db_column='No_', max_length=100, primary_key=True)
    document_line_no = models.IntegerField(db_column='Document Line No_', null=True, blank=True)
    
    # Asset classification
    asset_type = models.IntegerField(db_column='Asset Type', null=True, blank=True, choices=ASSET_TYPE_CHOICES)  # 1=Cash, else=Non-Cash
    source = models.IntegerField(db_column='Source', null=True, blank=True, choices=SOURCE_CHOICES)  # 1=Cash, 2=Shares, 3=Safe Deposit
    class_code = models.CharField(db_column='Class Code', max_length=50, null=True, blank=True)
    class_name = models.CharField(db_column='Class', max_length=100, null=True, blank=True)
    asset_code = models.CharField(db_column='Asset Code', max_length=100, null=True, blank=True)
    
    # Asset description
    description = models.TextField(db_column='Description_', null=True, blank=True)
    name = models.CharField(db_column='Name', max_length=255, null=True, blank=True)
    middle_name = models.CharField(db_column='Middle Name', max_length=100, null=True, blank=True)
    last_name = models.CharField(db_column='Last Name', max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(db_column='Date of Birth', null=True, blank=True)
    
    # Owner identification - Important fields
    id_number = models.CharField(db_column='ID Number', max_length=50, db_index=True, null=True, blank=True)
    passport_no = models.CharField(db_column='Passport No_', max_length=50, db_index=True, null=True, blank=True)
    cds_account_no = models.CharField(db_column='CDS Account No_', max_length=100, null=True, blank=True)
    
    # Owner contact information
    owners_postal_address = models.CharField(db_column='Owners Postal Address', max_length=255, null=True, blank=True)
    owners_city_town = models.CharField(db_column='Owners City_Town', max_length=100, null=True, blank=True)
    county_code = models.CharField(db_column='County Code', max_length=50, null=True, blank=True)
    county_name = models.CharField(db_column='County Name', max_length=100, null=True, blank=True)
    owners_telephone_no = models.CharField(db_column='Owners Telephnone No_', max_length=50, null=True, blank=True)
    
    # Asset details
    amount_due_to_owner = models.DecimalField(db_column='Amount Due to Owner', max_digits=18, decimal_places=2, null=True, blank=True)
    amount_lcy = models.DecimalField(db_column='Amount LCY', max_digits=18, decimal_places=2, null=True, blank=True)
    
    # Status field (1=Unclaimed, 2=In Process, 3=Claimed, 4=Archived)
    status = models.IntegerField(db_column='Status', null=True, blank=True, choices=STATUS_CHOICES)
    
    # Holder information
    holder_name = models.CharField(db_column='Holder Name', max_length=255, null=True, blank=True)
    holder_no = models.CharField(db_column='Holder No_', max_length=50, null=True, blank=True)
    
    # Additional fields from your SQL
    interest_bearing_account = models.BooleanField(db_column='Interest Bearing Account', default=False, null=True, blank=True)
    more_than_one_owner = models.BooleanField(db_column='More than one owner', default=False, null=True, blank=True)
    
    # Safe deposit fields
    item_no = models.CharField(db_column='Item No_', max_length=50, null=True, blank=True)
    description_of_content = models.TextField(db_column='Description of the Content', null=True, blank=True)
    value_of_content = models.DecimalField(db_column='Value of the Content', max_digits=18, decimal_places=2, null=True, blank=True)
    safe_deposit_no = models.CharField(db_column='Safe Deposit No_', max_length=50, null=True, blank=True)
    
    # Shares fields
    no_of_remitted_shares = models.IntegerField(db_column='No of Remitted Shares', null=True, blank=True)
    
    # Cheque fields
    cheque_no = models.CharField(db_column='Cheque No_', max_length=50, null=True, blank=True)
    
    # Currency
    currency_code = models.CharField(db_column='Currency Code', max_length=10, default='KES', null=True, blank=True)
    
    # Account fields
    account_no = models.CharField(db_column='Account No_', max_length=50, null=True, blank=True)
    last_transaction_date = models.DateField(db_column='Last Transction Date', null=True, blank=True)
    
    # Invoice fields
    sales_invoice_no = models.CharField(db_column='Sales Invoice No_', max_length=50, null=True, blank=True)
    receipt_no = models.CharField(db_column='Receipt No_', max_length=50, null=True, blank=True)
    claimant_no = models.CharField(db_column='Claimant No_', max_length=50, null=True, blank=True)
    asset_appl_no = models.CharField(db_column='Asset Appl_ No_', max_length=50, null=True, blank=True)
    purch_invoice_no = models.CharField(db_column='Purch_ Invoice No_', max_length=50, null=True, blank=True)
    voucher_no = models.CharField(db_column='Voucher No_', max_length=50, null=True, blank=True)
    
    # Batch
    batch_no = models.CharField(db_column='Batch No_', max_length=50, null=True, blank=True)
    claim_batch_no = models.CharField(db_column='Claim Batch No', max_length=50, null=True, blank=True)
    
    # Virtual bank
    virtual_bank = models.CharField(db_column='Virtual Bank', max_length=50, null=True, blank=True)
    
    # Dates
    date_posted = models.DateField(db_column='Date Posted', null=True, blank=True)
    time_posted = models.TimeField(db_column='Time Posted', null=True, blank=True)
    
    # System fields
    synchronized = models.BooleanField(db_column='Synchronized', default=False, null=True, blank=True)
    data_imported = models.BooleanField(db_column='Data Imported', default=False, null=True, blank=True)
    no_series = models.CharField(db_column='No_ Series', max_length=50, null=True, blank=True)
    system_id = models.CharField(db_column='$systemId', max_length=100, null=True, blank=True)
    system_created_at = models.DateTimeField(db_column='$systemCreatedAt', null=True, blank=True)
    system_created_by = models.CharField(db_column='$systemCreatedBy', max_length=100, null=True, blank=True)
    system_modified_at = models.DateTimeField(db_column='$systemModifiedAt', null=True, blank=True)
    system_modified_by = models.CharField(db_column='$systemModifiedBy', max_length=100, null=True, blank=True)
    
    # Search fields
    search_description = models.TextField(db_column='Search Description', null=True, blank=True)
    search_name = models.CharField(db_column='Search Name', max_length=200, null=True, blank=True)
    name_search_key = models.CharField(db_column='Name Search Key', max_length=200, null=True, blank=True)
    search_hash = models.CharField(db_column='Search Hash', max_length=100, null=True, blank=True)
    
    # Posting groups
    inventory_posting_group = models.CharField(db_column='Inventory Posting Group', max_length=50, null=True, blank=True)
    type = models.CharField(db_column='Type', max_length=50, null=True, blank=True)
    vat_prod_posting_group = models.CharField(db_column='VAT Prod_ Posting Group', max_length=50, null=True, blank=True)
    price_profit_calculation = models.CharField(db_column='Price_Profit Calculation', max_length=50, null=True, blank=True)
    gen_prod_posting_group = models.CharField(db_column='Gen_ Prod_ Posting Group', max_length=50, null=True, blank=True)
    
    # Year/Month
    year_posted = models.IntegerField(db_column='Year Posted', null=True, blank=True)
    month_posted = models.IntegerField(db_column='Month Posted', null=True, blank=True)
    
    # CDS
    cds_no = models.CharField(db_column='CDS No_', max_length=50, null=True, blank=True)
    registrar_code = models.CharField(db_column='Registrar Code', max_length=50, null=True, blank=True)
    
    # Claim fields
    date_claimed = models.DateTimeField(db_column='Date Claimed', null=True, blank=True)
    claimed_by = models.CharField(db_column='Claimed By', max_length=100, null=True, blank=True)
    pv_no = models.CharField(db_column='PV No_', max_length=50, null=True, blank=True)
    locker_no = models.CharField(db_column='Locker No_', max_length=50, null=True, blank=True)
    owner_name = models.CharField(db_column='Owner Name', max_length=200, null=True, blank=True)
    synced = models.BooleanField(db_column='Synced', default=False, null=True, blank=True)
    
    class Meta:
        managed = False  # Don't create/modify table in Django
        db_table = '[UFAA TRUST FUND$Unclaimed Asset$2636ffcf-1aea-4b3a-808a-c1da12e824c1]'
        ordering = ['-timestamp']
        
    def get_asset_type_display_name(self):
        """Convert asset type code to display value"""
        if self.asset_type == 1:
            return 'Cash'
        return 'Non-Cash'
    
    def get_source_display_name(self):
        """Convert source code to display value"""
        source_map = {
            1: 'Cash',
            2: 'Shares',
            3: 'Safe Deposit'
        }
        return source_map.get(self.source, 'Other')
    
    def get_status_display_name(self):
        """Convert status code to display value"""
        status_map = {
            1: 'Unclaimed',
            2: 'In Process',
            3: 'Claimed',
            4: 'Archived'
        }
        return status_map.get(self.status, 'Unknown')
    
    def is_claimable(self):
        """Check if asset can be claimed"""
        return self.status == 1  # Status 1 = Unclaimed
    
    def get_full_name(self):
        """Get full name from name, middle_name, last_name"""
        parts = []
        if self.name:
            parts.append(self.name)
        if self.middle_name:
            parts.append(self.middle_name)
        if self.last_name:
            parts.append(self.last_name)
        return ' '.join(parts).strip() or self.holder_name or 'N/A'
    
    def __str__(self):
        return f"{self.no} - {self.holder_name} - {self.get_status_display_name()}"


class LiveOnlineClaim(models.Model):
    """Model for reading online claims from live database (READ-ONLY)"""
    
    # ==================== PRIMARY KEY & BASIC FIELDS ====================
    # FIX: Use brackets around column name with special characters
    claim_no = models.CharField(db_column='[No_]', primary_key=True, max_length=100)
    timestamp = models.CharField(db_column='[timestamp]', max_length=50, null=True, blank=True)
    no_series = models.CharField(db_column='[No_ Series]', max_length=50, null=True, blank=True)
    
    # ==================== CREATED BY ====================
    created_by = models.CharField(db_column='[Created BY]', max_length=100, null=True, blank=True)
    profile_id = models.CharField(db_column='[Profile Id]', max_length=100, null=True, blank=True)
    
    # ==================== STATUS ====================
    status = models.CharField(db_column='[Status]', max_length=50, null=True, blank=True)
    
    # ==================== LOCATION ====================
    residence = models.CharField(db_column='[Residence]', max_length=50, null=True, blank=True)
    location = models.CharField(db_column='[Location]', max_length=200, null=True, blank=True)
    location_source = models.CharField(db_column='[Location Source]', max_length=50, null=True, blank=True)
    location_sent_to = models.CharField(db_column='[Location Sent To:]', max_length=200, null=True, blank=True)
    
    # ==================== CLAIM CATEGORY ====================
    category = models.CharField(db_column='[Category]', max_length=50, null=True, blank=True)
    
    # ==================== CLAIMANT INFORMATION ====================
    claimant_name = models.CharField(db_column='[Name]', max_length=200, null=True, blank=True)
    kra_pin = models.CharField(db_column='[KRA P_I_N]', max_length=50, null=True, blank=True)
    id_number = models.CharField(db_column='[ID Number_]', max_length=50, db_index=True, null=True, blank=True)
    address = models.TextField(db_column='[Address]', null=True, blank=True)
    address_2 = models.TextField(db_column='[Address 2]', null=True, blank=True)
    claimant_phone = models.CharField(db_column='[Phone No_]', max_length=20, null=True, blank=True)
    post_code = models.CharField(db_column='[Post Code]', max_length=20, null=True, blank=True)
    county = models.CharField(db_column='[County]', max_length=50, null=True, blank=True)
    city = models.CharField(db_column='[City]', max_length=50, null=True, blank=True)
    country_region_code = models.CharField(db_column='[Country_Region Code]', max_length=20, null=True, blank=True)
    claimant_email = models.EmailField(db_column='[E-Mail]', max_length=200, null=True, blank=True)
    home_page = models.CharField(db_column='[Home Page]', max_length=200, null=True, blank=True)
    
    # ==================== CLAIM TYPE & ASSETS ====================
    claim_type = models.CharField(db_column='[Claim Type]', max_length=50, null=True, blank=True)
    asset_no = models.CharField(db_column='[Asset No_]', max_length=100, null=True, blank=True)
    asset_type = models.CharField(db_column='[Asset Type]', max_length=50, null=True, blank=True)
    source = models.CharField(db_column='[Source]', max_length=50, null=True, blank=True)
    class_code = models.CharField(db_column='[Class Code]', max_length=50, null=True, blank=True)
    class_field = models.CharField(db_column='[Class]', max_length=50, null=True, blank=True)
    asset_code = models.CharField(db_column='[Asset Code]', max_length=50, null=True, blank=True)
    description = models.TextField(db_column='[Description]', null=True, blank=True)
    description_2 = models.TextField(db_column='[Description_]', null=True, blank=True)
    
    # ==================== NAME FIELDS ====================
    first_name = models.CharField(db_column='[First Name]', max_length=100, null=True, blank=True)
    middle_name = models.CharField(db_column='[Middle Name]', max_length=100, null=True, blank=True)
    last_name = models.CharField(db_column='[Last Name]', max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(db_column='[Date of Birth]', null=True, blank=True)
    id_number_alt = models.CharField(db_column='[ID Number]', max_length=50, db_index=True, null=True, blank=True)
    passport_no = models.CharField(db_column='[Passport No_]', max_length=50, db_index=True, null=True, blank=True)
    
    # ==================== VALUE ====================
    amount = models.DecimalField(db_column='[Value]', max_digits=18, decimal_places=2, null=True, blank=True)
    
    # ==================== OWNERS INFORMATION ====================
    owners_postal_address = models.CharField(db_column='[Owners Postal Address]', max_length=200, null=True, blank=True)
    owners_city_town = models.CharField(db_column='[Owners City_Town]', max_length=100, null=True, blank=True)
    county_code = models.CharField(db_column='[County Code]', max_length=50, null=True, blank=True)
    county_name = models.CharField(db_column='[County Name]', max_length=100, null=True, blank=True)
    owners_telephone_no = models.CharField(db_column='[Owners Telephnone No_]', max_length=50, null=True, blank=True)
    
    # ==================== POSTING ====================
    posting_date = models.DateField(db_column='[Posting Date]', null=True, blank=True)
    currency = models.CharField(db_column='[Currency]', max_length=10, null=True, blank=True)
    posted = models.BooleanField(db_column='[Posted]', default=False, null=True, blank=True)
    date_posted = models.DateField(db_column='[Date Posted]', null=True, blank=True)
    time_posted = models.TimeField(db_column='[Time Posted]', null=True, blank=True)
    posted_by = models.CharField(db_column='[Posted BY]', max_length=100, null=True, blank=True)
    
    # ==================== CLAIMANT REFERENCES ====================
    claimant_no = models.CharField(db_column='[Claimant No_]', max_length=50, null=True, blank=True)
    invoice_no = models.CharField(db_column='[Invoice No_]', max_length=50, null=True, blank=True)
    voucher_no = models.CharField(db_column='[Voucher No_]', max_length=50, null=True, blank=True)
    laptrust_no = models.CharField(db_column='[Laptrust No_]', max_length=50, null=True, blank=True)
    policy_no = models.CharField(db_column='[Policy No_]', max_length=50, null=True, blank=True)
    holder_no = models.CharField(db_column='[Holder No_]', max_length=50, null=True, blank=True)
    holder_name = models.CharField(db_column='[Holder Name]', max_length=200, null=True, blank=True)
    asset_appl_no = models.CharField(db_column='[Asset Appl_ No_]', max_length=50, null=True, blank=True)
    document_line_no = models.IntegerField(db_column='[Document Line No_]', null=True, blank=True)
    
    # ==================== SEND TO ====================
    send_to_location = models.CharField(db_column='[Send To Location]', max_length=200, null=True, blank=True)
    send_to_location_source = models.CharField(db_column='[Send To Location Source]', max_length=50, null=True, blank=True)
    send_to = models.CharField(db_column='[Send To:]', max_length=200, null=True, blank=True)
    send_to_name = models.CharField(db_column='[Send To Name:]', max_length=200, null=True, blank=True)
    send_remarks = models.TextField(db_column='[Send Remarks]', null=True, blank=True)
    claimant_birth_date = models.CharField(db_column='[Claimant Birth Date]', max_length=50, null=True, blank=True)
    
    # ==================== AGENT ====================
    agent_name = models.CharField(db_column='[Agent Name]', max_length=200, null=True, blank=True)
    
    # ==================== DATES ====================
    start_date = models.DateField(db_column='[Start Date]', null=True, blank=True)
    due_date = models.DateField(db_column='[Due Date]', null=True, blank=True)
    published = models.BooleanField(db_column='[Published]', default=False, null=True, blank=True)
    quantity = models.IntegerField(db_column='[Quantity]', null=True, blank=True)
    
    # ==================== POSTING GROUPS ====================
    posting_group = models.CharField(db_column='[Posting Group]', max_length=50, null=True, blank=True)
    gen_bus_posting_group = models.CharField(db_column='[Gen_ Bus_ Posting Group]', max_length=50, null=True, blank=True)
    attachment_link = models.CharField(db_column='[Attachment Link]', max_length=500, null=True, blank=True)
    claimant_no_series = models.CharField(db_column='[Claimant No_ Series]', max_length=50, null=True, blank=True)
    vat_bus_posting_group = models.CharField(db_column='[VAT Bus_ Posting Group]', max_length=50, null=True, blank=True)
    
    # ==================== REJECTED ====================
    rejected = models.BooleanField(db_column='[Rejected]', default=False, null=True, blank=True)
    
    # ==================== BANK DETAILS ====================
    bank_code = models.CharField(db_column='[Bank Code]', max_length=50, null=True, blank=True)
    bank_name = models.CharField(db_column='[Bank Name]', max_length=200, null=True, blank=True)
    branch_code = models.CharField(db_column='[Branch Code]', max_length=50, null=True, blank=True)
    branch_name = models.CharField(db_column='[Branch Name]', max_length=200, null=True, blank=True)
    bank_account_name = models.CharField(db_column='[Bank Account Name]', max_length=200, null=True, blank=True)
    bank_account_no = models.CharField(db_column='[Bank Account No_]', max_length=50, null=True, blank=True)
    base_unit_of_measure = models.CharField(db_column='[Base Unit of Measure]', max_length=50, null=True, blank=True)
    voucher_no_series = models.CharField(db_column='[Vocher No_ Series]', max_length=50, null=True, blank=True)
    account_currency = models.CharField(db_column='[Account Currency]', max_length=10, null=True, blank=True)
    international_payment = models.BooleanField(db_column='[International Payment]', default=False, null=True, blank=True)
    swift_code = models.CharField(db_column='[Swift Code]', max_length=20, null=True, blank=True)
    sort_code = models.CharField(db_column='[Sort Code]', max_length=20, null=True, blank=True)
    location_source_filter = models.CharField(db_column='[Location Source Filter]', max_length=50, null=True, blank=True)
    select_field = models.BooleanField(db_column='[Select]', default=False, null=True, blank=True)
    exchange_rate = models.DecimalField(db_column='[Exchange Rate]', max_digits=18, decimal_places=6, null=True, blank=True)
    
    # ==================== SUB CATEGORY ====================
    sub_category = models.CharField(db_column='[Sub Category]', max_length=100, null=True, blank=True)
    person_living_with_disability = models.BooleanField(db_column='[Person Living with Disability]', default=False, null=True, blank=True)
    gender = models.CharField(db_column='[Gender]', max_length=10, null=True, blank=True)
    mpesa_mobile_no = models.CharField(db_column='[Mpesa Mobile No_]', max_length=20, null=True, blank=True)
    gazette_no_series = models.CharField(db_column='[Gazette No_ Series]', max_length=50, null=True, blank=True)
    gazette_no = models.CharField(db_column='[Gazette No_]', max_length=50, null=True, blank=True)
    international_bank_name = models.CharField(db_column='[International Bank Name]', max_length=200, null=True, blank=True)
    international_branch_name = models.CharField(db_column='[International Branch Name]', max_length=200, null=True, blank=True)
    home_county = models.CharField(db_column='[Home County]', max_length=50, null=True, blank=True)
    business_registration_no = models.CharField(db_column='[Business Registration No_]', max_length=50, null=True, blank=True)
    date_signed_by_hod = models.DateField(db_column='[Date Signed By HOD]', null=True, blank=True)
    name_of_deceased = models.CharField(db_column='[Name of Deceased]', max_length=200, null=True, blank=True)
    district = models.CharField(db_column='[District]', max_length=100, null=True, blank=True)
    entry_no = models.CharField(db_column='[Entry No_]', max_length=50, null=True, blank=True)
    serial_no = models.CharField(db_column='[Serial No_]', max_length=50, null=True, blank=True)
    issuing_no = models.CharField(db_column='[Issuing No_]', max_length=50, null=True, blank=True)
    cause_no = models.CharField(db_column='[Cause No_]', max_length=50, null=True, blank=True)
    type_field = models.CharField(db_column='[Type]', max_length=50, null=True, blank=True)
    title = models.CharField(db_column='[Title]', max_length=100, null=True, blank=True)
    organization = models.CharField(db_column='[Organization]', max_length=200, null=True, blank=True)
    postal_address = models.TextField(db_column='[Postal Address]', null=True, blank=True)
    address_to = models.TextField(db_column='[Address To]', null=True, blank=True)
    address_to_2 = models.TextField(db_column='[Address To 2]', null=True, blank=True)
    address_to_city = models.CharField(db_column='[Address to City]', max_length=100, null=True, blank=True)
    accept_terms = models.BooleanField(db_column='[Accept Terms & Condition]', default=False, null=True, blank=True)
    submit = models.BooleanField(db_column='[Submit]', default=False, null=True, blank=True)
    cheque_no = models.CharField(db_column='[Cheque No_]', max_length=50, null=True, blank=True)
    cheque_date = models.DateField(db_column='[Cheque Date]', null=True, blank=True)
    drawee = models.CharField(db_column='[Drawee]', max_length=200, null=True, blank=True)
    estate_name = models.CharField(db_column='[Estate Name]', max_length=200, null=True, blank=True)
    donor = models.CharField(db_column='[Donor]', max_length=200, null=True, blank=True)
    donee = models.CharField(db_column='[Donee]', max_length=200, null=True, blank=True)
    rpa_ipa_no = models.CharField(db_column='[RPA IPA No_]', max_length=50, null=True, blank=True)
    citizenship = models.CharField(db_column='[Citizenship]', max_length=50, null=True, blank=True)
    type_description = models.CharField(db_column='[Type Description]', max_length=200, null=True, blank=True)
    business_owner = models.CharField(db_column='[Business Owner]', max_length=200, null=True, blank=True)
    huduma_profile_id = models.CharField(db_column='[Huduma Profile ID]', max_length=100, null=True, blank=True)
    customer_care_id = models.CharField(db_column='[Customer Care ID]', max_length=100, null=True, blank=True)
    user_id = models.CharField(db_column='[User ID]', max_length=100, null=True, blank=True)
    claimant_action_required = models.BooleanField(db_column='[Claimant Action Required]', default=False, null=True, blank=True)
    synchronized = models.BooleanField(db_column='[Synchronized]', default=False, null=True, blank=True)
    internal_remarks = models.TextField(db_column='[Internal Remarks]', null=True, blank=True)
    iprs_name = models.CharField(db_column='[IPRS Name]', max_length=200, null=True, blank=True)
    archived = models.BooleanField(db_column='[Archived]', default=False, null=True, blank=True)
    payment_category = models.CharField(db_column='[Payment Category]', max_length=50, null=True, blank=True)
    amend = models.BooleanField(db_column='[Amend]', default=False, null=True, blank=True)
    organization_name = models.CharField(db_column='[Organization Name]', max_length=200, null=True, blank=True)
    title_description = models.CharField(db_column='[Title Description]', max_length=200, null=True, blank=True)
    verification_region = models.CharField(db_column='[Verication Region]', max_length=100, null=True, blank=True)
    doc_verification_remarks = models.TextField(db_column='[Doc verification remarks]', null=True, blank=True)
    claim_origin = models.CharField(db_column='[Claim Origin]', max_length=50, null=True, blank=True)
    draft_remarks = models.TextField(db_column='[Draft Remarks]', null=True, blank=True)
    archived_date = models.DateField(db_column='[Archived Date]', null=True, blank=True)
    archived_time = models.TimeField(db_column='[Archived Time]', null=True, blank=True)
    days_taken = models.IntegerField(db_column='[Days Taken]', null=True, blank=True)
    
    # ==================== SYSTEM FIELDS ====================
    system_id = models.CharField(db_column='[$systemId]', max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(db_column='[$systemCreatedAt]', null=True, blank=True)
    created_by_system = models.CharField(db_column='[$systemCreatedBy]', max_length=100, null=True, blank=True)
    updated_at = models.DateTimeField(db_column='[$systemModifiedAt]', null=True, blank=True)
    updated_by_system = models.CharField(db_column='[$systemModifiedBy]', max_length=100, null=True, blank=True)
    
    # ==================== VERIFICATION ====================
    verification_stage = models.CharField(db_column='[Verification Stage]', max_length=50, null=True, blank=True)
    verification_stage_date = models.DateField(db_column='[Verification Stage Date]', null=True, blank=True)
    verification_stage_time = models.TimeField(db_column='[Verification Stage Time]', null=True, blank=True)
    date_sent_for_verification = models.DateField(db_column='[Date Sent for Verification]', null=True, blank=True)
    time_sent_for_verification = models.TimeField(db_column='[Time Sent for Verification]', null=True, blank=True)
    document_verified = models.BooleanField(db_column='[Document Verified]', default=False, null=True, blank=True)
    sent_for_verification_by = models.CharField(db_column='[Sent for Verification By]', max_length=100, null=True, blank=True)
    gazetted = models.BooleanField(db_column='[Gazetted]', default=False, null=True, blank=True)
    select_claim = models.BooleanField(db_column='[SelectClaim]', default=False, null=True, blank=True)
    paid = models.BooleanField(db_column='[Paid]', default=False, null=True, blank=True)
    date_verified = models.DateField(db_column='[Date Verified]', null=True, blank=True)
    verified_by = models.CharField(db_column='[Verified By]', max_length=100, null=True, blank=True)
    publish_date = models.DateField(db_column='[Publish Date]', null=True, blank=True)
    due_date_elapsed = models.BooleanField(db_column='[Due Date Elapsed]', default=False, null=True, blank=True)
    verification_code = models.CharField(db_column='[Verification Code]', max_length=50, null=True, blank=True)
    secondary_phone_no = models.CharField(db_column='[Secondary Phone No_]', max_length=20, null=True, blank=True)
    turn_around_time = models.IntegerField(db_column='[Turn Around Time (Days)]', null=True, blank=True)
    processing_time = models.IntegerField(db_column='[Processing Time (Days)]', null=True, blank=True)
    processing_date = models.DateField(db_column='[Processing Date]', null=True, blank=True)
    document_date = models.DateField(db_column='[Document Date]', null=True, blank=True)
    document_time = models.TimeField(db_column='[Document Time]', null=True, blank=True)
    
    class Meta:
        managed = False
        db_table = '[UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]'
        app_label = 'live_operations'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.claim_no} - {self.claimant_name}"
    
    @property
    def cds_account_no(self):
        """CDS Account Number - not in this table, return None"""
        return None


class LiveOnlineClaimLine(models.Model):
    """Model for reading claim lines from live database (READ-ONLY)"""
    
    id = models.BigAutoField(primary_key=True)
    claim = models.ForeignKey(
        LiveOnlineClaim,
        on_delete=models.DO_NOTHING,
        db_column='Claim No',
        related_name='claim_lines'
    )
    line_no = models.IntegerField(db_column='Line No')
    asset_no = models.CharField(db_column='Asset No', max_length=100, blank=True, null=True)
    asset_type = models.CharField(db_column='Asset Type', max_length=50, blank=True, null=True)
    asset_value = models.DecimalField(db_column='Asset Value', max_digits=18, decimal_places=2, blank=True, null=True)
    description = models.TextField(db_column='Description', blank=True, null=True)
    holder_name = models.CharField(db_column='Holder Name', max_length=200, blank=True, null=True)
    document_path = models.CharField(db_column='Document Path', max_length=500, blank=True, null=True)
    
    class Meta:
        managed = False
        db_table = '[UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1]'
        app_label = 'live_operations'
    
    def __str__(self):
        return f"{self.claim.claim_no} - Line {self.line_no}"


class LiveDocumentReference(models.Model):
    """Model for storing document references in MSSQL live database"""
    
    doc_id = models.CharField(max_length=255, primary_key=True)
    claim_no = models.CharField(max_length=100, db_column='Claim No')
    document_type = models.CharField(max_length=50, db_column='Document Type')
    file_name = models.CharField(max_length=500, db_column='File Name')
    sharepoint_url = models.CharField(max_length=1000, db_column='SharePoint URL')
    file_size = models.BigIntegerField(db_column='File Size', null=True, blank=True)
    uploaded_by = models.CharField(max_length=100, db_column='Uploaded By', blank=True)
    uploaded_at = models.DateTimeField(db_column='Uploaded At', auto_now_add=True)
    
    class Meta:
        managed = False
        db_table = '[UFAA TRUST FUND$Claim Documents$2636ffcf-1aea-4b3a-808a-c1da12e824c1]'
        app_label = 'live_operations'
    
    def __str__(self):
        return f"{self.claim_no} - {self.file_name}"
