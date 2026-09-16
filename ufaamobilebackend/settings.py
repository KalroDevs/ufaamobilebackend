from pathlib import Path
from decouple import config, Csv
import os
from datetime import timedelta
import logging

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = ['mobile.ufaa.go.ke', '196.201.226.101', '196.202.210.90']

# These settings are necessary for the modal windows to function
X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019"]

# ==================== SESSION ENGINE CONFIGURATION ====================
# Use database backend for maximum reliability
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_AGE = 60 * 60 * 72  # 259,200 seconds (3 days)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True  
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'

# ==================== CSRF BASE CONFIGURATION ====================
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_HTTPONLY = False  # Must be False to allow frontend architectures to read it
CSRF_TRUSTED_ORIGINS = [
    'https://mobile.ufaa.go.ke',
    'http://localhost:8000',
]

# Application definition
INSTALLED_APPS = [
    'admin_interface',       # Must be first
    'colorfield',            # Required for color picker functionality
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # OAuth2 Core / OIDC
    'apps.oidc',  
    
    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_yasg',
    'django_filters',
    'django_celery_beat',
    'django_celery_results',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'axes',
    
    # Local apps - UFAA Kenya
    'apps.accounts',
    'apps.assets',
    'apps.claims',
    'apps.payments',
    'apps.documents',
    'apps.notifications',
    'apps.tracking',
    'apps.reports',
    'apps.api',
    'apps.soap',
    'apps.live_operations',
    'apps.iprs',

    'guest_portal', 
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'axes.middleware.AxesMiddleware',
    'apps.api.middleware.APIJSONMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "https://mobile.ufaa.go.ke",
#    "http://localhost:52225/",
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

ROOT_URLCONF = 'ufaamobilebackend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Auth Redirection Targets
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = 'landing'
LOGIN_REDIRECT_URL = 'guest_portal:admin_dashboard'

WSGI_APPLICATION = 'ufaamobilebackend.wsgi.application'

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'ufaa_mobile_app_24_db',
        'USER': 'ufaa_mobile_user',
        'PASSWORD': 'P3nd@ufaaDb_U334a',
        'HOST': 'localhost',
        'PORT': '5432',
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    },
    'ereunify': {
        'ENGINE': 'mssql',
        'NAME': 'UFAAv24',
        'USER': 'ereunifymobile',
        'PASSWORD': 'R3un1fy@ufaa',
        'HOST': '192.168.40.54',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 18 for SQL Server',
            'extra_params': 'TrustServerCertificate=yes;Encrypt=yes;Connection Timeout=30;',
        },
        'CONN_MAX_AGE': 0,
    }
}

DATABASE_ROUTERS = ['routers.DatabaseRouter']

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# Static files layout
STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/ufaa_reunify_mobile_backend/ufaa-reunify-backend/staticfiles/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

BASE_URL = os.environ.get('BASE_URL', 'https://mobile.ufaa.go.ke/')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT, exist_ok=True)

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'apps.api.exceptions.custom_exception_handler',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': config('REST_PAGE_SIZE', default=20, cast=int),
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [],
    #'DEFAULT_THROTTLE_CLASSES': [
    #    'rest_framework.throttling.AnonRateThrottle',
    #    'rest_framework.throttling.UserRateThrottle',
    #],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('THROTTLE_ANON_RATE', default='100/day'),
        'user': config('THROTTLE_USER_RATE', default='1000/day'),
        'login': config('THROTTLE_LOGIN_RATE', default='5/minute'),
    },
    'UNAUTHENTICATED_USER': None,
    'UNAUTHENTICATED_TOKEN': None,
}

# JWT Engine Token Lifetimes
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=config('JWT_ACCESS_TOKEN_LIFETIME_HOURS', default=2, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Database Cache Layer Setup
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
        'OPTIONS': {
            'MAX_ENTRIES': 10000,
            'CULL_FREQUENCY': 3,
        }
    }
}

# Redis Configuration with Password
REDIS_HOST = config('REDIS_HOST', default='localhost')
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)
REDIS_DB = config('REDIS_DB', default=0, cast=int)
REDIS_PASSWORD = config('REDIS_PASSWORD', default='P3nd@ufaaDb_U334aR')
REDIS_URL = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'


# Celery Configuration
#CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Nairobi'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Celery Beat Schedule
CELERY_BEAT_SCHEDULE = {
    'push-claims-to-live-every-3-hours': {
        'task': 'apps.live_operations.tasks.push_pending_claims_to_live',
        'schedule': 10800.0,  # 3 hours in seconds
        'options': {
            'expires': 3600.0,  # Task expires after 1 hour if not started
        }
    },
    'sync-claim-statuses-every-6-hours': {
        'task': 'apps.live_operations.tasks.sync_claim_statuses',
        'schedule': 21600.0,  # 6 hours in seconds
        'options': {
            'expires': 3600.0,
        }
    },
}







