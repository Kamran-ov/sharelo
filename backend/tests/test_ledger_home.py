import datetime
import inspect

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Profile
from ledger.errors import LedgerError
from ledger.models import Category, ExchangeRate, GroupLink, Member, Settlement
from ledger.services import home
from ledger.services.expenses import create_expense_from_preset, delete_expense
from ledger.services.groups import (
    create_group,
    join_group_by_token,
    move_debt_to_home,
    set_link_active,
)
from ledger.services.home import (
    home_spending_by_category,
    home_spending_by_member,
    home_spending_by_month,
    home_trip_breakdown,
    linked_trips,
)

pytestmark = pytest.mark.django_db

D = datetime.date
WIDE = (D(2026, 1, 1), D(2026, 12, 31))
ROME_DAY = D(2026, 10, 2)  # a Friday
TOKYO_DAY = D(2026, 10, 5)  # a Monday


def make_profile(name: str) -> Profile:
    user = get_user_model().objects.create_user(username=name.lower())
    return Profile.objects.create(user=user, display_name=name)


def spend(group, payer, amount, category, day, preset="equal", member_ids=None):
    return create_expense_from_preset(
        group,
        preset=preset,
        payer_id=payer.id,
        member_ids=member_ids,
        description="x",
        amount_cents=amount,
        currency=group.currency,
        date=day,
        category=category,
    )


def cat(name: str) -> Category:
    return Category.objects.get(name=name)


class World:
    """Ticket 008 fixture: Home EUR (A, B), Rome EUR (A, B, guest G), Tokyo JPY (A only)."""

    def __init__(self):
        self.a, self.b = make_profile("Ann"), make_profile("Bea")
        self.home = create_group(self.a, "Home", "EUR", as_main=True)
        join_group_by_token(self.home.share_token, "Bea", profile=self.b, as_main=True)
        self.rome = create_group(self.a, "Rome", "EUR")
        join_group_by_token(self.rome.share_token, "Bea", profile=self.b)
        self.guest = join_group_by_token(self.rome.share_token, "Gus")
        self.tokyo = create_group(self.a, "Tokyo", "JPY")
        # joining always creates a Member, so "link without a member" is the one hand-written row
        GroupLink.objects.create(
            profile=self.b, sub_group=self.tokyo, main_group=self.home, active=False
        )
        ExchangeRate.objects.create(date=TOKYO_DAY, currency="JPY", rate_to_eur=160)
        self.ma = self.member(self.home, self.a)
        self.mb = self.member(self.home, self.b)
        spend(self.rome, self.member(self.rome, self.a), 9000, cat("Dining out"), ROME_DAY)
        spend(
            self.tokyo,
            self.member(self.tokyo, self.a),
            100000,
            cat("Groceries"),
            TOKYO_DAY,
            "personal",
        )
        spend(
            self.home,
            self.ma,
            5000,
            cat("Groceries"),
            ROME_DAY,
            member_ids=[self.ma.id, self.mb.id],
        )

    @staticmethod
    def member(group, profile) -> Member:
        return Member.objects.get(group=group, profile=profile)


@pytest.fixture
def w():
    return World()


def test_member_totals_match_acceptance_numbers(w):
    totals = home_spending_by_member(w.home, *WIDE)
    assert totals == {w.ma.id: 2500 + 3000 + 625, w.mb.id: 2500 + 3000}
    assert w.guest.id not in totals


def test_trip_lines_show_one_row_per_trip_without_guest_share(w):
    groceries_parent = cat("Groceries").parent_id
    assert home_spending_by_category(w.home, *WIDE, trips="lines") == {
        groceries_parent: 5000,
        ("trip", w.rome.id): 6000,
        ("trip", w.tokyo.id): 625,
    }


def test_spread_puts_trip_spending_in_real_categories(w):
    parent = cat("Groceries").parent_id
    assert home_spending_by_category(w.home, *WIDE, trips="spread", level=2) == {
        cat("Groceries").id: 5000 + 625,
        cat("Dining out").id: 6000,
    }
    assert home_spending_by_category(w.home, *WIDE, trips="spread", level=1) == {parent: 11625}


def test_lines_and_spread_sum_to_same_total_and_member_total(w):
    lines = home_spending_by_category(w.home, *WIDE, trips="lines")
    spread = home_spending_by_category(w.home, *WIDE, trips="spread")
    members = home_spending_by_member(w.home, *WIDE)
    assert sum(lines.values()) == sum(spread.values()) == sum(members.values()) == 11625


