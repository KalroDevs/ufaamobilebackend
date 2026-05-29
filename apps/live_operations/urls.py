from django.urls import path
from . import views

urlpatterns = [
    path('search/assets/', views.search_unclaimed_assets, name='search_assets'),
    path('search/claims/', views.search_existing_claims, name='search_claims'),
    path('claims/create/', views.create_claim, name='create_claim'),
    path('claims/<str:claim_no>/status/', views.update_claim_status, name='update_status'),
]
