from urllib.parse import unquote, urlparse

ALLOWED_SCHEMES = {"postgres", "postgresql"}


def parse_database_url(url: str) -> dict:
    """Parse a Postgres URL into a Django DATABASES entry; anything else is refused, never
    silently replaced, so a typo cannot turn into a SQLite database."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"DATABASE_URL must be a postgres:// URL, got scheme {parsed.scheme!r}")
    name = parsed.path.lstrip("/")
    if not name or not parsed.hostname:
        raise ValueError("DATABASE_URL needs a host and a database name")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(name),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
    }