def test_deactivated_link_removes_exactly_that_partners_trip_share(w):
    """KEY: without the `active` filter the inactive link would still contribute."""
    before = home_spending_by_member(w.home, *WIDE)
    set_link_active(w.a, w.rome, False)
    after = home_spending_by_member(w.home, *WIDE)
    assert after == {w.ma.id: before[w.ma.id] - 3000, w.mb.id: before[w.mb.id]}
    set_link_active(w.a, w.rome, True)
    assert home_spending_by_member(w.home, *WIDE) == before


def test_inactive_link_without_member_contributes_nothing(w):
    assert w.mb.id in home_spending_by_member(w.home, *WIDE)
    assert not Member.objects.filter(group=w.tokyo, profile=w.b).exists()
    assert home_spending_by_member(w.home, *WIDE)[w.mb.id] == 5500


def test_trip_member_with_other_main_group_contributes_nothing(w):
    c = make_profile("Cy")
    other_home = create_group(c, "Home2", "EUR", as_main=True)
    mc = join_group_by_token(w.rome.share_token, "Cy", profile=c)
    spend(w.rome, mc, 3000, cat("Dining out"), ROME_DAY, "personal")
    assert home_spending_by_member(w.home, *WIDE)[w.ma.id] == 6125
    assert sum(home_spending_by_member(w.home, *WIDE).values()) == 11625
    # twin: the same share does reach Cy's own Home
    mc_home2 = Member.objects.get(group=other_home, profile=c)
    assert home_spending_by_member(other_home, *WIDE) == {mc_home2.id: 3000}


def test_move_to_home_pair_changes_no_spending(w):
    ma_rome = w.member(w.rome, w.a)
    mb_rome = w.member(w.rome, w.b)
    spend(w.rome, ma_rome, 3000, cat("Taxi"), ROME_DAY, member_ids=[mb_rome.id])
    snapshot = lambda: (  # noqa: E731
        home_spending_by_member(w.home, *WIDE),
        home_spending_by_category(w.home, *WIDE),
        home_spending_by_category(w.home, *WIDE, trips="spread", level=2),
        home_spending_by_month(w.home, *WIDE),
    )
    before = snapshot()
    move_debt_to_home(w.rome, w.b, w.a, 3000, ROME_DAY)
    assert Settlement.objects.count() == 2
    assert snapshot() == before


def test_conversion_uses_expense_date_rate(w):
    later = D(2026, 11, 2)
    ExchangeRate.objects.create(date=later, currency="JPY", rate_to_eur=150)
    ma_tokyo = w.member(w.tokyo, w.a)
    spend(w.tokyo, ma_tokyo, 100000, cat("Groceries"), later, "personal")
    lines = home_spending_by_category(w.home, *WIDE)
    assert lines[("trip", w.tokyo.id)] == 625 + 667
    assert home_spending_by_month(w.home, D(2026, 11, 1), D(2026, 11, 30)) == {"2026-11": 667}


def test_missing_rate_propagates_no_rate(w):
    ExchangeRate.objects.all().delete()
    with pytest.raises(LedgerError) as exc:
        home_spending_by_member(w.home, *WIDE)
    assert exc.value.code == "no_rate"
    ExchangeRate.objects.create(date=TOKYO_DAY, currency="JPY", rate_to_eur=160)
    assert home_spending_by_member(w.home, *WIDE)[w.ma.id] == 6125


def test_date_range_is_inclusive_on_both_ends_across_groups(w):
    assert sum(home_spending_by_member(w.home, ROME_DAY, TOKYO_DAY).values()) == 11625
    assert sum(home_spending_by_member(w.home, ROME_DAY + D.resolution, TOKYO_DAY).values()) == 625
    assert (
        sum(home_spending_by_member(w.home, ROME_DAY, TOKYO_DAY - D.resolution).values()) == 11000
    )


def test_deleted_trip_expense_excluded(w):
    expense = w.rome.expenses.get()
    delete_expense(expense)
    assert home_spending_by_member(w.home, *WIDE) == {w.ma.id: 2500 + 625, w.mb.id: 2500}


def test_unlinked_group_excluded(w):
    d = make_profile("Dee")
    lone = create_group(d, "Lone", "EUR")
    spend(lone, Member.objects.get(group=lone), 900, cat("Taxi"), ROME_DAY, "personal")
    assert sum(home_spending_by_member(w.home, *WIDE).values()) == 11625


def test_month_rollup_buckets_by_date_and_sums_to_total(w):
    assert home_spending_by_month(w.home, *WIDE) == {"2026-10": 11625}
    spend(w.home, w.ma, 100, cat("Taxi"), D(2026, 11, 1), "personal")
    spend(w.home, w.ma, 100, cat("Taxi"), D(2026, 9, 30), "personal")
    months = home_spending_by_month(w.home, *WIDE)
    assert months == {"2026-09": 100, "2026-10": 11625, "2026-11": 100}


