# apps/iprs/models.py
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class IprsSearchLog(models.Model):
    """
    Log every IPRS search request for audit and security purposes.
    Since this is used during registration (unauthenticated),
    we track IP address and user agent instead of the user.
    """
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('not_found', 'Not Found'),
        ('error', 'Error'),
        ('rate_limited', 'Rate Limited'),
        ('timeout', 'Timeout'),
    ]
    
    # Search parameters
    id_card = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name=_('ID Card Number'),
        help_text=_('National ID number that was searched')
    )
    
    # Requester info (no user FK - public endpoint)
    requested_from_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('Request IP'),
        db_index=True
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('User Agent')
    )
    device_fingerprint = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Device Fingerprint')
    )
    
    # Response data
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='error',
        db_index=True
    )
    response_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Response Data'),
        help_text=_('Full response from IPRS API')
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=_('Error Message')
    )
    
    # Extracted personal details (denormalized for quick access)
    surname = models.CharField(max_length=100, blank=True)
    other_names = models.CharField(max_length=200, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    iprs_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_('IPRS Internal ID')
    )
    searched_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('IPRS Searched At')
    )
    
    # Timing
    response_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Response Time (ms)')
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'iprs_search_logs'
        ordering = ['-created_at']
        verbose_name = _('IPRS Search Log')
        verbose_name_plural = _('IPRS Search Logs')
        indexes = [
            models.Index(fields=['id_card', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['requested_from_ip', '-created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"IPRS Search: {self.id_card} - {self.status} at {self.created_at}"
    
    @property
    def full_name(self):
        """Return the full name in Kenyan convention: Surname OtherNames"""
        parts = [self.surname, self.other_names]
        return ' '.join(p for p in parts if p).strip()
    
    @classmethod
    def get_recent_searches(cls, id_card=None, hours=24):
        """Get recent searches, optionally filtered by ID card"""
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        qs = cls.objects.filter(created_at__gte=cutoff)
        if id_card:
            qs = qs.filter(id_card=id_card)
        return qs
    
    @classmethod
    def get_search_count(cls, id_card, hours=24):
        """Count searches for a specific ID within a time window"""
        return cls.get_recent_searches(id_card, hours).count()
    
    @classmethod
    def get_ip_search_count(cls, ip_address, hours=1):
        """Count searches from a specific IP within a time window (for rate limiting)"""
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        return cls.objects.filter(
            requested_from_ip=ip_address,
            created_at__gte=cutoff
        ).count()


class IprsCache(models.Model):
    """
    Cache IPRS results to avoid repeated API calls.
    Results are cached for a configurable duration.
    """
    
    id_card = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name=_('ID Card Number')
    )
    surname = models.CharField(max_length=100, blank=True)
    other_names = models.CharField(max_length=200, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    iprs_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_('IPRS Internal ID')
    )
    raw_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Raw Response')
    )
    is_valid = models.BooleanField(
        default=True,
        verbose_name=_('Is Valid'),
        help_text=_('False if the ID was not found in IPRS')
    )
    cached_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name=_('Expires At')
    )
    
    class Meta:
        db_table = 'iprs_cache'
        ordering = ['-cached_at']
        verbose_name = _('IPRS Cache Entry')
        verbose_name_plural = _('IPRS Cache Entries')
    
    def __str__(self):
        return f"IPRS Cache: {self.id_card} ({'valid' if self.is_valid else 'invalid'})"
    
    @property
    def is_expired(self):
        """Check if cache entry has expired"""
        if not self.expires_at:
           return False   # Unsaved/new instance — not expired (yet)
        return timezone.now() > self.expires_at
    
    @property
    def full_name(self):
        """Return the full name in Kenyan convention: Surname OtherNames"""
        parts = [self.surname, self.other_names]
        return ' '.join(p for p in parts if p).strip()
    
    @classmethod
    def get_cached(cls, id_card):
        """Get a valid (non-expired) cache entry for an ID card"""
        try:
            entry = cls.objects.get(id_card=id_card)
            if entry.is_expired:
                entry.delete()
                return None
            return entry
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def set_cache(cls, id_card, data, is_valid=True, ttl_hours=24):
        """Create or update a cache entry"""
        from django.utils import timezone
        from datetime import timedelta
        
        expires_at = timezone.now() + timedelta(hours=ttl_hours)
        
        # Build other_names from first_Name + other_Name
        first_name = data.get('first_Name', '') or ''
        other_name = data.get('other_Name', '') or ''
        other_names = ' '.join(p for p in [first_name, other_name] if p).strip()
        
        entry, created = cls.objects.update_or_create(
            id_card=id_card,
            defaults={
                'surname': data.get('surname', ''),
                'other_names': other_names,
                'gender': data.get('gender', ''),
                'iprs_id': data.get('id'),
                'raw_response': data,
                'is_valid': is_valid,
                'expires_at': expires_at,
            }
        )
        return entry
    
    @classmethod
    def cleanup_expired(cls):
        """Delete all expired cache entries"""
        deleted, _ = cls.objects.filter(expires_at__lt=timezone.now()).delete()
        return deleted
