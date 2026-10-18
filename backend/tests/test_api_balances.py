import datetime

import pytest

from ledger.models import Settlement
from ledger.services import balances

pytestmark = pytest.mark.django_db

TODAY = "2026-10-05"


def add_expense(client, world, group, payer, amount, **over):
    res = client.post(
        f"/api/groups/{group.id}/expenses/",
        world.expense_body(group, payer, amount_cents=amount, **over),
        format="json",
    )
    assert res.status_code == 201, res.content
    return res


def test_balances_match_services_on_fixture(world, api_a):
    add_expense(api_a, world, world.home, world.a, 1001)
    add_expense(api_a, world, world.home, world.b, 3000, preset="personal")
    body = api_a.get(f"/api/groups/{world.home.id}/balances/").json()
    nets = balances.net_balances(world.home)
    assert body["nets"] == {str(m): c for m, c in nets.items()}
    assert [(t["from_member"], t["to_member"], t["amount_cents"]) for t in body["transfers"]] == (
        balances.simplify_debts(nets)
    )
    assert sum(body["nets"].values()) == 0
    for row in body["members"]:
        member = world.home.members.get(pk=row["member_id"])
        assert {k: row[k] for k in ("paid", "owed_share", "net")} == balances.member_summary(
            world.home, member
        )
    assert body["currency"] == "EUR"


def test_two_half_expenses_give_the_production_numbers(world, api_a):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    first = add_expense(api_a, world, world.home, world.a, 1000)
    second = add_expense(api_a, world, world.home, world.a, 1001)
    assert sorted(s["owed_cents"] for s in first.json()["splits"]) == [500, 500]
    assert {s["member"]: s["owed_cents"] for s in second.json()["splits"]} == {
        ann.id: 501,
        bea.id: 500,
    }
    body = api_a.get(f"/api/groups/{world.home.id}/balances/").json()
    assert body["nets"] == {str(ann.id): 1000, str(bea.id): -1000}
    assert body["transfers"] == [
        {
            "from_member": bea.id,
            "to_member": ann.id,
            "amount_cents": 1000,
            "can_move_to_home": False,  # Home is the main group
            "to_profile": world.a.id,
        }
    ]


def test_settlement_of_full_transfer_zeroes_nets_in_next_get(world, api_a, api_b):
    add_expense(api_a, world, world.home, world.a, 4000)
    url = f"/api/groups/{world.home.id}/balances/"
    transfer = api_b.get(url).json()["transfers"][0]
    assert transfer["amount_cents"] == 2000
    res = api_b.post(
        f"/api/groups/{world.home.id}/settlements/",
        {
            "from_member": transfer["from_member"],
            "to_member": transfer["to_member"],
            "amount_cents": transfer["amount_cents"],
            "date": TODAY,
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    after = api_b.get(url).json()
    assert set(after["nets"].values()) == {0} and after["transfers"] == []
    listed = api_b.get(f"/api/groups/{world.home.id}/settlements/").json()
    assert [r["amount_cents"] for r in listed] == [2000]


def test_settlement_in_the_wrong_direction_leaves_nets_nonzero(world, api_a, api_b):
    add_expense(api_a, world, world.home, world.a, 4000)
    transfer = api_b.get(f"/api/groups/{world.home.id}/balances/").json()["transfers"][0]
    api_b.post(
        f"/api/groups/{world.home.id}/settlements/",
        {
            "from_member": transfer["to_member"],
            "to_member": transfer["from_member"],
            "amount_cents": 2000,
            "date": TODAY,
        },
        format="json",
    )
    nets = api_b.get(f"/api/groups/{world.home.id}/balances/").json()["nets"]
    assert sorted(nets.values()) == [-4000, 4000]


def test_settlement_with_member_of_other_group_refused(world, api_a):
    ann = world.member(world.a, world.home)
    foreign = world.member(world.b, world.rome)
    body = {"from_member": ann.id, "to_member": foreign.id, "amount_cents": 100, "date": TODAY}
    res = api_a.post(f"/api/groups/{world.home.id}/settlements/", body, format="json")
    assert res.status_code == 400 and res.json()["code"] == "member_not_in_group"
    body["to_member"] = 999999
    res = api_a.post(f"/api/groups/{world.home.id}/settlements/", body, format="json")
    assert res.json()["code"] == "member_not_in_group"
    assert Settlement.objects.count() == 0
    body["to_member"] = world.member(world.b, world.home).id
    assert (
        api_a.post(f"/api/groups/{world.home.id}/settlements/", body, format="json").status_code
        == 201
    )


def test_settlement_list_newest_first(world, api_a):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    for day in ("2026-10-01", "2026-10-03", "2026-10-02"):
        api_a.post(
            f"/api/groups/{world.home.id}/settlements/",
            {"from_member": bea.id, "to_member": ann.id, "amount_cents": 100, "date": day},
            format="json",
        )
    rows = api_a.get(f"/api/groups/{world.home.id}/settlements/").json()
    assert [r["date"] for r in rows] == ["2026-10-03", "2026-10-02", "2026-10-01"]


def owe_in_rome(client, world):
    add_expense(client, world, world.rome, world.b, 5000, preset="equal")


def test_move_to_home_from_main_group_is_400_not_a_sub_group(world, api_a):
    add_expense(api_a, world, world.home, world.b, 5000)
    body = {"to_profile": world.b.id, "amount_cents": 100, "date": TODAY}
    res = api_a.post(f"/api/groups/{world.home.id}/move-to-home", body, format="json")
    assert res.status_code == 400 and res.json()["code"] == "not_a_sub_group"
    assert Settlement.objects.count() == 0


def test_move_to_home_from_trip_creates_two_twin_settlements(world, api_a):
    owe_in_rome(api_a, world)
    nets = balances.net_balances(world.rome)
    a_rome = world.member(world.a, world.rome)
    assert nets[a_rome.id] < 0
    owed = -nets[a_rome.id]
    body = {"to_profile": world.b.id, "amount_cents": owed, "date": TODAY}
    res = api_a.post(f"/api/groups/{world.rome.id}/move-to-home", body, format="json")
    assert res.status_code == 201, res.content
    rows = res.json()
    assert len(rows) == 2 and Settlement.objects.count() == 2
    trip_row, home_row = (
        Settlement.objects.get(pk=rows[0]["id"]),
        Settlement.objects.get(pk=rows[1]["id"]),
    )
    assert trip_row.twin_id == home_row.pk and home_row.twin_id == trip_row.pk
    assert {trip_row.group_id, home_row.group_id} == {world.rome.id, world.home.id}
    assert balances.net_balances(world.rome)[a_rome.id] == nets[a_rome.id] + owed


def test_move_to_home_exceeds_debt_is_400(world, api_a):
    owe_in_rome(api_a, world)
    body = {"to_profile": world.b.id, "amount_cents": 10**6, "date": TODAY}
    res = api_a.post(f"/api/groups/{world.rome.id}/move-to-home", body, format="json")
    assert res.status_code == 400 and res.json()["code"] == "exceeds_debt"
    body["to_profile"] = 999999
    assert (
        api_a.post(f"/api/groups/{world.rome.id}/move-to-home", body, format="json").json()["code"]
        == "unknown_profile"
    )


def test_move_to_home_by_guest_is_401(world):
    body = {"to_profile": world.b.id, "amount_cents": 100, "date": TODAY}
    res = world.guest_client().post(
        f"/api/groups/{world.rome.id}/move-to-home", body, format="json"
    )
    assert res.status_code == 401 and res.json()["code"] == "not_authenticated"
    assert datetime.date.fromisoformat(TODAY)