def test_rounding_is_consistent_across_every_view(w):
    """Second key test: three cells of 0.625 -> 1 each (3), but the day total 1.875 would be 2."""
    day = D(2026, 10, 7)
    ExchangeRate.objects.create(date=day, currency="JPY", rate_to_eur=160)
    ma = w.member(w.tokyo, w.a)
    for name in ("Groceries", "Dining out", "Taxi"):
        spend(w.tokyo, ma, 100, cat(name), day, "personal")
    only_day = (day, day)
    lines = home_spending_by_category(w.home, *only_day, trips="lines")
    spread = home_spending_by_category(w.home, *only_day, trips="spread", level=2)
    members = home_spending_by_member(w.home, *only_day)
    breakdown = home_trip_breakdown(w.home, w.tokyo, *only_day, level=2)
    assert lines == {("trip", w.tokyo.id): 3}
    assert sum(spread.values()) == 3
    assert sum(members.values()) == 3
    assert sum(sum(c.values()) for c in breakdown.values()) == 3
    assert sum(home_spending_by_month(w.home, *only_day).values()) == 3


def test_trip_breakdown_sums_to_trip_line(w):
    line = home_spending_by_category(w.home, *WIDE)[("trip", w.rome.id)]
    for level in (1, 2):
        breakdown = home_trip_breakdown(w.home, w.rome, *WIDE, level=level)
        assert sum(sum(c.values()) for c in breakdown.values()) == line == 6000
    ma, mb = w.member(w.rome, w.a), w.member(w.rome, w.b)
    assert set(home_trip_breakdown(w.home, w.rome, *WIDE)) == {ma.id, mb.id}
    assert w.guest.id not in home_trip_breakdown(w.home, w.rome, *WIDE)


def test_unlinked_trip_breakdown_refused(w):
    d = make_profile("Dee")
    lone = create_group(d, "Lone", "EUR")
    with pytest.raises(LedgerError) as exc:
        home_trip_breakdown(w.home, lone, *WIDE)
    assert exc.value.code == "trip_not_linked"
    set_link_active(w.a, w.rome, False)
    set_link_active(w.b, w.rome, False)
    with pytest.raises(LedgerError):
        home_trip_breakdown(w.home, w.rome, *WIDE)
    set_link_active(w.a, w.rome, True)
    assert home_trip_breakdown(w.home, w.rome, *WIDE)


def test_invalid_trips_value_refused(w):
    for fn in (home_spending_by_member, home_spending_by_category, home_spending_by_month):
        with pytest.raises(LedgerError) as exc:
            fn(w.home, *WIDE, trips="nope")
        assert exc.value.code == "invalid_trips"
        fn(w.home, *WIDE, trips="lines")
        fn(w.home, *WIDE, trips="spread")


def test_linked_trips_lists_active_linked_groups_with_names(w):
    trips = linked_trips(w.home)
    assert {(t.name, t.currency) for t in trips} == {("Rome", "EUR"), ("Tokyo", "JPY")}
    set_link_active(w.a, w.tokyo, False)
    assert [t.name for t in linked_trips(w.home)] == ["Rome"]


def _many_days_tokyo(w, days: int, per_day: int):
    ma = w.member(w.tokyo, w.a)
    start = D(2026, 11, 1)
    for i in range(days):
        day = start + datetime.timedelta(days=i)
        ExchangeRate.objects.update_or_create(
            date=day, currency="JPY", defaults={"rate_to_eur": 150 + i}
        )
        for _ in range(per_day):
            spend(w.tokyo, ma, 1000, cat("Taxi"), day, "personal")


def test_query_count_is_a_function_of_linked_sub_groups_only(w, django_assert_max_num_queries):
    """Constants: main-group analytics call, Home members with profile, active links.
    Per sub-group: one cell aggregate + at most one rate query. N = 2 (Rome, Tokyo)."""
    budget = 3 + 2 * 2
    calls = (
        lambda: home_spending_by_member(w.home, *WIDE),  # noqa: E731
        lambda: home_spending_by_category(w.home, *WIDE, trips="spread"),
        lambda: home_spending_by_month(w.home, *WIDE),
    )
    for call in calls:
        with django_assert_max_num_queries(budget):
            call()
    _many_days_tokyo(w, days=14, per_day=2)  # more distinct dates and 10x+ the expenses
    for call in calls:
        with django_assert_max_num_queries(budget):
            call()
    # breakdown: links, one cell aggregate, one rate query
    with django_assert_max_num_queries(3):
        home_trip_breakdown(w.home, w.tokyo, *WIDE)


def test_home_module_has_no_float_or_decimal():
    source = inspect.getsource(home)
    assert "float" not in source and "Decimal" not in source
