import os
from pathlib import Path

from .dburl import parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Compose default; the cloud session and the Makefile export a localhost URL instead.
DEFAULT_DATABASE_URL = "postgres://sharelo:sharelo@db:5432/sharelo"


def required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is missing or empty; see .env.example")
    return value


SECRET_KEY = required_env("SECRET_KEY")
DEBUG = os.environ.get("DEBUG", "") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# Browser tests run the real server on plain http against a throwaway `*_e2e` database.
E2E = os.environ.get("E2E") == "1"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "accounts",
    "ledger",
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

ROOT_URLCONF = "sharelo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "sharelo.wsgi.application"
ASGI_APPLICATION = "sharelo.asgi.application"

DATABASES = {"default": parse_database_url(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))}
if os.environ.get("TEST_DATABASE_NAME"):
    DATABASES["default"]["TEST"] = {"NAME": os.environ["TEST_DATABASE_NAME"]}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The built SPA (sw.js, manifest, icons, assets) is served from the site root by whitenoise;
# index.html itself goes through SpaIndexView so deep links work. A missing dir only warns.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST") or BASE_DIR / "frontend_dist")
WHITENOISE_ROOT = FRONTEND_DIST

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min"},
    # 0 = ignore X-Forwarded-For, so a client cannot mint a fresh throttle bucket per request.
    "NUM_PROXIES": 0,
    "EXCEPTION_HANDLER": "accounts.api.errors.handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "sharelo",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{n}"}
    for n in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
CSRF_FAILURE_VIEW = "accounts.api.errors.csrf_failure"
# HTTPS=1: served over https behind a proxy or tunnel. Plain http on localhost must still sign in.
HTTPS = os.environ.get("HTTPS", "") == "1"
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

if E2E:
    from .e2e import check_e2e_settings

    check_e2e_settings(DATABASES["default"]["NAME"], os.environ.get("ALLOWED_HOSTS"))
    DEBUG = False
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
    # Every `not DEBUG`-derived security setting is neutralised here: plain http, no redirects.
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_PROXY_SSL_HEADER = None
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"auth": "100000/min"}

# Optional by design: empty disables Google sign-in rather than refusing to boot.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
