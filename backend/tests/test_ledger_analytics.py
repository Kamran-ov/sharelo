import datetime
import inspect

import pytest

from ledger.errors import LedgerError
from ledger.models import Category, Group, Member
from ledger.services import analytics
from ledger.services.analytics import (
    spending_by_category,
    spending_by_member,
    spending_by_member_and_category,
    spending_by_month,
)
from ledger.services.balances import record_settlement
from ledger.services.expenses import create_expense_from_preset, delete_expense

D = datetime.date
WIDE = (D(2026, 1, 1), D(2026, 12, 31))


def add(group, category, day, payer, amount, preset="equal", **kw):
    return create_expense_from_preset(
        group,
        preset=preset,
        payer_id=payer.id,
        description="x",
        amount_cents=amount,
        currency="EUR",
        date=day,
        category=category,
        **kw,
    )


@pytest.fixture
def pair(group):
    ann = Member.objects.create(group=group, display_name="A")
    ben = Member.objects.create(group=group, display_name="B")
    return ann, ben


def test_equal_expense_counts_by_share_not_by_payer(group, pair, category, day):
    ann, ben = pair
    add(group, category, day, ann, 5000, member_ids=[ann.id, ben.id])
    assert spending_by_member(group, *WIDE) == {ann.id: 2500, ben.id: 2500}


def test_personal_expense_counts_fully_for_owner(group, pair, category, day):
    ann, ben = pair
    add(group, category, day, ann, 3000, "personal")
    assert spending_by_member(group, *WIDE) == {ann.id: 3000, ben.id: 0}


def test_level1_totals_equal_sum_of_children(group, pair, day):
    ann, ben = pair
    groceries = Category.objects.get(name="Groceries")
    dining = Category.objects.get(name="Dining out")
    add(group, groceries, day, ann, 1000, member_ids=[ann.id, ben.id])
    add(group, dining, day, ann, 400, member_ids=[ann.id, ben.id])
    parent = groceries.parent
    assert dining.parent == parent
    level1 = spending_by_category(group, *WIDE, level=1)
    level2 = spending_by_category(group, *WIDE, level=2)
    assert level1 == {parent.id: 1400}
    assert level2 == {groceries.id: 1000, dining.id: 400}


def test_root_category_expense_stays_under_itself_at_level1(group, pair, day):
    ann, _ = pair
    root = Category.objects.create(name="Misc root")
    add(group, root, day, ann, 700, "personal")
    assert spending_by_category(group, *WIDE, level=1) == {root.id: 700}
    assert spending_by_category(group, *WIDE, level=2) == {root.id: 700}


def test_category_totals_sum_to_member_totals(group, pair, category, day):
    ann, ben = pair
    add(group, category, day, ann, 1001, member_ids=[ann.id, ben.id])
    add(group, Category.objects.get(name="Dining out"), day, ben, 333, "personal")
    members = sum(spending_by_member(group, *WIDE).values())
    assert sum(spending_by_category(group, *WIDE, level=1).values()) == members
    assert sum(spending_by_category(group, *WIDE, level=2).values()) == members


def test_date_range_is_inclusive_on_both_ends(group, pair, category):
    ann, _ = pair
    for d, amount in [
        (D(2026, 9, 30), 1),
        (D(2026, 10, 1), 10),
        (D(2026, 10, 31), 100),
        (D(2026, 11, 1), 1000),
    ]:
        add(group, category, d, ann, amount, "personal")
    assert spending_by_member(group, D(2026, 10, 1), D(2026, 10, 31))[ann.id] == 110


def test_inverted_range_is_empty(group, pair, category, day):
    ann, ben = pair
    add(group, category, day, ann, 100, "personal")
    assert spending_by_member(group, D(2026, 12, 1), D(2026, 1, 1)) == {ann.id: 0, ben.id: 0}
    assert spending_by_category(group, D(2026, 12, 1), D(2026, 1, 1)) == {}


def test_deleted_expense_excluded(group, pair, category, day):
    ann, ben = pair
    exp = add(group, category, day, ann, 600, member_ids=[ann.id, ben.id])
    assert spending_by_member(group, *WIDE) == {ann.id: 300, ben.id: 300}
    delete_expense(exp)
    assert spending_by_member(group, *WIDE) == {ann.id: 0, ben.id: 0}
    assert spending_by_category(group, *WIDE) == {}


