from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "UFAA Reunify Mobile Admin"  
admin.site.site_title = "UFAA Reunify Mobile Admin"         
admin.site.index_title = "Welcome to the UFAA Mobile Dashboard" 


urlpatterns = [
    path('', include('guest_portal.urls')),
    path('admin/logout/', auth_views.LogoutView.as_view(), name='admin_logout'),
    path('admin/', admin.site.urls),
    path('api/live/', include('apps.live_operations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


