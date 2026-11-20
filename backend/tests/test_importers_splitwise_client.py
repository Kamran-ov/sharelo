import json
import urllib.parse
from pathlib import Path

import pytest

from importers.splitwise import client as client_module
from importers.splitwise.client import PAGE_SIZE, SplitwiseClient
from ledger.errors import LedgerError

IMPORTERS = Path(__file__).resolve().parent.parent / "importers"


class Recorder:
    def __init__(self, pages: list[list[dict]]):
        self.pages = pages
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        offset = int(query["offset"][0])
        return json.dumps({"expenses": self.pages[offset // PAGE_SIZE]})


def offsets(recorder: Recorder) -> list[int]:
    return [
        int(urllib.parse.parse_qs(urllib.parse.urlparse(r.full_url).query)["offset"][0])
        for r in recorder.requests
    ]


def test_expenses_are_paged_until_a_short_page(monkeypatch):
    rec = Recorder([[{"id": i} for i in range(PAGE_SIZE)], [{"id": PAGE_SIZE}]])
    monkeypatch.setattr(client_module, "_open", rec)
    rows = SplitwiseClient("k").get_expenses(555)
    assert len(rows) == PAGE_SIZE + 1
    assert offsets(rec) == [0, PAGE_SIZE]
    assert "group_id=555" in rec.requests[0].full_url
    assert f"limit={PAGE_SIZE}" in rec.requests[0].full_url


def test_exact_multiple_of_page_size_stops_on_empty_page(monkeypatch):
    rec = Recorder([[{"id": i} for i in range(PAGE_SIZE)], []])
    monkeypatch.setattr(client_module, "_open", rec)
    assert len(SplitwiseClient("k").get_expenses(555)) == PAGE_SIZE
    assert offsets(rec) == [0, PAGE_SIZE]


def test_api_key_is_sent_as_bearer(monkeypatch):
    seen = []

    def fake_open(request):
        seen.append(request)
        return json.dumps({"user": {"id": 1}})

    monkeypatch.setattr(client_module, "_open", fake_open)
    monkeypatch.setenv("SPLITWISE_API_KEY", "secret-key")
    SplitwiseClient.from_env().get_current_user()
    assert seen[0].get_header("Authorization") == "Bearer secret-key"
    assert seen[0].full_url == "https://secure.splitwise.com/api/v3.0/get_current_user"


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_api_key_is_refused(monkeypatch, value):
    monkeypatch.setenv("SPLITWISE_API_KEY", value)
    with pytest.raises(LedgerError) as err:
        SplitwiseClient.from_env()
    assert err.value.code == "missing_api_key"


def test_json_numbers_never_become_float(monkeypatch):
    body = '{"expenses": [{"id": 1, "cost": 12.5, "rate": 0.1}]}'
    monkeypatch.setattr(client_module, "_open", lambda request: body)
    row = SplitwiseClient("k").get_expenses(555)[0]
    assert row["cost"] == "12.5" and isinstance(row["cost"], str)
    assert row["rate"] == "0.1"


def test_importers_package_has_no_float_or_round():
    for path in IMPORTERS.rglob("*.py"):
        text = path.read_text()
        for banned in ("float(", "round("):
            assert banned not in text, f"{banned} in {path}"
