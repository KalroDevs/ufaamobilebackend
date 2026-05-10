from django.urls import path
from . import views

urlpatterns = [
    path('claims/<int:claim_id>/documents/upload/', 
         views.upload_claim_document, 
         name='upload_document'),
    path('claims/<int:claim_id>/documents/', 
         views.get_claim_documents, 
         name='get_documents'),
    path('documents/<int:document_id>/verify/', 
         views.verify_document, 
         name='verify_document'),
]