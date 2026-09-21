# apps/documents/urls.py
from django.urls import path

from . import views


app_name = 'documents'


urlpatterns = [
    # ============================================================
    # PER-CLAIM ENDPOINTS
    # ============================================================

    # POST /api/claims/{claim_id}/documents/upload/
    #   Upload a document for a claim. Bytes go to SharePoint.
    path(
        'claims/<int:claim_id>/documents/upload/',
        views.upload_claim_document,
        name='upload_document',
    ),

    # GET  /api/claims/{claim_id}/documents/
    #   List all documents attached to a claim.
    path(
        'claims/<int:claim_id>/documents/',
        views.get_claim_documents,
        name='get_documents',
    ),

    # ============================================================
    # PER-DOCUMENT ENDPOINTS
    # ============================================================

    # GET /api/documents/{document_id}/view/
    #   302 redirect to the SharePoint download URL.
    #   Used by the admin's View link and the mobile app.
    path(
        'documents/<int:document_id>/view/',
        views.view_document,
        name='view_document',
    ),

    # GET /api/documents/{document_id}/download/
    #   302 redirect to the SharePoint download URL (same as view,
    #   but semantically distinct for clients).
    path(
        'documents/<int:document_id>/download/',
        views.download_document,
        name='download_document',
    ),

    # GET /api/documents/{document_id}/stream/
    #   Stream the bytes through Django. Use only when the SharePoint
    #   URL must not be exposed to the client.
    path(
        'documents/<int:document_id>/stream/',
        views.stream_document,
        name='stream_document',
    ),

    # POST /api/documents/{document_id}/verify/
    #   Staff-only verification.
    path(
        'documents/<int:document_id>/verify/',
        views.verify_document,
        name='verify_document',
    ),
]
