import io
from pathlib import Path

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db

COMMITTED = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "schema.json"


def test_schema_generates_with_no_warnings(tmp_path):
    out = tmp_path / "schema.json"
    call_command(
        "spectacular",
        "--format",
        "openapi-json",
        "--file",
        str(out),
        "--validate",
        "--fail-on-warn",
        stderr=io.StringIO(),
    )
    assert out.stat().st_size > 0


def test_committed_schema_equals_generated(tmp_path):
    out = tmp_path / "schema.json"
    call_command(
        "spectacular", "--format", "openapi-json", "--file", str(out), stderr=io.StringIO()
    )
    assert COMMITTED.read_text() == out.read_text(), "run `make schema` and commit the result"


def test_schema_and_docs_pages_are_served(client):
    schema = client.get("/api/schema/")
    assert schema.status_code == 200
    assert client.get("/api/docs/").status_code == 200
