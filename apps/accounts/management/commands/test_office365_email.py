# apps/accounts/management/commands/test_office365_email.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

class Command(BaseCommand):
    help = 'Test Office 365 email configuration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email address to send test email to',
            required=True,
        )
    
    def handle(self, *args, **options):
        recipient_email = options['email']
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write("TESTING OFFICE 365 EMAIL CONFIGURATION")
        self.stdout.write("="*60)
        
        self.stdout.write(f"\n📧 Email Settings:")
        self.stdout.write(f"   Host: {settings.EMAIL_HOST}")
        self.stdout.write(f"   Port: {settings.EMAIL_PORT}")
        self.stdout.write(f"   User: {settings.EMAIL_HOST_USER}")
        self.stdout.write(f"   From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"   TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"   SSL: {settings.EMAIL_USE_SSL}")
        
        # Test 1: Simple email
        self.stdout.write("\n\n📤 Test 1: Sending simple text email...")
        try:
            send_mail(
                subject='Test Email from UFAA (Office 365)',
                message='This is a test email to verify SMTP configuration with Office 365.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS("\n✅ Simple text email sent successfully!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Failed to send simple text email: {e}"))
            return
        
        # Test 2: HTML email
        self.stdout.write("\n📤 Test 2: Sending HTML email...")
        try:
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background: linear-gradient(135deg, #262561 0%, #1a1a4a 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }
                    .header h1 { margin: 0; color: #E4B355; }
                    .content { padding: 20px; background: #ffffff; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px; }
                    .footer { background-color: #f5f5f5; padding: 10px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }
                    .success { color: green; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>UFAA Reunite</h1>
                        <p>Unclaimed Financial Assets Authority</p>
                    </div>
                    <div class="content">
                        <h2 class="success">✓ Email Configuration Successful!</h2>
                        <p>Your Office 365 SMTP configuration is working correctly.</p>
                        <p><strong>Configuration Details:</strong></p>
                        <ul>
                            <li>SMTP Host: smtp.office365.com</li>
                            <li>Port: 587</li>
                            <li>Encryption: STARTTLS</li>
                            <li>Authentication: Yes</li>
                            <li>From Email: reunite@ufaa.go.ke</li>
                        </ul>
                        <p>You are now ready to send:</p>
                        <ul>
                            <li>Verification emails</li>
                            <li>Password reset emails</li>
                            <li>Claim status notifications</li>
                            <li>System alerts</li>
                        </ul>
                    </div>
                    <div class="footer">
                        <p>&copy; 2024 UFAA Reunite. All rights reserved.</p>
                        <p>This is an automated test message. Please do not reply.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            email = EmailMultiAlternatives(
                subject='UFAA - Office 365 SMTP Configuration Test',
                body='Plain text version of the email.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            self.stdout.write(self.style.SUCCESS("\n✅ HTML email sent successfully!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Failed to send HTML email: {e}"))
            return
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("✅ EMAIL CONFIGURATION TEST COMPLETED SUCCESSFULLY!"))
        self.stdout.write(f"📧 Test email sent to: {recipient_email}")
        self.stdout.write("="*60)
