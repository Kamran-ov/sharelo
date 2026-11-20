import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.services.auth import register
from ledger.models import Category, ExchangeRate, Member
from ledger.services import analytics, groups, home
from ledger.services.expenses import create_expense_from_preset, delete_expense

pytestmark = pytest.mark.django_db

D = datetime.date
RANGE = {"from": "2026-10-01", "to": "2026-11-30"}
FROM, TO = D(2026, 10, 1), D(2026, 11, 30)
PW = "correct-horse-battery-9"


def cat(parent: str, name: str) -> Category:
    return Category.objects.get(parent__name=parent, name=name)


def spend(group, payer, cents, category, day, members=None, preset="equal"):
    return create_expense_from_preset(
        group,
        preset=preset,
        payer_id=payer.id,
        member_ids=[m.id for m in members] if members else None,
        description="x",
        amount_cents=cents,
        currency=group.currency,
        date=day,
        category=category,
    )


def login(profile) -> APIClient:
    client = APIClient()
    client.force_login(profile.user)
    return client


def guest_client(member: Member) -> APIClient:
    client = APIClient()
    session = client.session
    session["guest_member_ids"] = [member.id]
    session.save()
    return client


class World:
    """Home EUR: Ann, Bea (profiles), Gus (guest). Rome USD trip: Ann, Bea, Tim (guest).

    In 2026-10-01..2026-11-30, by hand (owed shares, EUR):
      Home   Ann 1000 groceries + 3000 dining = 4000; Bea 1000 + 3000 + 1500 personal taxi = 5500;
             Gus 1000 groceries (guest).
      Rome   90.00 USD dining split 3 ways = 30.00 USD each = 25.00 EUR at 1.2 USD/EUR;
             Tim's 25.00 is a guest share.
      Rome on 2026-12-01 (outside the range): 6.00 USD taxi split Ann/Bea = 2.50 EUR each.
    """

    def __init__(self):
        self.groceries = cat("Food and drink", "Groceries")
        self.dining = cat("Food and drink", "Dining out")
        self.taxi = cat("Transportation", "Taxi")
        self.food = self.groceries.parent
        self.transport = self.taxi.parent
        self.a = register("a@example.com", PW, "Ann")
        self.b = register("b@example.com", PW, "Bea")
        self.c = register("c@example.com", PW, "Cyd")
        self.home = groups.create_group(self.a, "Home", "EUR", as_main=True)
        groups.join_group_by_token(self.home.share_token, "Bea", self.b, as_main=True)
        self.gus = groups.join_group_by_token(self.home.share_token, "Gus")
        self.rome = groups.create_group(self.a, "Rome", "USD")
        groups.join_group_by_token(self.rome.share_token, "Bea", self.b)
        self.tim = groups.join_group_by_token(self.rome.share_token, "Tim")
        self.ann, self.bea = self.member(self.home, self.a), self.member(self.home, self.b)
        self.r_ann, self.r_bea = self.member(self.rome, self.a), self.member(self.rome, self.b)
        ExchangeRate.objects.create(
            date=D(2026, 10, 20), currency="USD", rate_to_eur=Decimal("1.2")
        )
        ExchangeRate.objects.create(date=D(2026, 12, 1), currency="USD", rate_to_eur=Decimal("1.2"))

        trio = [self.ann, self.bea, self.gus]
        spend(self.home, self.ann, 3000, self.groceries, D(2026, 10, 3), trio)
        spend(self.home, self.bea, 6000, self.dining, D(2026, 10, 10), [self.ann, self.bea])
        spend(self.home, self.bea, 1500, self.taxi, D(2026, 11, 7), preset="personal")
        gone = spend(self.home, self.ann, 7700, self.taxi, D(2026, 11, 8), [self.ann, self.bea])
        delete_expense(gone)
        spend(self.home, self.ann, 4400, self.taxi, D(2026, 9, 30), [self.ann, self.bea])
        rome_trio = [self.r_ann, self.r_bea, self.tim]
        spend(self.rome, self.r_ann, 9000, self.dining, D(2026, 10, 20), rome_trio)
        spend(self.rome, self.r_bea, 600, self.taxi, D(2026, 12, 1), [self.r_ann, self.r_bea])

    @staticmethod
    def member(group, profile) -> Member:
        return Member.objects.get(group=group, profile=profile)


