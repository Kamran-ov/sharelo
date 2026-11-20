# pytest only (backend/pyproject.toml). Never referenced by manage.py, wsgi, compose or E2E.
from .settings import *  # noqa: F403

# PBKDF2 dominates the suite's runtime; the hasher is not what any test is about.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
