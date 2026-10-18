"""Guards for E2E mode, kept pure so tests can call them without re-importing settings."""

from django.core.exceptions import ImproperlyConfigured

E2E_HOSTS = {"localhost", "127.0.0.1"}
E2E_DB_SUFFIX = "_e2e"


def is_e2e_database(name: str) -> bool:
    return name.endswith(E2E_DB_SUFFIX)


def check_e2e_settings(database_name: str, allowed_hosts_env: str | None) -> None:
    """E2E=1 must never serve a dev database or a deployed host name."""
    if not is_e2e_database(database_name):
        raise ImproperlyConfigured(
            f"E2E=1 needs a database whose name ends in {E2E_DB_SUFFIX!r}, got {database_name!r}"
        )
    hosts = {h for h in (allowed_hosts_env or "").split(",") if h}
    if hosts - E2E_HOSTS:
        raise ImproperlyConfigured(f"E2E=1 allows only {sorted(E2E_HOSTS)}, got {sorted(hosts)}")