@pytest.fixture
def w():
    return World()


def cents(body) -> dict[str, int]:
    return {r["key"]: r["cents"] for r in body["rows"]}


def strkeys(d) -> dict[str, int]:
    return {(f"trip:{k[1]}" if isinstance(k, tuple) else str(k)): v for k, v in d.items()}


# ---- same numbers as the service ----


@pytest.mark.parametrize(
    "by,level,service",
    [
        ("member", 1, lambda g: analytics.spending_by_member(g, FROM, TO)),
        ("category", 1, lambda g: analytics.spending_by_category(g, FROM, TO, level=1)),
        ("category", 2, lambda g: analytics.spending_by_category(g, FROM, TO, level=2)),
        ("month", 1, lambda g: analytics.spending_by_month(g, FROM, TO)),
    ],
)
def test_group_analytics_equals_service(w, by, level, service):
    res = login(w.a).get(f"/api/groups/{w.home.id}/analytics/", {**RANGE, "by": by, "level": level})
    assert res.status_code == 200, res.content
    body = res.json()
    assert cents(body) == strkeys(service(w.home))
    assert (body["currency"], body["from"], body["to"]) == ("EUR", "2026-10-01", "2026-11-30")


@pytest.mark.parametrize("level", [1, 2])
def test_group_analytics_by_member_category_equals_service(w, level):
    body = (
        login(w.a)
        .get(
            f"/api/groups/{w.home.id}/analytics/",
            {**RANGE, "by": "member_category", "level": level},
        )
        .json()
    )
    service = analytics.spending_by_member_and_category(w.home, FROM, TO, level=level)
    assert {r["key"]: cents(r) for r in body["rows"]} == {
        str(m): strkeys(inner) for m, inner in service.items()
    }


@pytest.mark.parametrize(
    "params,service",
    [
        ({"by": "member"}, lambda g: home.home_spending_by_member(g, FROM, TO)),
        (
            {"by": "category", "trips": "lines", "level": 1},
            lambda g: home.home_spending_by_category(g, FROM, TO, "lines", 1),
        ),
        (
            {"by": "category", "trips": "lines", "level": 2},
            lambda g: home.home_spending_by_category(g, FROM, TO, "lines", 2),
        ),
        (
            {"by": "category", "trips": "spread", "level": 1},
            lambda g: home.home_spending_by_category(g, FROM, TO, "spread", 1),
        ),
        (
            {"by": "category", "trips": "spread", "level": 2},
            lambda g: home.home_spending_by_category(g, FROM, TO, "spread", 2),
        ),
        ({"by": "month"}, lambda g: home.home_spending_by_month(g, FROM, TO)),
    ],
)
def test_home_analytics_equals_home_service(w, params, service):
    res = login(w.b).get("/api/home/analytics/", {**RANGE, **params})
    assert res.status_code == 200, res.content
    assert cents(res.json()) == strkeys(service(w.home))


def test_home_trip_breakdown_equals_service(w):
    res = login(w.a).get(f"/api/home/analytics/trip/{w.rome.id}/", {**RANGE, "level": 2})
    assert res.status_code == 200, res.content
    service = home.home_trip_breakdown(w.home, w.rome, FROM, TO, level=2)
    assert {r["key"]: cents(r) for r in res.json()["rows"]} == {
        str(m): strkeys(inner) for m, inner in service.items()
    }
    assert res.json()["currency"] == "EUR"


def test_home_trip_breakdown_respects_date_range(w):
    api = login(w.a)
    url = f"/api/home/analytics/trip/{w.rome.id}/"
    in_range = api.get(url, RANGE).json()
    wider = api.get(url, {"from": "2026-10-01", "to": "2026-12-31"}).json()
    assert {r["key"]: r["cents"] for r in in_range["rows"]} == {
        str(w.r_ann.id): 2500,
        str(w.r_bea.id): 2500,
    }
    assert {r["key"]: r["cents"] for r in wider["rows"]} == {
        str(w.r_ann.id): 2750,
        str(w.r_bea.id): 2750,
    }
    line = cents(api.get("/api/home/analytics/", {**RANGE, "trips": "lines"}).json())
    assert sum(r["cents"] for r in in_range["rows"]) == line[f"trip:{w.rome.id}"] == 5000


