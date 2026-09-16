from django.db import transaction
from django.core.files.uploadedfile import InMemoryUploadedFile
from apps.live_operations.services import LiveDatabaseService
from .sharepoint_service import SharePointUploadService
from .models import SharePointDocument
from django.utils import timezone

class DocumentUploadService:
    """Service for uploading documents to SharePoint and saving references"""
    
    def __init__(self):
        self.sharepoint_service = SharePointUploadService()
    
    def upload_claim_document(self, file, document_type, claim, user, claim_number=None):
        """
        Upload document for a claim and save references in both databases
        
        Args:
            file: Uploaded file object
            document_type: Type of document
            claim: Claim object (PostgreSQL)
            user: User object
            claim_number: Claim number for MSSQL reference
        
        Returns:
            dict: Upload result with file information
        """
        
        # Generate folder path
        folder_path = f"claims/{claim.created_at.year}/{claim.id}"
        
        # Upload to SharePoint
        upload_result = self.sharepoint_service.upload_file(
            file_content=file.read(),
            filename=file.name,
            folder_path=folder_path,
            claim_id=str(claim.id)
        )
        
        if not upload_result['success']:
            return upload_result
        
        # Save to PostgreSQL
        postgres_doc = self._save_to_postgresql(
            upload_result, file, document_type, claim, user
        )
        
        # Save to MSSQL (if claim_number provided)
        if claim_number:
            self._save_to_mssql(
                upload_result, file, document_type, claim_number, user
            )
        
        return {
            'success': True,
            'document_id': postgres_doc.id,
            'file_url': upload_result['file_url'],
            'file_name': upload_result['file_name'],
            'message': 'Document uploaded successfully'
        }
    
    def _save_to_postgresql(self, upload_result, file, document_type, claim, user):
        """Save document reference to PostgreSQL"""
        
        doc = SharePointDocument.objects.create(
            file_id=upload_result['file_id'],
            file_name=upload_result['file_name'],
            original_name=upload_result['original_name'],
            file_url=upload_result['file_url'],
            file_path=upload_result['file_path'],
            file_size=file.size,
            mime_type=file.content_type or 'application/octet-stream',
            document_type=document_type,
            claim=claim,
            uploaded_by=user,
            sharepoint_site=self.sharepoint_service.sharepoint_url,
            sharepoint_library=self.sharepoint_service.document_library,
            sharepoint_folder=f"claims/{claim.created_at.year}/{claim.id}",
        )
        
        return doc
    
    def _save_to_mssql(self, upload_result, file, document_type, claim_number, user):
        """Save document reference to MSSQL live database"""
        
        from apps.live_operations.services import LiveDatabaseService
        
        LiveDatabaseService.add_claim_document(
            claim_no=claim_number,
            document_type=document_type,
            sharepoint_url=upload_result['file_url'],
            file_name=upload_result['file_name'],
            file_size=file.size,
            uploaded_by=user.username
        )
    
    def get_claim_documents(self, claim_id, claim_number=None):
        """Get all documents for a claim from both databases"""
        
        documents = {
            'postgresql': [],
            'mssql': []
        }
        
        # Get from PostgreSQL
        postgres_docs = SharePointDocument.objects.filter(claim_id=claim_id)
        documents['postgresql'] = [
            {
                'id': doc.id,
                'name': doc.original_name,
                'type': doc.document_type,
                'url': doc.file_url,
                'size': doc.formatted_size,
                'uploaded_at': doc.created_at,
                'verified': doc.is_verified,
            }
            for doc in postgres_docs
        ]
        
        # Get from MSSQL if claim_number provided
        if claim_number:
            mssql_docs = LiveDatabaseService.get_claim_documents(claim_number)
            documents['mssql'] = mssql_docs
        
        return documents
    
    def verify_document(self, document_id, user):
        """Mark document as verified in PostgreSQL"""
        
        doc = SharePointDocument.objects.get(id=document_id)
        doc.is_verified = True
        doc.verified_by = user
        doc.verified_at = timezone.now()
        doc.save()
        
        return doc