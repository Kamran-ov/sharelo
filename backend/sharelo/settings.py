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

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "ledger",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