# ---- KEY ----


def test_home_trips_lines_and_spread_have_equal_totals_and_different_rows(w):
    api = login(w.a)
    lines = api.get("/api/home/analytics/", {**RANGE, "by": "category", "trips": "lines"}).json()
    spread = api.get("/api/home/analytics/", {**RANGE, "by": "category", "trips": "spread"}).json()
    trip_key = f"trip:{w.rome.id}"
    assert sum(cents(lines).values()) == sum(cents(spread).values()) == 14500
    assert [r for r in lines["rows"] if r["key"].startswith("trip:")] == [
        {"key": trip_key, "label": "Rome", "cents": 5000}
    ]
    assert not [r for r in spread["rows"] if r["key"].startswith("trip:")]
    food = str(w.food.id)
    assert cents(spread)[food] == cents(lines)[food] + 5000
    assert cents(lines) != cents(spread)


# ---- labels and shape ----


def test_analytics_labels_are_names(w):
    api = login(w.a)
    url = f"/api/groups/{w.home.id}/analytics/"
    members = api.get(url, {**RANGE, "by": "member"}).json()["rows"]
    assert [r["label"] for r in members] == ["Ann", "Bea", "Gus"]
    level2 = api.get(url, {**RANGE, "level": 2}).json()["rows"]
    assert {r["label"] for r in level2} == {
        "Food and drink › Groceries",
        "Food and drink › Dining out",
        "Transportation › Taxi",
    }
    level1 = api.get(url, RANGE).json()["rows"]
    assert [r["label"] for r in level1] == ["Food and drink", "Transportation"]
    months = api.get(url, {**RANGE, "by": "month"}).json()["rows"]
    assert months == [
        {"key": "2026-10", "label": "2026-10", "cents": 9000},
        {"key": "2026-11", "label": "2026-11", "cents": 1500},
    ]


def test_analytics_member_category_rows_are_nested_and_outer_cents_sum_inner(w):
    body = (
        login(w.a)
        .get(f"/api/groups/{w.home.id}/analytics/", {**RANGE, "by": "member_category"})
        .json()
    )
    assert [r["label"] for r in body["rows"]] == ["Ann", "Bea", "Gus"]
    for row in body["rows"]:
        assert row["cents"] == sum(inner["cents"] for inner in row["rows"])
    bea = body["rows"][1]
    assert bea["rows"] == [
        {"key": str(w.food.id), "label": "Food and drink", "cents": 4000},
        {"key": str(w.transport.id), "label": "Transportation", "cents": 1500},
    ]


def test_group_analytics_counts_guest_shares(w):
    api = login(w.a)
    home_rows = cents(
        api.get(f"/api/groups/{w.home.id}/analytics/", {**RANGE, "by": "member"}).json()
    )
    assert home_rows == {str(w.ann.id): 4000, str(w.bea.id): 5500, str(w.gus.id): 1000}
    rome_rows = cents(
        api.get(f"/api/groups/{w.rome.id}/analytics/", {**RANGE, "by": "member"}).json()
    )
    assert rome_rows == {str(w.r_ann.id): 3000, str(w.r_bea.id): 3000, str(w.tim.id): 3000}


def test_home_analytics_excludes_guest_shares(w):
    """Expected figures are the hand sums in World's docstring, not a profiles_only service call."""
    api = login(w.a)
    get = lambda **p: api.get("/api/home/analytics/", {**RANGE, **p}).json()  # noqa: E731
    guests = {str(w.gus.id), str(w.tim.id)}

    by_member = get(by="member")
    assert cents(by_member) == {str(w.ann.id): 4000 + 2500, str(w.bea.id): 5500 + 2500}
    assert not guests & set(cents(by_member))

    assert cents(get(by="category", trips="lines")) == {
        str(w.food.id): 1000 + 1000 + 3000 + 3000,
        str(w.transport.id): 1500,
        f"trip:{w.rome.id}": 2500 + 2500,
    }
    assert cents(get(by="category", trips="spread")) == {
        str(w.food.id): 8000 + 5000,
        str(w.transport.id): 1500,
    }
    assert cents(get(by="month")) == {"2026-10": 8000 + 5000, "2026-11": 1500}

    trip = api.get(f"/api/home/analytics/trip/{w.rome.id}/", RANGE).json()
    assert {r["key"] for r in trip["rows"]} == {str(w.r_ann.id), str(w.r_bea.id)}
    assert all(
        r["rows"] == [{"key": str(w.food.id), "label": "Food and drink", "cents": 2500}]
        for r in trip["rows"]
    )