# File Upload Settings
FILE_UPLOAD_PERMISSIONS = 0o644
DATA_UPLOAD_MAX_NUMBER_FILES = config('DATA_UPLOAD_MAX_NUMBER_FILES', default=50, cast=int)
DATA_UPLOAD_MAX_NUMBER_FIELDS = config('DATA_UPLOAD_MAX_NUMBER_FIELDS', default=1000, cast=int)
FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=10485760, cast=int) # 10MB

FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]

def ensure_directory_permissions(path):
    if os.path.exists(path):
        os.chmod(path, 0o755)

# ==================== EMAIL CONFIGURATION ====================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.office365.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

EMAIL_HOST_USER = 'reunite@ufaa.go.ke'
EMAIL_HOST_PASSWORD = 'Rudisha1'

DEFAULT_FROM_EMAIL = f'UFAA Reunite <{EMAIL_HOST_USER}>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ADMIN_EMAIL = 'https://mobile.ufaa.go.ke'

EMAIL_TIMEOUT = 30  
EMAIL_SUBJECT_PREFIX = '[UFAA] '  
EMAIL_TEMPLATES_DIR = BASE_DIR / 'apps' / 'accounts' / 'templates' / 'emails'

VERIFICATION_EMAIL_EXPIRY_HOURS = 24
VERIFICATION_CODE_LENGTH = 6
MAX_VERIFICATION_ATTEMPTS = 3
RESEND_VERIFICATION_COOLDOWN_SECONDS = 60
FRONTEND_URL = 'https://mobile.ufaa.go.ke'

# Push Notifications
FCM_API_KEY = config('FCM_API_KEY', default='')
APNS_CERTIFICATE = config('APNS_CERTIFICATE', default='')

# Axes Brute Force Login Defense Configuration
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = timedelta(minutes=5)
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True 
AXES_LOCKOUT_TEMPLATE = None 
AXES_HANDLER = 'axes.handlers.cache.AxesCacheHandler'
AXES_IPWARE_META_PRECEDENCE_ORDER = ('HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'REMOTE_ADDR')

# Global Core Security Elements
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ==================== ENVIRONMENT SPECIFIC COOKIE SECURITY ====================
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # Secure production cross-origin settings (Allows working alongside OAuth/eCitizen hooks)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SAMESITE = 'None'
else:
    # Local fallback allowing plain HTTP configurations without breaking cookie drop
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

# Custom Structural Models
AUTH_USER_MODEL = 'accounts.User'

# OTP Settings
OTP_TOTP_ISSUER = 'UFAA Mobile'
OTP_TOTP_DIGITS = 6
OTP_TOTP_INTERVAL = 30

# Swagger Engine Layout
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
    },
    'SECURITY_REQUIREMENTS': None,
}

ADMIN_URL = config('ADMIN_URL', default='admin/')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# SharePoint Integration Coordinates
SHAREPOINT_URL = os.getenv('SHAREPOINT_URL', 'https://your-domain.sharepoint.com')
SHAREPOINT_SITE = os.getenv('SHAREPOINT_SITE', '/sites/UFAA')
SHAREPOINT_DOCUMENT_LIBRARY = os.getenv('SHAREPOINT_DOCUMENT_LIBRARY', 'Claim Documents')
SHAREPOINT_CLIENT_ID = os.getenv('SHAREPOINT_CLIENT_ID', 'your-client-id')
SHAREPOINT_CLIENT_SECRET = os.getenv('SHAREPOINT_CLIENT_SECRET', 'your-client-secret')

# eCitizen OIDC Registry Parameters
OIDC_RP_CLIENT_ID = 'ac4c1bfde666365f26e5101d865ab113'  
OIDC_RP_CLIENT_SECRET = 'dPIkLVPWykaYtQIAh3J1TgNwhCJio90wLy+DIw/0hqw='  
OIDC_OP_AUTHORIZATION_URL = 'https://accounts.ecitizen.go.ke/oauth/authorize'
OIDC_OP_TOKEN_URL = 'https://accounts.ecitizen.go.ke/oauth/access-token'
OIDC_OP_USERINFO_URL = 'https://accounts.ecitizen.go.ke/api/user-info'
OIDC_RP_SCOPES = 'openid'

# ==================== LOGGING FRAMEWORK CONFIGURATION ====================
LOG_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'django.log'),
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'errors.log'),
            'formatter': 'verbose',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': config('LOG_LEVEL_DJANGO', default='INFO'),
            'propagate': True,
        },
        'apps': {
            'handlers': ['file', 'error_file', 'console'],
            'level': config('LOG_LEVEL_APPS', default='DEBUG'),
            'propagate': True,
        },
        'django.contrib.sessions': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django.security.csrf': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
