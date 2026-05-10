from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    # This must match the full path from the project root
    name = 'apps.accounts'