# ---- access ----


def test_group_analytics_outsider_gets_404(w):
    assert login(w.c).get(f"/api/groups/{w.home.id}/analytics/").status_code == 404


def test_group_analytics_member_gets_200(w):
    assert login(w.b).get(f"/api/groups/{w.home.id}/analytics/").status_code == 200


def test_group_analytics_guest_session_gets_200(w):
    res = guest_client(w.gus).get(f"/api/groups/{w.home.id}/analytics/", RANGE)
    assert res.status_code == 200
    assert sum(cents(res.json()).values()) == 10500


def test_home_analytics_guest_session_gets_401(w):
    res = guest_client(w.gus).get("/api/home/analytics/")
    assert res.status_code == 401
    assert res.json()["code"] == "not_authenticated"
    assert guest_client(w.tim).get(f"/api/home/analytics/trip/{w.rome.id}/").status_code == 401


def test_home_analytics_anonymous_gets_401(w):
    assert APIClient().get("/api/home/analytics/").status_code == 401


def test_home_analytics_profile_with_main_group_gets_200(w):
    assert login(w.a).get("/api/home/analytics/").status_code == 200


def test_home_analytics_profile_without_main_group_gets_404(w):
    api = login(w.c)
    assert api.get("/api/home/analytics/").status_code == 404
    assert api.get(f"/api/home/analytics/trip/{w.rome.id}/").status_code == 404


def test_home_trip_breakdown_unlinked_or_missing_group_gets_404(w):
    other = groups.create_group(w.c, "Cyd's flat", "EUR")
    api = login(w.a)
    for gid in (other.id, w.home.id, 999999):
        res = api.get(f"/api/home/analytics/trip/{gid}/")
        assert res.status_code == 404, gid
        assert res.json()["code"] == "not_found"


# ---- defaults and validation ----


def test_analytics_defaults_to_current_calendar_month(w, monkeypatch):
    monkeypatch.setattr("ledger.api.views.today", lambda: D(2026, 2, 14))
    spend(w.home, w.ann, 700, w.taxi, D(2026, 1, 31), [w.ann, w.bea])
    spend(w.home, w.ann, 300, w.taxi, D(2026, 2, 1), [w.ann])
    spend(w.home, w.ann, 500, w.taxi, D(2026, 3, 1), [w.ann, w.bea])
    for url in (f"/api/groups/{w.home.id}/analytics/", "/api/home/analytics/"):
        body = login(w.a).get(url, {"by": "month"}).json()
        assert (body["from"], body["to"]) == ("2026-02-01", "2026-02-28")
        assert body["rows"] == [{"key": "2026-02", "label": "2026-02", "cents": 300}]


def test_analytics_range_of_exactly_five_years_is_accepted(w):
    res = login(w.a).get(
        f"/api/groups/{w.home.id}/analytics/", {"from": "2021-01-01", "to": "2025-12-31"}
    )
    assert res.status_code == 200
    leap = login(w.a).get("/api/home/analytics/", {"from": "2024-02-29", "to": "2029-02-27"})
    assert leap.status_code == 200


def test_analytics_range_over_five_years_is_400_range_too_long(w):
    api = login(w.a)
    for url in (f"/api/groups/{w.home.id}/analytics/", "/api/home/analytics/"):
        res = api.get(url, {"from": "2021-01-01", "to": "2026-01-01"})
        assert (res.status_code, res.json()["code"]) == (400, "range_too_long")
    res = api.get("/api/home/analytics/", {"from": "2024-02-29", "to": "2029-02-28"})
    assert res.json()["code"] == "range_too_long"


