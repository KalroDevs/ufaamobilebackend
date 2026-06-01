# apps/accounts/utils/email_service.py
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails using Gmail SMTP"""
    
    @staticmethod
    def send_verification_email(user, verification_token, verification_code):
        """Send email verification email"""
        try:
            # Build verification URL
            frontend_url = settings.FRONTEND_URL.rstrip('/')
            verification_url = f"{frontend_url}/verify-email?token={verification_token}&email={user.email}"
            
            # Prepare context for template
            context = {
                'user': user,
                'verification_url': verification_url,
                'verification_code': verification_code,
                'expiry_hours': 24,
                'year': timezone.now().year,
                'app_name': 'UFAA Reunite',
                'support_email': 'reunite@ufaa.go.ke',
                'support_phone': '020 4023000',
                'frontend_url': frontend_url,
            }
            
            # Render HTML email
            html_message = render_to_string('emails/verification_email.html', context)
            plain_message = strip_tags(html_message)
            
            # Send email
            email = EmailMultiAlternatives(
                subject='Verify Your UFAA Account',
                body=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
                reply_to=['reunite@ufaa.go.ke'],
            )
            email.attach_alternative(html_message, "text/html")
            
            # Send with timeout
            result = email.send(fail_silently=False)
            
            if result:
                logger.info(f"✅ Verification email sent to {user.email}")
                return True
            else:
                logger.error(f"❌ Failed to send verification email to {user.email}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Email error for {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def test_email_connection():
        """Test the email configuration"""
        try:
            send_mail(
                subject='Test Email from UFAA',
                message='This is a test email to verify SMTP configuration.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.EMAIL_HOST_USER],  # Send to yourself
                fail_silently=False,
            )
            logger.info("✅ Test email sent successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Test email failed: {str(e)}")
            return False
