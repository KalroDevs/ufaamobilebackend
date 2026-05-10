from django.db import models
from apps.accounts.models import User
from apps.claims.models import Claim

class SharePointDocument(models.Model):
    """Model for storing SharePoint document references in PostgreSQL"""
    
    DOCUMENT_TYPES = [
        ('claim_form', 'Claim Form'),
        ('indemnity_form', 'Indemnity Agreement'),
        ('id_copy', 'ID Copy'),
        ('kra_pin', 'KRA PIN Certificate'),
        ('death_certificate', 'Death Certificate'),
        ('grant_certificate', 'Grant Certificate'),
        ('holder_letter', 'Holder Letter'),
        ('bank_statement', 'Bank Statement'),
        ('payment_form', 'Payment Form'),
        ('affidavit', 'Affidavit'),
        ('power_of_attorney', 'Power of Attorney'),
        ('guardianship_deed', 'Guardianship Deed'),
        ('cr12', 'CR12 Form'),
        ('incorporation', 'Certificate of Incorporation'),
        ('other', 'Other'),
    ]
    
    # File information
    file_id = models.CharField(max_length=255, unique=True)
    file_name = models.CharField(max_length=500)
    original_name = models.CharField(max_length=500)
    file_url = models.URLField(max_length=1000)
    file_path = models.CharField(max_length=1000)
    file_size = models.BigIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    
    # Document metadata
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='sharepoint_documents', null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_sharepoint_docs')
    
    # SharePoint specific
    sharepoint_site = models.CharField(max_length=500)
    sharepoint_library = models.CharField(max_length=200)
    sharepoint_folder = models.CharField(max_length=500)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='verified_sharepoint_docs')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sharepoint_documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['file_id']),
            models.Index(fields=['claim', 'document_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.original_name} - {self.document_type}"
    
    @property
    def formatted_size(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.2f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.2f} MB"