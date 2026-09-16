# apps/iprs/urls.py
from django.urls import path
from . import views

# app_name = 'iprs'

urlpatterns = [
    # Public endpoints (used during registration)
    path('lookup/', views.IprsLookupView.as_view(), name='lookup'),
    path('verify/', views.IprsVerifyView.as_view(), name='verify'),
 #   path('bulk-lookup/', views.IprsBulkLookupView.as_view(), name='bulk-lookup'),
    
    # Staff-only endpoints
    path('search-logs/', views.IprsSearchLogListView.as_view(), name='search-logs'),
    path('cache/', views.IprsCacheListView.as_view(), name='cache'),
]
