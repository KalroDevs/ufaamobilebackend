from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import reverse
from django.utils.html import format_html

class CustomAdminSite(admin.AdminSite):
    site_header = 'Admin Portal'
    site_title = 'Admin Portal'
    index_title = 'Dashboard'
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        # Add custom URLs if needed
        return urls
    
    def index(self, request, extra_context=None):
        # Custom context for admin index
        from .views import admin_dashboard
        return admin_dashboard(request)

# Use custom admin site
admin_site = CustomAdminSite(name='myadmin')

# Register your models with the custom admin site
# admin_site.register(YourModel)