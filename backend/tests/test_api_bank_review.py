from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from importers.banks import shop_rules, staging
from importers.models import PendingBankRow, ShopRule
from ledger.models import Category, CategoryDefault, Expense

FIXTURES = Path(__file__).parent / "fixtures" / "banks"

pytestmark = pytest.mark.django_db


def stage(world, profile, name="revolut_review.csv"):
    member = world.member(profile, world.home)
    data = (FIXTURES / name).read_bytes()
    batch = staging.stage_bank_file(world.home, member, SimpleUploadedFile(name, data)).batch
    return {r.description: r for r in batch.bank_rows.all()}


def url(world, tail):
    return f"/api/groups/{world.home.id}/{tail}"


def test_pending_rows_list_has_suggestions_and_only_mine(world, api_a):
    mine = stage(world, world.a)
    stage(world, world.b, "revolut_review_next.csv")
    res = api_a.get(url(world, "bank-rows/"))
    assert res.status_code == 200, res.content
    body = res.json()
    assert [r["id"] for r in body["rows"]] == [
        mine[d].id for d in ("Esselunga", "Farmacia Centrale", "Transfer to Bea")
    ]
    general = Category.objects.get(name="General", parent__name="Uncategorized")
    assert body["rows"][0]["suggestion"] == {
        "category": general.id,
        "category_name": "General",
        "decision": "shared",
        "preset": "equal",
        "params": {},
        "basis": "default",
        "rule": None,
    }
    leaves = Category.objects.filter(children__isnull=True).count()
    assert len(body["category_splits"]) == leaves
    assert body["category_splits"][str(general.id)] == {"preset": "equal", "params": {}}


def test_resolve_shared_half_via_api_returns_expense(world, api_a):
    row = stage(world, world.a)["Esselunga"]
    res = api_a.post(
        url(world, f"bank-rows/{row.id}/resolve"),
        {
            "decision": "shared",
            "category": world.groceries.id,
            "preset": "half",
            "params": {},
            "remember": True,
        },
        format="json",
    )
    assert res.status_code == 200, res.content
    body = res.json()
    expense = Expense.objects.get(pk=body["expense"])
    assert expense.split_type == "equal"
    assert sorted(s.owed_cents for s in expense.splits.all()) == [2260, 2260]
    assert body["row"]["status"] == "shared"
    assert ShopRule.objects.get(pk=body["rule"]).match_text == "Esselunga"


def test_resolve_twice_is_400_row_already_resolved(world, api_a):
    row = stage(world, world.a)["Transfer to Bea"]
    path = url(world, f"bank-rows/{row.id}/resolve")
    assert api_a.post(path, {"decision": "skip"}, format="json").status_code == 200
    res = api_a.post(path, {"decision": "personal"}, format="json")
    assert res.status_code == 400
    assert res.json()["code"] == "row_already_resolved"
    assert not Expense.all_objects.exists()


def test_changed_category_creates_the_split_the_list_showed(world, api_a):
    alice, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    dining = Category.objects.get(name="Dining out")
    shop_rules.save_rule(
        world.home, alice, match_text="Esselunga", category=world.groceries, preset="equal"
    )
    CategoryDefault.objects.create(
        group=world.home,
        category=dining,
        split_type="percentage",
        split_params={"basis_points": {str(alice.id): 7000, str(bea.id): 3000}},
    )
    row = stage(world, world.a)["Esselunga"]
    listing = api_a.get(url(world, "bank-rows/")).json()
    shown = listing["category_splits"][str(dining.id)]
    assert shown["preset"] == "percentage"
    res = api_a.post(
        url(world, f"bank-rows/{row.id}/resolve"),
        {"decision": "shared", "category": dining.id, **shown},
        format="json",
    )
    assert res.status_code == 200, res.content
    expense = Expense.objects.get(pk=res.json()["expense"])
    assert expense.split_type == shown["preset"]
    assert {s.member_id: s.owed_cents for s in expense.splits.all()} == {
        alice.id: 3164,
        bea.id: 1356,
    }


def test_undo_via_api_returns_row_pending(world, api_a):
    row = stage(world, world.a)["Esselunga"]
    api_a.post(url(world, f"bank-rows/{row.id}/resolve"), {"decision": "shared"}, format="json")
    res = api_a.post(url(world, f"bank-rows/{row.id}/undo"))
    assert res.status_code == 200, res.content
    assert res.json()["status"] == "pending"
    assert not Expense.objects.exists()
    assert PendingBankRow.objects.get(pk=row.id).status == "pending"


def test_other_uploaders_row_is_404(world, api_b):
    row = stage(world, world.a)["Esselunga"]
    res = api_b.post(url(world, f"bank-rows/{row.id}/resolve"), {"decision": "skip"}, format="json")
    assert res.status_code == 404
    assert api_b.get(url(world, "bank-rows/")).json()["rows"] == []


def test_shop_rules_crud(world, api_a, api_b):
    res = api_a.post(
        url(world, "shop-rules/"),
        {"match_text": "  Esselunga ", "category": world.groceries.id, "preset": "half"},
        format="json",
    )
    assert res.status_code == 201, res.content
    rule = res.json()
    assert (rule["match_text"], rule["preset"], rule["category_name"]) == (
        "Esselunga",
        "equal",
        "Groceries",
    )
    # Rules are group data: another member sees and edits them.
    listed = api_b.get(url(world, "shop-rules/")).json()
    assert [r["id"] for r in listed] == [rule["id"]]
    patched = api_b.patch(
        url(world, f"shop-rules/{rule['id']}/"), {"match_text": "Esselunga Milano"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["match_text"] == "Esselunga Milano"
    assert api_a.delete(url(world, f"shop-rules/{rule['id']}/")).status_code == 204
    assert api_a.get(url(world, "shop-rules/")).json() == []
    assert ShopRule.all_objects.filter(pk=rule["id"], deleted_at__isnull=False).exists()


def test_shop_rule_duplicate_text_is_400(world, api_a):
    body = {"match_text": "Esselunga", "category": world.groceries.id, "preset": "equal"}
    assert api_a.post(url(world, "shop-rules/"), body, format="json").status_code == 201
    res = api_a.post(url(world, "shop-rules/"), {**body, "match_text": "ESSELUNGA"}, format="json")
    assert res.status_code == 400
    assert res.json()["code"] == "duplicate_rule"
    assert ShopRule.objects.count() == 1
