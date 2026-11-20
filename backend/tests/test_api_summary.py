import pytest

from ledger.models import Member
from ledger.services import groups

pytestmark = pytest.mark.django_db


def test_summary_transfer_direction_is_debtor_to_creditor(world, api_a):
    """Hard-coded, not compared with simplify_debts: a flip anywhere on the way would pass that."""
    cyd = groups.join_group_by_token(world.rome.share_token, "Cyd", world.c)
    ann, bea = world.member(world.a, world.rome), world.member(world.b, world.rome)
    Member.objects.filter(pk=world.gus.pk).delete()
    res = api_a.post(
        f"/api/groups/{world.rome.id}/expenses/",
        world.expense_body(world.rome, world.a, amount_cents=9000, preset="equal"),
        format="json",
    )
    assert res.status_code == 201, res.content
    body = api_a.get(f"/api/groups/{world.rome.id}/summary/").json()
    assert body["transfers"] == [
        {"from_member": bea.id, "to_member": ann.id, "amount_cents": 3000},
        {"from_member": cyd.id, "to_member": ann.id, "amount_cents": 3000},
    ]
    nets = {r["member_id"]: r["net"] for r in body["per_member"]}
    assert all(nets[t["from_member"]] < 0 < nets[t["to_member"]] for t in body["transfers"])
    assert body["group"] == {"id": world.rome.id, "name": "Rome"}
    assert body["currency"] == "EUR"
    assert body["total_spent_cents"] == 9000
    assert body["recent_expenses"][0]["paid_by"] == [ann.id]
    assert body["recent_expenses"][0]["date"] == "2026-10-01"


def test_summary_outsider_gets_404(world, api_c):
    res = api_c.get(f"/api/groups/{world.home.id}/summary/")
    assert res.status_code == 404


def test_summary_member_gets_200(world, api_b):
    res = api_b.get(f"/api/groups/{world.home.id}/summary/")
    assert res.status_code == 200
    assert res.json()["total_spent_cents"] == 0


def test_summary_guest_session_gets_200(world):
    res = world.guest_client().get(f"/api/groups/{world.rome.id}/summary/")
    assert res.status_code == 200
    assert [r["display_name"] for r in res.json()["per_member"]] == ["Ann", "Bea", "Gus"]
