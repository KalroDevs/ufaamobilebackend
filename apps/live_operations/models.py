from django.db import models

class LiveUnclaimedAsset(models.Model):
    """Model for reading unclaimed assets from live database (READ-ONLY)"""
    
    asset_no = models.CharField(db_column='Asset No', primary_key=True, max_length=100)
    owner_name = models.CharField(db_column='Owner Name', max_length=200)
    owner_id = models.CharField(db_column='Owner ID', max_length=50, db_index=True)
    holder_name = models.CharField(db_column='Holder Name', max_length=200)
    asset_type = models.CharField(db_column='Asset Type', max_length=50, blank=True, null=True)
    value = models.DecimalField(db_column='Value', max_digits=15, decimal_places=2, blank=True, null=True)
    physical_address = models.TextField(db_column='Physical Address', blank=True, null=True)
    status = models.CharField(db_column='Status', max_length=50, default='available')
    is_claimed = models.BooleanField(db_column='Is Claimed', default=False)
    reported_date = models.DateField(db_column='Reported Date', blank=True, null=True)
    last_updated = models.DateTimeField(db_column='Last Updated', auto_now=True)
    cds_account_no = models.CharField(db_column='CDS Account No', max_length=50, blank=True, null=True, db_index=True)
    passport_no = models.CharField(db_column='Passport No', max_length=50, blank=True, null=True, db_index=True)
    
    class Meta:
        managed = False
        db_table = '"UFAA TRUST FUND$Unclaimed Asset$2636ffcf-1aea-4b3a-808a-c1da12e824c1"'
        app_label = 'live_operations'
    
    def __str__(self):
        return f"{self.asset_no} - {self.owner_name}"


class LiveOnlineClaim(models.Model):
    """Model for reading online claims from live database (READ-ONLY)"""
    
    claim_no = models.CharField(db_column='Claim No', primary_key=True, max_length=100)
    document_date = models.DateField(db_column='Document Date', blank=True, null=True)
    category = models.CharField(db_column='Category', max_length=50, blank=True, null=True)
    claim_type = models.CharField(db_column='Claim Type', max_length=50, blank=True, null=True)
    claimant_name = models.CharField(db_column='Claimant Name', max_length=200)
    claimant_id = models.CharField(db_column='Claimant ID', max_length=50, db_index=True)
    claimant_phone = models.CharField(db_column='Claimant Phone', max_length=20, blank=True, null=True)
    claimant_email = models.EmailField(db_column='Claimant Email', max_length=200, blank=True, null=True)
    amount = models.DecimalField(db_column='Amount', max_digits=15, decimal_places=2, blank=True, null=True)
    status = models.CharField(db_column='Status', max_length=50, default='Pending')
    payment_category = models.CharField(db_column='Payment Category', max_length=50, blank=True, null=True)
    bank_name = models.CharField(db_column='Bank Name', max_length=200, blank=True, null=True)
    bank_account_no = models.CharField(db_column='Bank Account No', max_length=50, blank=True, null=True)
    mpesa_mobile_no = models.CharField(db_column='Mpesa Mobile No', max_length=20, blank=True, null=True)
    cds_account_no = models.CharField(db_column='CDS Account No', max_length=50, blank=True, null=True)
    claimant_passport = models.CharField(db_column='Claimant Passport', max_length=50, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(db_column='Created At', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='Updated At', auto_now=True)
    
    class Meta:
        managed = False
        db_table = '"UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1"'
        app_label = 'live_operations'
    
    def __str__(self):
        return f"{self.claim_no} - {self.claimant_name}"


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
    asset_value = models.DecimalField(db_column='Asset Value', max_digits=15, decimal_places=2, blank=True, null=True)
    description = models.TextField(db_column='Description', blank=True, null=True)
    holder_name = models.CharField(db_column='Holder Name', max_length=200, blank=True, null=True)
    document_path = models.CharField(db_column='Document Path', max_length=500, blank=True, null=True)
    
    class Meta:
        managed = False
        db_table = '"UFAA TRUST FUND$Online Claim Lines$2636ffcf-1aea-4b3a-808a-c1da12e824c1"'
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
        db_table = '"UFAA TRUST FUND$Claim Documents$2636ffcf-1aea-4b3a-808a-c1da12e824c1"'
        app_label = 'live_operations'
    
    def __str__(self):
        return f"{self.claim_no} - {self.file_name}"