def test_analytics_from_after_to_is_400_invalid_range(w):
    res = login(w.a).get(
        f"/api/groups/{w.home.id}/analytics/", {"from": "2026-11-02", "to": "2026-11-01"}
    )
    assert (res.status_code, res.json()["code"]) == (400, "invalid_range")


BAD = [
    ({"by": "week"}, "invalid_by"),
    ({"level": "3"}, "invalid_level"),
    ({"level": "x"}, "invalid_level"),
    ({"from": "2026-13-01"}, "invalid_date"),
    ({"from": "foo"}, "invalid_date"),
    ({"from": ""}, "invalid_date"),
    ({"to": "2026-13-01"}, "invalid_date"),
    ({"to": "foo"}, "invalid_date"),
    ({"to": ""}, "invalid_date"),
]


@pytest.mark.parametrize(
    "route,params,code",
    [
        *[(r, p, c) for r in ("group", "home") for p, c in BAD],
        ("home", {"trips": "both"}, "invalid_trips"),
    ],
)
def test_analytics_bad_by_level_or_trips_is_400(w, route, params, code):
    url = f"/api/groups/{w.home.id}/analytics/" if route == "group" else "/api/home/analytics/"
    res = login(w.a).get(url, params)
    assert (res.status_code, res.json()["code"]) == (400, code)


@pytest.mark.parametrize("params,code", [p for p in BAD if p[1] != "invalid_by"])
def test_home_trip_breakdown_bad_params_are_400(w, params, code):
    res = login(w.a).get(f"/api/home/analytics/trip/{w.rome.id}/", params)
    assert (res.status_code, res.json()["code"]) == (400, code)


def test_home_analytics_member_category_is_400_invalid_by(w):
    res = login(w.a).get("/api/home/analytics/", {"by": "member_category"})
    assert (res.status_code, res.json()["code"]) == (400, "invalid_by")


# ---- query bound ----


def count(api, url, params) -> int:
    with CaptureQueriesContext(connection) as ctx:
        assert api.get(url, params).status_code == 200
    return len(ctx.captured_queries)


ALL_BY = ["member", "category", "month", "member_category"]


def test_group_analytics_query_count_is_constant(w):
    api = login(w.a)
    url = f"/api/groups/{w.home.id}/analytics/"
    before = {
        (by, lv): count(api, url, {**RANGE, "by": by, "level": lv})
        for by in ALL_BY
        for lv in (1, 2)
    }
    extra = [groups.join_group_by_token(w.home.share_token, f"P{i}") for i in range(3)]
    everyone = [w.ann, w.bea, w.gus, *extra]
    for i in range(27):
        category = (w.groceries, w.dining, w.taxi)[i % 3]
        spend(w.home, everyone[i % 6], 1000 + i, category, D(2026, 10 + i % 2, 1 + i), everyone)
    after = {
        (by, lv): count(api, url, {**RANGE, "by": by, "level": lv})
        for by in ALL_BY
        for lv in (1, 2)
    }
    assert after == before


def test_home_analytics_query_count_grows_only_per_linked_trip(w):
    api = login(w.a)
    params = [
        {**RANGE, "by": by, "trips": trips}
        for by in ("member", "category", "month")
        for trips in ("lines", "spread")
    ]
    one = [count(api, "/api/home/analytics/", p) for p in params]

    for i in range(27):
        spend(w.rome, w.r_ann, 300 + i, w.dining, D(2026, 10, 20), [w.r_ann, w.r_bea, w.tim])
    assert [count(api, "/api/home/analytics/", p) for p in params] == one

    def add_trip(name):
        trip = groups.create_group(w.a, name, "USD")
        payer = Member.objects.get(group=trip, profile=w.a)
        spend(trip, payer, 1200, w.taxi, D(2026, 10, 20))

    add_trip("Oslo")
    two = [count(api, "/api/home/analytics/", p) for p in params]
    add_trip("Lima")
    three = [count(api, "/api/home/analytics/", p) for p in params]
    for a, b, c in zip(one, two, three, strict=True):
        assert 0 < b - a <= 2
        assert c - b == b - a