def test_settlement_never_counts_as_spending(group, pair, category, day):
    ann, ben = pair
    record_settlement(group, ben, ann, 900, day)
    assert spending_by_member(group, *WIDE) == {ann.id: 0, ben.id: 0}
    assert spending_by_category(group, *WIDE) == {}
    assert spending_by_month(group, *WIDE) == {}
    assert spending_by_member_and_category(group, *WIDE) == {}


def test_other_group_excluded(group, pair, category, day):
    ann, _ = pair
    other = Group.objects.create(name="Trip", currency="EUR")
    oa = Member.objects.create(group=other, display_name="O")
    add(other, category, day, oa, 999, "personal")
    add(group, category, day, ann, 100, "personal")
    assert spending_by_member(group, *WIDE)[ann.id] == 100
    assert sum(spending_by_category(group, *WIDE).values()) == 100
    assert spending_by_month(group, *WIDE) == {"2026-10": 100}


def test_member_filter_restricts_all_functions(group, pair, category, day):
    ann, ben = pair
    add(group, category, day, ann, 1000, member_ids=[ann.id, ben.id])
    assert spending_by_member(group, *WIDE, member=ben) == {ben.id: 500}
    assert spending_by_category(group, *WIDE, member=ben) == {category.parent.id: 500}
    assert spending_by_month(group, *WIDE, member=ben) == {"2026-10": 500}
    assert spending_by_member_and_category(group, *WIDE, member=ben) == {
        ben.id: {category.parent.id: 500}
    }


def test_member_of_other_group_refused(group, pair, category, day):
    ann, _ = pair
    other = Group.objects.create(name="Trip", currency="EUR")
    stranger = Member.objects.create(group=other, display_name="S")
    for fn in (
        spending_by_member,
        spending_by_category,
        spending_by_month,
        spending_by_member_and_category,
    ):
        with pytest.raises(LedgerError) as exc:
            fn(group, *WIDE, member=stranger)
        assert exc.value.code == "member_not_in_group"
        fn(group, *WIDE, member=ann)


def test_invalid_level_refused(group, pair, category, day):
    ann, _ = pair
    add(group, category, day, ann, 100, "personal")
    for fn in (spending_by_category, spending_by_member_and_category):
        for bad in (0, 3):
            with pytest.raises(LedgerError) as exc:
                fn(group, *WIDE, level=bad)
            assert exc.value.code == "invalid_level"
        fn(group, *WIDE, level=1)
        fn(group, *WIDE, level=2)


def test_spending_by_month_buckets_by_expense_date(group, pair, category):
    ann, _ = pair
    add(group, category, D(2026, 9, 30), ann, 10, "personal")
    add(group, category, D(2026, 10, 1), ann, 20, "personal")
    add(group, category, D(2026, 10, 31), ann, 30, "personal")
    assert spending_by_month(group, *WIDE) == {"2026-09": 10, "2026-10": 50}


def test_member_and_category_nested_sums_match_member_totals(group, pair, day):
    ann, ben = pair
    add(group, Category.objects.get(name="Groceries"), day, ann, 1001, member_ids=[ann.id, ben.id])
    add(group, Category.objects.get(name="Dining out"), day, ben, 333, "personal")
    nested = spending_by_member_and_category(group, *WIDE, level=2)
    totals = spending_by_member(group, *WIDE)
    assert {m: sum(c.values()) for m, c in nested.items()} == totals
    parent = Category.objects.get(name="Groceries").parent_id
    assert spending_by_member_and_category(group, *WIDE, level=1)[ben.id] == {parent: 500 + 333}


@pytest.mark.parametrize(
    "fn",
    [spending_by_member, spending_by_category, spending_by_month, spending_by_member_and_category],
)
@pytest.mark.parametrize("n", [1, 6])
def test_each_function_runs_in_exactly_one_query(
    django_assert_num_queries, group, pair, category, day, fn, n
):
    ann, ben = pair
    cats = list(Category.objects.filter(parent__isnull=False)[:3])
    for i in range(n):
        add(group, cats[i % 3], D(2026, 1 + i, 5), ann, 100 + i, member_ids=[ann.id, ben.id])
        add(group, cats[i % 3], D(2026, 1 + i, 6), ben, 50, "personal")
    with django_assert_num_queries(1):
        fn(group, *WIDE)


def test_analytics_module_has_no_float_or_decimal():
    src = inspect.getsource(analytics)
    for trap in ("float(", "Decimal(", "round(", " / "):
        assert trap not in src
