# apps/documents/views.py
import logging
import mimetypes
import os

from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.claims.models import Claim, ClaimDocument
from .upload_service import DocumentUploadService

logger = logging.getLogger(__name__)

upload_service = DocumentUploadService()


# ============================================================ #
# UPLOAD
# ============================================================ #

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_claim_document(request, claim_id):
    """
    Upload a document for a claim.

    The bytes are written to SharePoint by ``ClaimDocument.file``
    (storage=storages['sharepoint']). Only metadata is stored in
    Postgres. This view never touches ``.path``.
    """
    claim = get_object_or_404(Claim, id=claim_id)

    file = request.FILES.get('file')
    document_type = request.data.get('document_type')

    if not file or not document_type:
        return Response(
            {'error': 'file and document_type are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    claim_number = request.data.get('claim_number')

    result = upload_service.upload_claim_document(
        file=file,
        document_type=document_type,
        claim=claim,
        user=request.user,
        claim_number=claim_number,
    )

    if result.get('success'):
        return Response(result, status=status.HTTP_201_CREATED)
    return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================ #
# LIST
# ============================================================ #

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_claim_documents(request, claim_id):
    """
    List all documents attached to a claim.

    Each entry includes a pre-resolved ``file_url``. The service layer
    handles SharePoint URL resolution; this view never touches ``.path``.
    """
    claim = get_object_or_404(Claim, id=claim_id)
    claim_number = request.query_params.get('claim_number')

    documents = upload_service.get_claim_documents(claim_id, claim_number)

    return Response(
        {
            'claim_id': claim.id,
            'claim_no': claim.no,
            'count': len(documents),
            'documents': documents,
        },
        status=status.HTTP_200_OK,
    )


# ============================================================ #
# VIEW / DOWNLOAD / STREAM
# ============================================================ #

def _resolve_document_url(document):
    """
    Resolve the storage URL for a document.

    Returns ``None`` if the storage backend cannot produce a URL or if
    the document has no file attached.
    """
    if not document.file:
        return None
    try:
        return document.file.url
    except NotImplementedError:
        logger.warning(
            "Storage backend cannot produce a URL for document %s",
            document.pk,
        )
        return None
    except Exception as exc:
        logger.exception(
            "Error resolving URL for document %s: %s", document.pk, exc
        )
        return None


def _check_document_access(document, user):
    """Return True if the user may access this document."""
    if user.is_staff or getattr(user, 'role', '') in ['staff', 'admin']:
        return True
    return document.claim.claimant == user


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_document(request, document_id):
    """
    Redirect the client to the SharePoint-hosted file.

    We never call ``document.file.path`` — SharePointStorage raises
    ``NotImplementedError`` for cloud files. Instead, ``FileField.url``
    resolves through the storage backend and returns a short-lived,
    pre-authenticated Microsoft Graph download link (cached for ~50
    minutes).
    """
    document = get_object_or_404(ClaimDocument, id=document_id)

    if not _check_document_access(document, request.user):
        return Response(
            {"error": "You do not have permission to view this document."},
            status=status.HTTP_403_FORBIDDEN,
        )

    file_url = _resolve_document_url(document)
    if not file_url:
        return Response(
            {"error": "File not found on storage backend."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 302 sends the browser straight to SharePoint.
    return HttpResponseRedirect(file_url)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_document(request, document_id):
    """
    Download variant — redirects to SharePoint.

    SharePoint already serves the file with a sensible
    ``Content-Disposition`` header, so no further work is needed here.
    """
    return view_document(request, document_id)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stream_document(request, document_id):
    """
    Stream the bytes through Django.

    Use this only when the SharePoint URL must not be exposed to the
    client. It holds a worker for the duration of the transfer, so it
    is intentionally kept off the hot path used by the admin and the
    mobile app.

    ``FileField.open('rb')`` delegates to the storage backend. For
    ``SharePointStorage`` that downloads the file into a spooled temp
    file and returns a file-like object — no local path required.
    """
    document = get_object_or_404(ClaimDocument, id=document_id)

    if not _check_document_access(document, request.user):
        return Response(
            {"error": "You do not have permission to view this document."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not document.file:
        return Response(
            {"error": "Document has no file attached."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        # ✅ Delegates to SharePointStorage._open() — no .path call.
        file_handle = document.file.open('rb')
    except FileNotFoundError:
        raise Http404("File not found on storage backend.")
    except Exception as exc:
        logger.exception(
            "Error opening file for document %s: %s", document_id, exc
        )
        return Response(
            {"error": f"Error opening file: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    content_type = (
        mimetypes.guess_type(document.file.name)[0]
        or "application/octet-stream"
    )

    response = FileResponse(
        file_handle,
        content_type=content_type,
        as_attachment=False,
    )
    filename = os.path.basename(document.file.name)
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# ============================================================ #
# VERIFY
# ============================================================ #

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_document(request, document_id):
    """
    Mark a document as verified (staff only).
    """
    if not getattr(request.user, 'is_staff_member', False):
        return Response(
            {'error': 'Only staff can verify documents'},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        doc = upload_service.verify_document(document_id, request.user)
    except ClaimDocument.DoesNotExist:
        return Response(
            {'error': f'Document {document_id} not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as exc:
        logger.exception(
            "Error verifying document %s: %s", document_id, exc
        )
        return Response(
            {'error': str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            'message': 'Document verified successfully',
            'document_id': doc.id,
            'verified_at': doc.verified_at,
        },
        status=status.HTTP_200_OK,
    )
