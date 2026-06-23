# apps/live_operations/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Test endpoints
    path('test/connection/', views.test_live_connection, name='test_connection'),
    path('test/data/', views.check_data_fields, name='check_data_fields'),
    
    # Search endpoints
    path('search/claims/', views.search_existing_claims, name='search_claims'),
    path('search/claims/universal/', views.search_claims_universal, name='search_claims_universal'),
    path('search/assets/', views.search_unclaimed_assets, name='search_assets'),
    
    # Claim endpoints
    path('claims/<str:claim_no>/', views.get_claim_details, name='claim_details'),
    path('claims/<str:claim_no>/status/', views.update_claim_status, name='update_status'),
    path('claims/<str:claim_no>/summary/', views.get_claim_summary, name='claim_summary'),
    path('claims/<str:claim_no>/submit/', views.submit_claim_for_review, name='submit_claim'),
    
    # Asset endpoints
    path('assets/<str:asset_no>/', views.get_asset_details, name='asset_details'),
    path('assets/user/', views.get_user_assets, name='user_assets'),
    
    # Push to live endpoints
    path('push/claim/<int:claim_id>/', views.push_claim_to_live, name='push_claim_to_live'),
    path('push/claims/', views.push_pending_claims, name='push_pending_claims'),
    path('push/status/<str:task_id>/', views.check_push_status, name='check_push_status'),
    path('push/trigger/', views.trigger_push_to_live, name='trigger_push_to_live'),
]
