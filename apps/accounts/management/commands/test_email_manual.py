# test_email_manual.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def test_smtp_connection():
    smtp_server = "smtp.office365.com"
    port = 587
    username = "reunite@ufaa.go.ke"
    password = "Unclaimed1"  # Your password
    
    print(f"Testing connection to {smtp_server}:{port}")
    print(f"Username: {username}")
    
    try:
        # Create SMTP connection
        server = smtplib.SMTP(smtp_server, port)
        server.set_debuglevel(1)
        server.starttls()
        print("✅ TLS connection established")
        
        # Try to login
        server.login(username, password)
        print("✅ Authentication successful!")
        
        # Send test email
        msg = MIMEMultipart()
        msg['From'] = username
        msg['To'] = "kevinkiambe@gmail.com"
        msg['Subject'] = "Test Email from UFAA"
        
        body = "This is a test email from UFAA Reunite"
        msg.attach(MIMEText(body, 'plain'))
        
        server.send_message(msg)
        print("✅ Email sent successfully!")
        
        server.quit()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_smtp_connection()
