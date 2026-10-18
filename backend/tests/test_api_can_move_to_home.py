import pytest

from ledger.models import Category
from ledger.services import groups

pytestmark = pytest.mark.django_db

TODAY = "2026-10-05"


def owes(client, group, debtor, creditor, cents=3000):
    res = client.post(
        f"/api/groups/{group.id}/expenses/",
        {
            "description": "Dinner",
            "amount_cents": cents,
            "date": TODAY,
            "category": Category.objects.get(name="Groceries").id,
            "payer_member": creditor.id,
            "preset": "full_for_other",
            "params": {"other_id": debtor.id},
        },
        format="json",
    )
    assert res.status_code == 201, res.content


def transfers(client, group):
    return client.get(f"/api/groups/{group.id}/balances/").json()["transfers"]


def case_main_group(world):
    owes(
        world.login(world.a),
        world.home,
        world.member(world.b, world.home),
        world.member(world.a, world.home),
    )
    return world.b, world.home


def case_creditor_is_guest(world):
    owes(world.login(world.b), world.rome, world.member(world.b, world.rome), world.gus)
    return world.b, world.rome


def case_main_groups_differ(world):
    groups.create_group(world.c, "Cyd home", "EUR", as_main=True)
    groups.join_group_by_token(world.rome.share_token, "Cyd", world.c)
    owes(
        world.login(world.b),
        world.rome,
        world.member(world.b, world.rome),
        world.member(world.c, world.rome),
    )
    return world.b, world.rome


def case_currencies_differ(world):
    usd = groups.create_group(world.a, "USD trip", "USD")
    groups.join_group_by_token(usd.share_token, "Bea", world.b)
    owes(world.login(world.a), usd, world.member(world.b, usd), world.member(world.a, usd))
    return world.b, usd


def case_viewer_is_the_creditor(world):
    owes(
        world.login(world.a),
        world.rome,
        world.member(world.b, world.rome),
        world.member(world.a, world.rome),
    )
    return world.a, world.rome


def case_sub_group_with_two_profiles(world):
    owes(
        world.login(world.a),
        world.rome,
        world.member(world.b, world.rome),
        world.member(world.a, world.rome),
    )
    return world.b, world.rome


@pytest.mark.parametrize(
    "case, expected",
    [
        (case_main_group, False),
        (case_creditor_is_guest, False),
        (case_main_groups_differ, False),
        (case_viewer_is_the_creditor, False),
        (case_sub_group_with_two_profiles, True),
    ],
)
def test_can_move_to_home_is_true_only_for_two_profiles_sharing_a_main_group(world, case, expected):
    viewer, group = case(world)
    rows = transfers(world.login(viewer), group)
    assert rows, "the case must produce a transfer"
    assert any(r["can_move_to_home"] for r in rows) is expected


def test_can_move_to_home_is_false_when_currencies_differ(world):
    viewer, group = case_currencies_differ(world)
    assert [r["can_move_to_home"] for r in transfers(world.login(viewer), group)] == [False]


def test_can_move_to_home_is_false_for_guest_session(world):
    owes(world.login(world.b), world.rome, world.gus, world.member(world.b, world.rome))
    rows = transfers(world.guest_client(), world.rome)
    assert rows and not any(r["can_move_to_home"] for r in rows)


def test_transfer_carries_to_profile_for_creditor_with_profile_and_null_for_guest(world):
    client = world.login(world.b)
    owes(client, world.rome, world.member(world.b, world.rome), world.member(world.a, world.rome))
    owes(client, world.rome, world.member(world.b, world.rome), world.gus, cents=1000)
    by_target = {r["to_member"]: r["to_profile"] for r in transfers(client, world.rome)}
    assert by_target == {world.member(world.a, world.rome).id: world.a.id, world.gus.id: None}


def test_balances_query_count_is_constant_with_can_move_to_home(world):
    client = world.login(world.b)
    b = world.member(world.b, world.rome)
    owes(client, world.rome, b, world.member(world.a, world.rome))
    url = f"/api/groups/{world.rome.id}/balances/"
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as one:
        assert len(client.get(url).json()["transfers"]) == 1
    owes(client, world.rome, b, world.gus, cents=1000)
    with CaptureQueriesContext(connection) as two:
        assert len(client.get(url).json()["transfers"]) == 2
    assert len(two) == len(one)
