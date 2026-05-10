# SharePoint Configuration
from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.client_credential import ClientCredential
from django.conf import settings
import os

class SharePointConfig:
    """SharePoint configuration and connection manager"""
    
    # SharePoint connection settings
    SHAREPOINT_URL = settings.SHAREPOINT_URL
    SHAREPOINT_SITE = settings.SHAREPOINT_SITE
    SHAREPOINT_DOCUMENT_LIBRARY = settings.SHAREPOINT_DOCUMENT_LIBRARY
    CLIENT_ID = settings.SHAREPOINT_CLIENT_ID
    CLIENT_SECRET = settings.SHAREPOINT_CLIENT_SECRET
    
    @classmethod
    def get_client_context(cls):
        """Get SharePoint client context"""
        credentials = ClientCredential(cls.CLIENT_ID, cls.CLIENT_SECRET)
        ctx = ClientContext(cls.SHAREPOINT_URL).with_credentials(credentials)
        return ctx
    
    @classmethod
    def get_document_library(cls):
        """Get SharePoint document library"""
        ctx = cls.get_client_context()
        web = ctx.web
        lists = web.lists
        target_list = lists.get_by_title(cls.SHAREPOINT_DOCUMENT_LIBRARY)
        ctx.load(target_list)
        ctx.execute_query()
        return target_list
    
    @classmethod
    def create_folder_if_not_exists(cls, folder_path):
        """Create folder structure in SharePoint if it doesn't exist"""
        ctx = cls.get_client_context()
        library = cls.get_document_library()
        
        # Create folder path
        folder = library.root_folder
        for part in folder_path.split('/'):
            if part:
                folder = folder.folders.add(part)
                ctx.execute_query()
        
        return folder