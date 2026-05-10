from django.db import models
from django.contrib.postgres.fields import JSONField

class Asset(models.Model):
    """Asset model matching WSDL Asset_Type, Source, Class enumerations"""
    
    ASSET_TYPE_CHOICES = [
        ('', 'Blank'),
        ('Cash', 'Cash'),
        ('Non_Cash', 'Non_Cash'),
    ]
    
    SOURCE_CHOICES = [
        ('', 'Blank'),
        ('Cash', 'Cash'),
        ('Shares', 'Shares'),
        ('Safe_Deposit', 'Safe Deposit'),
    ]
    
    CLASS_CHOICES = [
        ('', 'Blank'),
        ('Account_Balances', 'Account Balances'),
        ('Uncashed_Cheques', 'Uncashed Cheques'),
        ('Safe_Deposit_Boxes__x0026__Safe_Keeping', 'Safe Deposit Boxes & Safe Keeping'),
        ('Insurance', 'Insurance'),
        ('Government_Assets', 'Government Assets'),
        ('Misc_Cheques__x0026__Intangible_Property', 'Misc Cheques & Intangible Property'),
        ('Securities', 'Securities'),
        ('Utilities', 'Utilities'),
        ('Trust__x0026__Escrow_Accounts', 'Trust & Escrow Accounts'),
    ]
    
    # Core asset fields from WSDL
    asset_no = models.CharField(max_length=50, unique=True)
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPE_CHOICES, blank=True, default='')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, blank=True, default='')
    class_code = models.CharField(max_length=50, blank=True)
    class_field = models.CharField(max_length=50, choices=CLASS_CHOICES, blank=True, db_column='class')
    asset_code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    description_field = models.TextField(blank=True, db_column='description_')
    
    # Owner information
    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    holder_no = models.CharField(max_length=50, blank=True)
    holder_name = models.CharField(max_length=200, blank=True)
    name = models.CharField(max_length=200, blank=True)
    
    # Asset details
    value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    id_number = models.CharField(max_length=20, blank=True)
    passport_no = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=10, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    
    # Address information
    owners_postal_address = models.TextField(blank=True)
    owners_city_town = models.CharField(max_length=100, blank=True)
    owners_telephone_no = models.CharField(max_length=20, blank=True)
    
    # Specific asset fields from WSDL subpage
    interest_bearing_account = models.BooleanField(default=False)
    more_than_one_owner = models.BooleanField(default=False)
    item_no = models.IntegerField(null=True, blank=True)
    description_of_the_content = models.TextField(blank=True)
    value_of_the_content = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    safe_deposit_no = models.CharField(max_length=50, blank=True)
    no_of_remitted_shares = models.IntegerField(null=True, blank=True)
    cds_account_no = models.CharField(max_length=50, blank=True)
    cheque_no = models.CharField(max_length=50, blank=True)
    amount_due_to_owner = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    account_no = models.CharField(max_length=50, blank=True)
    currency_code = models.CharField(max_length=10, blank=True)
    drawee = models.CharField(max_length=200, blank=True)
    cheque_date = models.DateField(null=True, blank=True)
    drawee_id_number = models.CharField(max_length=20, blank=True)
    
    # Location fields
    physical_address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Status
    is_claimed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default='pending')
    synchronized = models.BooleanField(default=False)
    batch_no = models.CharField(max_length=50, blank=True)
    line_no = models.IntegerField(null=True, blank=True)
    asset_appl_no = models.CharField(max_length=50, blank=True)
    document_line_no = models.IntegerField(null=True, blank=True)
    base_unit_of_measure = models.CharField(max_length=20, blank=True)
    value_lcy = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    posted = models.BooleanField(default=False)
    location_source = models.CharField(max_length=50, blank=True)
    
    # Tracking
    reported_date = models.DateField()
    last_updated = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='created_assets')
    
    class Meta:
        db_table = 'assets'
        indexes = [
            models.Index(fields=['id_number']),
            models.Index(fields=['asset_no']),
            models.Index(fields=['holder_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.asset_no} - {self.name} - {self.holder_name}"


class AssetLocation(models.Model):
    """Asset location model for tracking physical asset locations"""
    
    LOCATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('found', 'Found'),
        ('not_found', 'Not Found'),
        ('transferred', 'Transferred'),
        ('verified', 'Verified'),
    ]
    
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name='location')
    
    # Location details
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    address = models.TextField(blank=True)
    building_name = models.CharField(max_length=200, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    room_number = models.CharField(max_length=50, blank=True)
    additional_instructions = models.TextField(blank=True)
    landmark = models.CharField(max_length=200, blank=True)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=LOCATION_STATUS_CHOICES, default='pending')
    location_source = models.CharField(max_length=50, blank=True)  # Who updated the location
    notes = models.TextField(blank=True)
    
    # Verification
    verified_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='verified_locations')
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_photos = models.JSONField(default=list, blank=True)  # Store photo URLs
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_verified = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'asset_locations'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['latitude', 'longitude']),
        ]
    
    def __str__(self):
        return f"Location for {self.asset.asset_no} - {self.status}"


class AssetTrackingHistory(models.Model):
    """Track history of asset location changes"""
    
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='tracking_history')
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    location = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'asset_tracking_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['asset']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.asset.asset_no} - {self.previous_status} -> {self.new_status} at {self.created_at}"