# apps/accounts/management/commands/test_email.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from apps.accounts.utils.email_service import EmailService

class Command(BaseCommand):
    help = 'Test email configuration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email address to send test email to',
        )
    
    def handle(self, *args, **options):
        self.stdout.write("Testing email configuration...")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        
        # Test connection
        success = EmailService.test_email_connection()
        
        if success:
            self.stdout.write(self.style.SUCCESS("✅ Email configuration is working!"))
        else:
            self.stdout.write(self.style.ERROR("❌ Email configuration failed!"))
            self.stdout.write("Check your EMAIL_HOST_PASSWORD and 2FA settings.")
