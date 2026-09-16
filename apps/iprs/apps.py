# apps/iprs/apps.py
from django.apps import AppConfig


class IprsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.iprs'
    verbose_name = 'IPRS Integration'
