# apps/asset_tracking/models.py
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class TrackedAsset(models.Model):
    """
    One row per (asset_number, staff_email) pair.

    Uniqueness:
        unique_together on (asset_no, staff_email) ensures a staff member
        tracks a given asset only once. Re-tracking updates the same row.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('found', 'Found'),
        ('not_found', 'Not Found'),
        ('moved', 'Moved'),
        ('transferred', 'Transferred'),
    ]

    # --- Identity of the tracked asset ---
    asset_no = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Asset number from the live Unclaimed Asset table",
    )
    asset_name = models.CharField(max_length=255, blank=True)
    asset_owner = models.CharField(max_length=255, blank=True)
    holder_name = models.CharField(max_length=255, blank=True)
    holder_no = models.CharField(max_length=100, blank=True)
    asset_type = models.CharField(max_length=50, blank=True)
    source = models.CharField(max_length=50, blank=True)

    # --- Owner identifiers used during search ---
    id_number = models.CharField(max_length=50, blank=True, db_index=True)
    passport_no = models.CharField(max_length=50, blank=True, db_index=True)
    cds_account_no = models.CharField(max_length=100, blank=True, db_index=True)

    # --- Address snapshot from the live data ---
    postal_address = models.CharField(max_length=500, blank=True)
    city_town = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    physical_address = models.TextField(blank=True)

    # --- Live coordinates (from reverse geocoding, set on first track) ---
    latitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )

    # --- Tracking state ---
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    last_notes = models.TextField(blank=True)

    # --- Staff member who tracked this asset ---
    staff_email = models.EmailField(db_index=True)
    staff_name = models.CharField(max_length=255, blank=True)
    staff_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tracked_assets',
    )

    # --- The most recent tracking event ---
    last_tracked_at = models.DateTimeField(null=True, blank=True)
    last_tracked_by = models.CharField(max_length=255, blank=True)
    last_staff_latitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )
    last_staff_longitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tracked_assets'
        ordering = ['-last_tracked_at', '-created_at']
        unique_together = ('asset_no', 'staff_email')
        indexes = [
            models.Index(fields=['asset_no']),
            models.Index(fields=['staff_email']),
            models.Index(fields=['id_number']),
            models.Index(fields=['passport_no']),
            models.Index(fields=['cds_account_no']),
            models.Index(fields=['status']),
            models.Index(fields=['last_tracked_at']),
        ]

    def __str__(self):
        return f"{self.asset_no} - {self.staff_email} - {self.status}"


class AssetLocationLog(models.Model):
    """
    Immutable log of every tracking action (status change, note, etc.).
    """

    tracked_asset = models.ForeignKey(
        TrackedAsset,
        on_delete=models.CASCADE,
        related_name='location_logs',
    )
    status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)

    staff_email = models.EmailField(db_index=True)
    staff_name = models.CharField(max_length=255, blank=True)

    # Position reported at the time of this log entry
    staff_latitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )
    staff_longitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )
    distance_km = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'asset_location_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tracked_asset.asset_no} @ {self.created_at} - {self.status}"


class AssetTrackingDocument(models.Model):
    """
    Documents attached to a tracking record (photos, forms, etc.).
    """

    DOCUMENT_TYPES = [
        ('photo', 'Photo of Asset'),
        ('form', 'Completed Form'),
        ('receipt', 'Receipt'),
        ('letter', 'Letter'),
        ('id', 'Identification'),
        ('other', 'Other'),
    ]

    tracked_asset = models.ForeignKey(
        TrackedAsset,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(
        max_length=20, choices=DOCUMENT_TYPES, default='photo'
    )
    document_name = models.CharField(max_length=255, blank=True)

    file = models.FileField(
        upload_to='asset_tracking/%Y/%m/%d/',
        max_length=500,
    )
    file_size = models.IntegerField(default=0)
    file_extension = models.CharField(max_length=10, blank=True)

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asset_tracking_documents',
    )
    uploaded_by_email = models.EmailField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'asset_tracking_documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.tracked_asset.asset_no} - {self.get_document_type_display()}"
