from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from importers.banks import staging
from importers.models import PendingBankRow
from ledger.models import ImportBatch

FIXTURES = Path(__file__).parent / "fixtures" / "banks"

pytestmark = pytest.mark.django_db


def csv_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, (FIXTURES / name).read_bytes(), content_type="text/csv")


def post(client, group, name):
    return client.post(
        f"/api/groups/{group.id}/bank-imports/", {"file": csv_file(name)}, format="multipart"
    )


def test_upload_returns_201_with_batch_counts_and_rows(world, api_a):
    res = post(api_a, world.home, "wise_2026_09.csv")
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["ignored"] == 1
    batch = body["batch"]
    assert batch["source"] == "wise"
    assert batch["label"] == "wise_2026_09.csv"
    assert (batch["rows_seen"], batch["rows_created"], batch["rows_skipped"]) == (4, 4, 0)
    first = body["rows"][0]
    assert first == {
        "id": first["id"],
        "date": "2026-09-03",
        "amount_cents": 1820,
        "currency": "EUR",
        "description": "Card transaction of 18.20 EUR issued by Lidl",
        "merchant": "Lidl",
        "external_id": "wise:CARD-1001",
        "status": "pending",
    }
    assert "raw" not in first
    assert PendingBankRow.objects.get(pk=first["id"]).uploaded_by == world.member(
        world.a, world.home
    )


def test_upload_same_file_again_returns_created_0(world, api_a):
    post(api_a, world.home, "revolut_2026_09.csv")
    res = post(api_a, world.home, "revolut_2026_09.csv")
    assert res.status_code == 201
    batch = res.json()["batch"]
    assert (batch["rows_seen"], batch["rows_created"], batch["rows_skipped"]) == (7, 0, 7)
    assert res.json()["rows"] == []
    assert PendingBankRow.objects.count() == 7


def test_unknown_csv_is_400_unknown_bank_format_with_missing_columns(world, api_a):
    res = post(api_a, world.home, "unknown.csv")
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "unknown_bank_format"
    assert "TransferWise ID" in body["detail"]
    assert "Completed Date" in body["detail"]
    assert not ImportBatch.objects.exists()


def test_upload_without_file_is_400(world, api_a):
    res = api_a.post(f"/api/groups/{world.home.id}/bank-imports/", {}, format="multipart")
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_request"


def test_oversized_file_is_400_file_too_large(world, api_a, monkeypatch):
    monkeypatch.setattr(staging, "MAX_BYTES", 100)
    res = post(api_a, world.home, "revolut_2026_09.csv")
    assert res.status_code == 400
    assert res.json()["code"] == "file_too_large"
    assert not PendingBankRow.objects.exists()


def test_non_member_upload_is_404(world, api_c):
    res = post(api_c, world.home, "wise_2026_09.csv")
    assert res.status_code == 404
    assert not PendingBankRow.objects.exists()


def test_batch_get_returns_counts_and_my_rows(world, api_a):
    batch_id = post(api_a, world.home, "wise_2026_09.csv").json()["batch"]["id"]
    res = api_a.get(f"/api/groups/{world.home.id}/bank-imports/{batch_id}/")
    assert res.status_code == 200
    body = res.json()
    assert body["batch"]["rows_created"] == 4
    assert [r["external_id"] for r in body["rows"]] == [
        "wise:CARD-1001",
        "wise:TRANSFER-2001",
        "wise:CARD-1002",
        "wise:CONVERSION-3001",
    ]
    assert "ignored" not in body


def test_batch_of_another_uploader_is_404(world, api_a, api_b):
    batch_id = post(api_a, world.home, "wise_2026_09.csv").json()["batch"]["id"]
    res = api_b.get(f"/api/groups/{world.home.id}/bank-imports/{batch_id}/")
    assert res.status_code == 404


def test_empty_batch_counts_are_visible_to_any_member(world, api_a, api_b):
    post(api_a, world.home, "wise_2026_09.csv")
    empty_id = post(api_a, world.home, "wise_2026_09.csv").json()["batch"]["id"]
    res = api_b.get(f"/api/groups/{world.home.id}/bank-imports/{empty_id}/")
    assert res.status_code == 200
    assert res.json()["rows"] == []
    assert res.json()["batch"]["rows_skipped"] == 4


def test_batch_of_another_group_is_404(world, api_a):
    batch_id = post(api_a, world.rome, "wise_2026_09.csv").json()["batch"]["id"]
    res = api_a.get(f"/api/groups/{world.home.id}/bank-imports/{batch_id}/")
    assert res.status_code == 404


def test_splitwise_batch_is_not_a_bank_import(world, api_a):
    batch = ImportBatch.objects.create(group=world.home, source="splitwise")
    res = api_a.get(f"/api/groups/{world.home.id}/bank-imports/{batch.id}/")
    assert res.status_code == 404
