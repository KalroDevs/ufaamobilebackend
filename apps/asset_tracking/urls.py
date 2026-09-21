# apps/asset_tracking/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path('search/', views.staff_search_assets, name='staff_search_assets'),
    path('track/', views.track_asset, name='track_asset'),
    path('my-assets/', views.my_tracked_assets, name='my_tracked_assets'),
    path('assets/<int:asset_id>/', views.tracked_asset_detail, name='tracked_asset_detail'),
    path('assets/<int:asset_id>/documents/', views.upload_tracking_document, name='upload_tracking_document'),
]
