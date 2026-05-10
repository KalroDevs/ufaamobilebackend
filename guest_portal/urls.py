from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# No app_name to avoid namespace conflicts
# app_name = 'guest_portal'  # Comment this out or remove

urlpatterns = [
    # Landing page
    path('', views.landing_page, name='landing'),
    
    # Custom login/logout views
    path('login/', auth_views.LoginView.as_view(template_name='admin/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]