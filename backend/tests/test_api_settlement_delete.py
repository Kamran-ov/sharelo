import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger.models import Settlement
from ledger.services import balances
from tests.test_api_can_move_to_home import TODAY, owes

pytestmark = pytest.mark.django_db


def settle(client, group, sender, receiver, cents):
    res = client.post(
        f"/api/groups/{group.id}/settlements/",
        {
            "from_member": sender.id,
            "to_member": receiver.id,
            "amount_cents": cents,
            "date": TODAY,
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()["id"]


def home_pair(world):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    return ann, bea


def test_delete_settlement_removes_it_from_balances(world, api_a, api_b):
    ann, bea = home_pair(world)
    owes(api_a, world.home, bea, ann, cents=4210)
    before = balances.net_balances(world.home)
    sid = settle(api_b, world.home, bea, ann, 4210)
    assert set(balances.net_balances(world.home).values()) == {0}
    res = api_b.delete(f"/api/groups/{world.home.id}/settlements/{sid}/")
    assert res.status_code == 204
    assert balances.net_balances(world.home) == before
    assert sum(before.values()) == 0
    assert api_b.get(f"/api/groups/{world.home.id}/settlements/").json() == []


def test_deleted_settlement_stays_in_the_database(world, api_b):
    ann, bea = home_pair(world)
    sid = settle(api_b, world.home, bea, ann, 100)
    api_b.delete(f"/api/groups/{world.home.id}/settlements/{sid}/")
    assert Settlement.objects.count() == 0
    assert Settlement.all_objects.get(pk=sid).deleted_at is not None


def test_delete_settlement_with_twin_is_refused_and_plain_row_succeeds(world, api_a, api_b):
    ann, bea = home_pair(world)
    owes(api_b, world.rome, world.member(world.b, world.rome), world.member(world.a, world.rome))
    nets = balances.net_balances(world.rome)
    owed = -nets[world.member(world.b, world.rome).id]
    res = api_b.post(
        f"/api/groups/{world.rome.id}/move-to-home",
        {"to_profile": world.a.id, "amount_cents": owed, "date": TODAY},
        format="json",
    )
    assert res.status_code == 201, res.content
    trip_row = res.json()[0]["id"]
    refused = api_b.delete(f"/api/groups/{world.rome.id}/settlements/{trip_row}/")
    assert refused.status_code == 400 and refused.json()["code"] == "twin_settlement"
    assert Settlement.objects.count() == 2
    plain = settle(api_b, world.home, bea, ann, 100)
    assert api_b.delete(f"/api/groups/{world.home.id}/settlements/{plain}/").status_code == 204


def test_delete_settlement_of_other_group_is_404_and_member_succeeds(world, api_a, api_b):
    ann, bea = home_pair(world)
    sid = settle(api_b, world.home, bea, ann, 100)
    wrong_group = api_b.delete(f"/api/groups/{world.rome.id}/settlements/{sid}/")
    assert wrong_group.status_code == 404
    assert Settlement.objects.count() == 1
    assert api_a.delete(f"/api/groups/{world.home.id}/settlements/{sid}/").status_code == 204


def test_delete_settlement_by_non_member_is_404(world, api_b, api_c):
    ann, bea = home_pair(world)
    sid = settle(api_b, world.home, bea, ann, 100)
    assert api_c.delete(f"/api/groups/{world.home.id}/settlements/{sid}/").status_code == 404
    assert Settlement.objects.count() == 1


def test_settlement_list_reports_twin_group_name_and_home_side(world, api_b):
    owes(api_b, world.rome, world.member(world.b, world.rome), world.member(world.a, world.rome))
    owed = -balances.net_balances(world.rome)[world.member(world.b, world.rome).id]
    api_b.post(
        f"/api/groups/{world.rome.id}/move-to-home",
        {"to_profile": world.a.id, "amount_cents": owed, "date": TODAY},
        format="json",
    )
    trip = api_b.get(f"/api/groups/{world.rome.id}/settlements/").json()
    home = api_b.get(f"/api/groups/{world.home.id}/settlements/").json()
    assert [(r["twin_group_name"], r["is_home_side"]) for r in trip] == [("Home", False)]
    assert [(r["twin_group_name"], r["is_home_side"]) for r in home] == [("Rome", True)]
    ann, bea = home_pair(world)
    settle(api_b, world.home, bea, ann, 100)
    plain = api_b.get(f"/api/groups/{world.home.id}/settlements/").json()
    assert [(r["twin_group_name"], r["is_home_side"]) for r in plain if r["twin"] is None] == [
        (None, False)
    ]


def test_settlement_list_query_count_is_constant(world, api_b):
    ann, bea = home_pair(world)
    url = f"/api/groups/{world.home.id}/settlements/"
    settle(api_b, world.home, bea, ann, 100)
    with CaptureQueriesContext(connection) as one:
        api_b.get(url)
    for cents in (200, 300, 400):
        settle(api_b, world.home, bea, ann, cents)
    with CaptureQueriesContext(connection) as many:
        assert len(api_b.get(url).json()) == 4
    assert len(many) == len(one)
