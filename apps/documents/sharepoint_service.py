from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.client_credential import ClientCredential
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
import os
import uuid
from datetime import datetime

class SharePointUploadService:
    """Service for uploading files to SharePoint"""
    
    def __init__(self):
        self.client_id = settings.SHAREPOINT_CLIENT_ID
        self.client_secret = settings.SHAREPOINT_CLIENT_SECRET
        self.sharepoint_url = settings.SHAREPOINT_URL
        self.document_library = settings.SHAREPOINT_DOCUMENT_LIBRARY
    
    def _get_client_context(self):
        """Get SharePoint client context"""
        credentials = ClientCredential(self.client_id, self.client_secret)
        ctx = ClientContext(self.sharepoint_url).with_credentials(credentials)
        return ctx
    
    def upload_file(self, file_content, filename, folder_path, claim_id):
        """
        Upload file to SharePoint and return the file URL
        
        Args:
            file_content: Binary content of the file
            filename: Original filename
            folder_path: SharePoint folder path (e.g., "claims/2024/CLM001")
            claim_id: Claim ID for reference
        
        Returns:
            dict: Contains file_url, file_id, and sharepoint_path
        """
        try:
            ctx = self._get_client_context()
            
            # Get document library
            library = ctx.web.lists.get_by_title(self.document_library)
            ctx.load(library)
            ctx.execute_query()
            
            # Create folder path if needed
            target_folder = library.root_folder
            for part in folder_path.split('/'):
                if part:
                    folders = target_folder.folders
                    target_folder = folders.add(part)
                    ctx.execute_query()
            
            # Generate unique filename
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            target_file = target_folder.upload_file(unique_filename, file_content)
            ctx.execute_query()
            
            # Get file URL
            file_url = target_file.serverRelativeUrl
            absolute_url = f"{self.sharepoint_url}{file_url}"
            
            return {
                'success': True,
                'file_url': absolute_url,
                'file_path': file_url,
                'file_id': target_file.unique_id,
                'file_name': unique_filename,
                'original_name': filename,
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_file(self, file_path):
        """Delete file from SharePoint"""
        try:
            ctx = self._get_client_context()
            file = ctx.web.get_file_by_server_relative_path(file_path)
            file.delete_object()
            ctx.execute_query()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}