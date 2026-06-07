# test_email.py
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ufaamobilebackend.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def test_email_configuration():
    """Test the email configuration"""
    print("\n" + "="*60)
    print("TESTING EMAIL CONFIGURATION")
    print("="*60)
    
    print(f"\n📧 Email Settings:")
    print(f"   Host: {settings.EMAIL_HOST}")
    print(f"   Port: {settings.EMAIL_PORT}")
    print(f"   User: {settings.EMAIL_HOST_USER}")
    print(f"   From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"   TLS: {settings.EMAIL_USE_TLS}")
    print(f"   SSL: {settings.EMAIL_USE_SSL}")
    
    # Test 1: Send simple text email
    print("\n📤 Test 1: Sending simple text email...")
    try:
        send_mail(
            subject='Test Email from UFAA',
            message='This is a test email to verify SMTP configuration with Office 365.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['kevinkiambe@gmail.com'],
            fail_silently=False,
        )
        print("✅ Simple text email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send simple text email: {e}")
        return False
    
    # Test 2: Send HTML email
    print("\n📤 Test 2: Sending HTML email...")
    try:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #262561; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .footer { background-color: #f5f5f5; padding: 10px; text-align: center; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>UFAA Reunite</h1>
                </div>
                <div class="content">
                    <h2>Test Email</h2>
                    <p>This is a test HTML email from UFAA Reunite.</p>
                    <p>Your Office 365 SMTP configuration is working correctly!</p>
                    <p><strong>Configuration Details:</strong></p>
                    <ul>
                        <li>SMTP Host: smtp.office365.com</li>
                        <li>Port: 587</li>
                        <li>TLS: Enabled</li>
                        <li>From: reunite@ufaa.go.ke</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>&copy; 2024 UFAA Reunite. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        email = EmailMultiAlternatives(
            subject='UFAA - Office 365 SMTP Test (HTML)',
            body='This is a plain text version of the email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=['kevinkiambe@gmail.com'],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        print("✅ HTML email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send HTML email: {e}")
        return False
    
    print("\n" + "="*60)
    print("✅ EMAIL CONFIGURATION TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    return True

if __name__ == "__main__":
    test_email_configuration()
