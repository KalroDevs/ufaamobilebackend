from pathlib import Path
from decouple import config, Csv
import os
from datetime import timedelta


from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())



# These settings are necessary for the modal windows to function
# X_FRAME_OPTIONS = "SAMEORIGIN"
X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019"]




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

    # OAuth2 authcodeflow
    #'oauth2_authcodeflow',
    'apps.oidc',  
     # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_yasg',
    'django_filters',
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
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000,http://127.0.0.1:3000', cast=Csv())

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True


# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:64086",  # Flutter web dev server
#     "http://localhost:56097",  # Flutter web dev server
    
# ]

CORS_ALLOWED_ORIGINS = [
    "https://mobile.ufaa.go.ke",  # Add your mobile domain
]




ROOT_URLCONF = 'ufaamobilebackend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 'DIRS': [],
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


# Start Guest
# Login/Logout URLs
LOGIN_URL = 'login'
# LOGIN_REDIRECT_URL = 'admin:index'
LOGOUT_REDIRECT_URL = 'landing'

LOGIN_REDIRECT_URL = 'guest_portal:admin_dashboard'
# LOGOUT_REDIRECT_URL = 'guest_portal:landing'



# Optional: Add custom admin context processor
# def admin_context(request):
#     return {
#         'site_header': 'Admin Portal',
#         'site_title': 'Admin Portal',
#     }
# # End Guest


WSGI_APPLICATION = 'ufaamobilebackend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases


# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }


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
        'HOST': '192.168.40.127',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 18 for SQL Server',
            'extra_params': 'TrustServerCertificate=yes;Encrypt=yes;Connection Timeout=30;',
        },
        'CONN_MAX_AGE': 0,  # MSSQL connection pooling
    }
}

# Database Routers for multiple databases
# DATABASE_ROUTERS = ['ufaamobilebackend.routers.DatabaseRouter']
# DATABASE_ROUTERS = ['routers.LiveDatabaseRouter']

# Database Routers for multiple databases
# Use a list to support multiple routers - they will be called in order
# DATABASE_ROUTERS = [
#     'routers.LiveDatabaseRouter',      # First, handle live database operations
#     'ufaamobilebackend.routers.DatabaseRouter',  # Then, handle default database
# ]

DATABASE_ROUTERS = ['routers.DatabaseRouter']

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/ufaa_reunify_mobile_backend/ufaa-reunify-backend/staticfiles/'
#STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
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
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('THROTTLE_ANON_RATE', default='100/day'),
        'user': config('THROTTLE_USER_RATE', default='1000/day'),
        'login': config('THROTTLE_LOGIN_RATE', default='5/minute'),
    },
}


# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=config('JWT_ACCESS_TOKEN_LIFETIME_HOURS', default=2, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# Cache (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PASSWORD': config('REDIS_PASSWORD', default=None),
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        }
    }
}


# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
#         "LOCATION": "unique-snowflake",
#     }
# }


# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'


# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Nairobi'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# File Upload Settings
DATA_UPLOAD_MAX_NUMBER_FILES = config('DATA_UPLOAD_MAX_NUMBER_FILES', default=50, cast=int)
DATA_UPLOAD_MAX_NUMBER_FIELDS = config('DATA_UPLOAD_MAX_NUMBER_FIELDS', default=1000, cast=int)
FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=10485760, cast=int)  # 10MB
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]


# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@ufaa.go.ke')
SERVER_EMAIL = config('SERVER_EMAIL', default='admin@ufaa.go.ke')


# Push Notifications
FCM_API_KEY = config('FCM_API_KEY', default='')
APNS_CERTIFICATE = config('APNS_CERTIFICATE', default='')


# Axes (Login attempt tracking)
AXES_ENABLED = config('AXES_ENABLED', default=True, cast=bool)
AXES_FAILURE_LIMIT = config('AXES_FAILURE_LIMIT', default=5, cast=int)
AXES_COOLOFF_TIME = timedelta(minutes=config('AXES_COOLOFF_TIME_MINUTES', default=15, cast=int))
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'axes/lockout.html'
AXES_IPWARE_META_PRECEDENCE_ORDER = ('HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'REMOTE_ADDR')

# Logging Configuration
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
    },
}


# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Production security settings (enabled only when DEBUG=False)
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
    CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Custom User Model
AUTH_USER_MODEL = 'accounts.User'


# Django OTP Settings
OTP_TOTP_ISSUER = 'UFAA Mobile'
OTP_TOTP_DIGITS = 6
OTP_TOTP_INTERVAL = 30


# Swagger/OpenAPI Settings
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
    }
}


# Admin URL (customize for security)
ADMIN_URL = config('ADMIN_URL', default='admin/')


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# AWS S3 Settings (for production file storage - optional)
if config('USE_AWS_S3', default=False, cast=bool):
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'



# SharePoint Configuration
SHAREPOINT_URL = os.getenv('SHAREPOINT_URL', 'https://your-domain.sharepoint.com')
SHAREPOINT_SITE = os.getenv('SHAREPOINT_SITE', '/sites/UFAA')
SHAREPOINT_DOCUMENT_LIBRARY = os.getenv('SHAREPOINT_DOCUMENT_LIBRARY', 'Claim Documents')
SHAREPOINT_CLIENT_ID = os.getenv('SHAREPOINT_CLIENT_ID', 'your-client-id')
SHAREPOINT_CLIENT_SECRET = os.getenv('SHAREPOINT_CLIENT_SECRET', 'your-client-secret')




# eCitizen OIDC Configuration
# You'll need to register your app with eCitizen to get these credentials
OIDC_RP_CLIENT_ID = '278f1ef8168611eebdbf0050560101d6'  # From eCitizen registration
OIDC_RP_CLIENT_SECRET = 'your_ecitizen_client_secret'  # From eCitizen registration

# Use discovery document URL if available (recommended)
OIDC_OP_DISCOVERY_DOCUMENT_URL = 'https://auth.ecitizen.go.ke/.well-known/openid-configuration'

# Or configure endpoints individually if discovery not available
OIDC_OP_AUTHORIZATION_URL = 'https://auth.ecitizen.go.ke/authorize'
OIDC_OP_TOKEN_URL = 'https://auth.ecitizen.go.ke/token'
OIDC_OP_USERINFO_URL = 'https://auth.ecitizen.go.ke/userinfo'
OIDC_OP_JWKS_URL = 'https://auth.ecitizen.go.ke/jwks'

# OIDC Scopes - include openid (required), profile, email
OIDC_RP_SCOPES = 'openid profile email phone'

# Enable PKCE for mobile app security (highly recommended)
OIDC_RP_USE_PKCE = True

# Fetch user info on login to get user details
OIDC_OP_FETCH_USER_INFO = True

# Auto-create users from OIDC login
OIDC_CREATE_USER = True


# Session security settings (important for production)
SESSION_COOKIE_SECURE = True  # Set to True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Login URL configuration
#from django.urls import reverse_lazy
#from django.utils.text import format_lazy
#LOGIN_URL = format_lazy('{}?fail=/', url=reverse_lazy('oidc_authentication'))
