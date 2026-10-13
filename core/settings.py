from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Không để .env ghi đè biến môi trường do host cung cấp (override=False)
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# Môi trường chạy (local / production)
ENVIRONMENT = os.getenv("ENVIRONMENT", "local").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# DEBUG: Production bắt buộc False, Local mặc định True
if IS_PRODUCTION:
    DEBUG = env_bool("DEBUG", False)
    if DEBUG:
        raise ImproperlyConfigured("DEBUG must be set to False in production.")
else:
    DEBUG = env_bool("DEBUG", True)

# SECRET_KEY validation
_raw_secret = os.getenv("SECRET_KEY", "").strip()
_insecure_defaults = {
    "",
    "change-me-in-production",
    "django-insecure-change-me",
}
if IS_PRODUCTION:
    if not _raw_secret or _raw_secret in _insecure_defaults or _raw_secret.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            "SECRET_KEY must be configured with a secure, unique production value when running in production."
        )
    SECRET_KEY = _raw_secret
else:
    SECRET_KEY = _raw_secret or "django-insecure-local-dev-contentops-hub"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1" if not IS_PRODUCTION else "")
if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty in production.")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Cấu hình Feature Flag: BILLING_ENABLED
BILLING_ENABLED = env_bool("BILLING_ENABLED", False)

PAYOS_WEBHOOK_SECRET = os.getenv("PAYOS_WEBHOOK_SECRET", "")
SEPAY_WEBHOOK_SECRET = os.getenv("SEPAY_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PRO_PLAN_PRICE = int(os.getenv("PRO_PLAN_PRICE", "199000") or 199000)
VIETQR_BANK_ID = os.getenv("VIETQR_BANK_ID", "")
VIETQR_ACCOUNT_NO = os.getenv("VIETQR_ACCOUNT_NO", "")
VIETQR_ACCOUNT_NAME = os.getenv("VIETQR_ACCOUNT_NAME", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.billing_context",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# Database Configuration
database_url = os.getenv("DATABASE_URL", "").strip()

if IS_PRODUCTION:
    if not database_url:
        raise ImproperlyConfigured(
            "DATABASE_URL must be configured in production (PostgreSQL required). SQLite fallback is only allowed in local development."
        )
    if database_url.startswith("sqlite"):
        raise ImproperlyConfigured(
            "SQLite is not permitted in production. PostgreSQL is required via DATABASE_URL."
        )
    DATABASES = {
        "default": dj_database_url.parse(database_url, conn_max_age=600)
    }
else:
    # Local development: fallback SQLite nếu DATABASE_URL rỗng
    DATABASES = {
        "default": dj_database_url.parse(database_url, conn_max_age=600)
        if database_url
        else dj_database_url.parse(f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600)
    }

# Cấu hình test database tách biệt, cách ly hoàn toàn khỏi CSDL ứng dụng (B00.2 gate)
test_database_url = os.getenv("TEST_DATABASE_URL", "").strip()
if test_database_url:
    DATABASES["default"]["TEST"] = dj_database_url.parse(test_database_url)
else:
    test_db_name = os.getenv("TEST_DATABASE_NAME", "").strip()
    if not test_db_name:
        if database_url and not database_url.startswith("sqlite"):
            test_db_name = "test_postgres"
        else:
            test_db_name = ":memory:"
    DATABASES["default"]["TEST"] = {
        "NAME": test_db_name,
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameModelBackend",
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Django 5.2 STORAGES (thay thế STATICFILES_STORAGE đã bị loại bỏ)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
WHITENOISE_MANIFEST_STRICT = env_bool("WHITENOISE_MANIFEST_STRICT", False)

# Cấu hình bảo mật môi trường Production
if IS_PRODUCTION or not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"