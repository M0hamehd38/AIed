"""Classyar settings. Everything environment-specific comes from env vars (see .env.example)."""
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


DEBUG = env_bool('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-insecure-key' if DEBUG else '')
if not SECRET_KEY:
    raise RuntimeError('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off')
ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o]

INSTALLED_APPS = [
    'daphne',  # ASGI server: runserver then serves WebSockets too
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.accounts',
    'apps.courses',
    'apps.insights',
    'apps.audit',
    'apps.audio',
    'apps.panel',
    'apps.site',
    'apps.live',
    'channels',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.IdleTimeoutMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# live sessions: Redis when there is more than one server process, otherwise in memory
REDIS_URL = os.environ.get('REDIS_URL')
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer', 'CONFIG': {'hosts': [REDIS_URL]}}
                  if REDIS_URL else {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


def database_from_url(url):
    if not url:
        # development only. Live sessions write in bursts (a class answering at once): wait for the lock
        # instead of failing, and let readers and the writer work side by side (WAL)
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3',
                'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE',
                            'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;'}}
    u = urlparse(url)
    return {'ENGINE': 'django.db.backends.postgresql', 'NAME': u.path.lstrip('/'), 'USER': u.username or '',
            'PASSWORD': u.password or '', 'HOST': u.hostname or '', 'PORT': str(u.port or 5432),
            # reuse connections across requests instead of reconnecting every time
            'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True}


DATABASES = {'default': database_from_url(os.environ.get('DATABASE_URL'))}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = '/?auth=login'
LOGIN_REDIRECT_URL = '/t/'
LOGOUT_REDIRECT_URL = '/'

LANGUAGE_CODE = 'fa'
LANGUAGES = [('fa', 'فارسی')]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if not DEBUG
                    else 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

SESSION_COOKIE_HTTPONLY = True
# signed in until « خروج », or until 2 hours without use (see apps.accounts.middleware)
SESSION_COOKIE_AGE = 2 * 60 * 60
# https-only cookies in production; DJANGO_SSL_REDIRECT=0 is for trying the image over plain http locally
HTTPS = not DEBUG and env_bool('DJANGO_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = HTTPS
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = HTTPS
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if HTTPS else 0

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# keep personal data out of logs: no request bodies, only status lines
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
