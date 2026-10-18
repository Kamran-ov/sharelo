import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

PROD_ENV = {
    "DEBUG": "0",
    "HTTPS": "1",
    "SECRET_KEY": "k9Xv2mQpL7sR4tYw8ZcB6nHfJd3GaUe5VoIxT1yKrMlPq0WzSbNhCjDgEiAu",
    "ALLOWED_HOSTS": "example.test",
    "DATABASE_URL": "postgres://sharelo:sharelo@localhost:5432/sharelo",
}


def run_python(code: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    # E2E and every inherited flag are dropped: the E2E block neutralises security settings.
    clean = {k: v for k, v in os.environ.items() if k not in {"E2E", "HTTPS", "DEBUG"}}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**clean, "DJANGO_SETTINGS_MODULE": "sharelo.settings", **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


CHECK = (
    "import django;django.setup();"
    "from django.core.management import call_command;"
    "call_command('check', deploy=True, fail_level='WARNING')"
)


def test_check_deploy_has_no_warnings_with_prod_env():
    result = run_python(CHECK, PROD_ENV)
    assert result.returncode == 0, result.stderr
    assert "WARNINGS" not in result.stderr and "identified" not in result.stderr


def test_check_deploy_reports_warnings_without_https():
    result = run_python(CHECK, {**PROD_ENV, "HTTPS": ""})
    assert result.returncode != 0
    for check_id in ("security.W004", "security.W008", "security.W012", "security.W016"):
        assert check_id in result.stderr


@pytest.mark.parametrize(("https", "expected"), [("1", "True True"), ("", "False False")])
def test_cookie_secure_follows_https_flag(https, expected):
    code = (
        "from django.conf import settings;"
        "print(settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)"
    )
    result = run_python(code, {**PROD_ENV, "HTTPS": https})
    assert result.stdout.strip() == expected, result.stderr


def test_no_silenced_checks():
    result = run_python(
        "from django.conf import settings;print(settings.SILENCED_SYSTEM_CHECKS)", PROD_ENV
    )
    assert result.stdout.strip() == "[]"


def test_crontab_runs_run_daily_once_at_0600():
    lines = [
        line
        for line in (ROOT / "deploy" / "crontab").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(lines) == 1
    assert re.fullmatch(r"0 6 \* \* \* .*manage\.py run_daily", lines[0])


def test_compose_prod_declares_expected_services():
    compose = yaml.safe_load((ROOT / "compose.prod.yml").read_text())
    assert {"db", "backend", "cron"} <= set(compose["services"])
    assert compose["services"]["backend"]["environment"]["DEBUG"] in ("0", 0)


def test_cron_runs_only_in_compose():
    for path in [ROOT / "Makefile", *(ROOT / "scripts").iterdir()]:
        assert "supercronic" not in path.read_text(), path
