# apps/oidc/apps.py
from django.apps import AppConfig

class OIDCConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.oidc'
    label = 'oidc'
    verbose_name = 'OIDC Authentication'
