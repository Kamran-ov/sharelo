import datetime

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from ledger.models import Expense, RecurringRule
from ledger.services import balances, expenses, recurring

pytestmark = pytest.mark.django_db

OK_STATUSES = {200, 201, 204}

# (path template, method) -> body factory, and the status a guest of Rome gets by design.
# Templates use {g} group, {e} expense, {r} rule, {s} settlement.
ROUTES = [
    ("groups/{g}/", "GET", None, 200),
    ("groups/{g}/link", "POST", lambda w: {"active": False}, 401),
    ("groups/{g}/category-defaults/", "GET", None, 200),
    ("groups/{g}/category-defaults/", "PUT", lambda w: {}, 200),
    ("groups/{g}/expenses/", "GET", None, 200),
    ("groups/{g}/expenses/", "POST", lambda w: {}, 400),
    ("groups/{g}/expenses/{e}/", "PATCH", lambda w: {"description": "x"}, 200),
    ("groups/{g}/expenses/{e}/", "DELETE", None, 204),
    ("groups/{g}/rate/", "GET", None, 400),
    ("groups/{g}/balances/", "GET", None, 200),
    ("groups/{g}/settlements/", "GET", None, 200),
    ("groups/{g}/settlements/", "POST", lambda w: {}, 400),
    ("groups/{g}/settlements/{s}/", "DELETE", None, 204),
    ("groups/{g}/move-to-home", "POST", lambda w: {}, 401),
    ("groups/{g}/recurring/", "GET", None, 200),
    ("groups/{g}/recurring/", "POST", lambda w: {}, 400),
    ("groups/{g}/recurring/{r}/", "PATCH", lambda w: {"description": "x"}, 200),
    ("groups/{g}/recurring/{r}/", "DELETE", None, 204),
    ("groups/{g}/recurring/{r}/pause", "POST", None, 200),
    ("groups/{g}/recurring/{r}/resume", "POST", None, 200),
    ("groups/{g}/recurring/{r}/skip", "POST", None, 200),
]
ROW_IDS = [f"{m} {t}" for t, m, _, _ in ROUTES]


@pytest.fixture
def rome_ids(world):
    rome = world.rome
    a_rome, b_rome = world.member(world.a, rome), world.member(world.b, rome)
    expense = expenses.create_expense(
        rome,
        description="Taxi",
        amount_cents=1000,
        currency="EUR",
        date=datetime.date(2026, 10, 1),
        category=world.groceries,
        payers={a_rome.id: 1000},
        splits={a_rome.id: 500, b_rome.id: 500},
        split_type="equal",
    )
    rule = recurring.create_rule(
        rome,
        description="Rent",
        amount_cents=1000,
        payer=a_rome,
        split_type="equal",
        split_params={},
        category=world.groceries,
        frequency="monthly",
        day_of_month=1,
        start_date=datetime.date(2026, 10, 1),
    )
    settlement = balances.record_settlement(rome, b_rome, a_rome, 100, datetime.date(2026, 10, 2))
    return {"g": rome.id, "e": expense.id, "r": rule.id, "s": settlement.id}


def call(client, ids, template, method, body):
    path = "/api/" + template.format(**ids)
    return getattr(client, method.lower())(path, body, format="json")


@pytest.mark.parametrize(("template", "method", "body", "guest_status"), ROUTES, ids=ROW_IDS)
def test_every_group_route_is_404_for_outsider_and_open_to_guest_member(
    world, api_c, rome_ids, template, method, body, guest_status
):
    payload = body(world) if body else None
    missing = {**rome_ids, "g": 999999}
    gone = call(api_c, missing, template, method, payload)
    assert gone.status_code == 404

    outsider = call(api_c, rome_ids, template, method, payload)
    assert outsider.status_code == 404
    assert outsider.content == gone.content  # no existence leak, byte for byte

    anonymous = call(APIClient(), rome_ids, template, method, payload)
    assert anonymous.status_code == 404

    guest = call(world.guest_client(), rome_ids, template, method, payload)
    assert guest.status_code == guest_status, guest.content


def _routes(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _routes(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route, p.callback


def test_route_table_covers_every_group_url():
    covered = {(t, m) for t, m, _, _ in ROUTES}
    seen = set()
    for route, callback in _routes(get_resolver().url_patterns):
        if not route.startswith("api/groups/<int:group_id>/"):
            continue
        template = (
            route.removeprefix("api/")
            .replace("<int:group_id>", "{g}")
            .replace("<int:eid>", "{e}")
            .replace("<int:rid>", "{r}")
            .replace("<int:sid>", "{s}")
        )
        for method in ("get", "post", "put", "patch", "delete"):
            if hasattr(callback.cls, method):
                seen.add((template, method.upper()))
    assert seen - covered == set(), "routes missing from ROUTES"
    assert covered - seen == set(), "ROUTES rows with no route"


def test_member_of_group_a_cannot_touch_group_b_expense_by_id(world, api_a, rome_ids):
    other = expenses.create_expense(
        world.home,
        description="Rent",
        amount_cents=100,
        currency="EUR",
        date=datetime.date(2026, 10, 1),
        category=world.groceries,
        payers={world.member(world.a, world.home).id: 100},
        splits={world.member(world.a, world.home).id: 100},
        split_type="personal",
    )
    url = f"/api/groups/{rome_ids['g']}/expenses/{other.id}/"
    assert api_a.patch(url, {"description": "x"}, format="json").status_code == 404
    assert api_a.delete(url).status_code == 404
    assert Expense.objects.get(pk=other.pk).description == "Rent"
    own = f"/api/groups/{rome_ids['g']}/expenses/{rome_ids['e']}/"
    assert api_a.patch(own, {"description": "x"}, format="json").status_code == 200


def test_rule_of_another_group_is_404_for_a_member(world, api_a, rome_ids):
    a_home = world.member(world.a, world.home)
    foreign = RecurringRule.objects.get(pk=rome_ids["r"])
    assert foreign.group_id == world.rome.id
    url = f"/api/groups/{world.home.id}/recurring/{rome_ids['r']}/"
    assert api_a.patch(url, {"description": "x"}, format="json").status_code == 404
    assert a_home.group_id == world.home.id


def test_guest_of_rome_gets_404_on_home(world):
    guest = world.guest_client()
    assert guest.get(f"/api/groups/{world.home.id}/").status_code == 404
    assert guest.get(f"/api/groups/{world.rome.id}/").status_code == 200
