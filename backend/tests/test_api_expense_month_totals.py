import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger.services import expenses

pytestmark = pytest.mark.django_db


def make(world, group, cents, day, preset="half", payer=None):
    me = world.member(payer or world.a, group)
    others = [m.id for m in group.members.all()]
    split = {m: cents // len(others) for m in others}
    split[others[0]] += cents - sum(split.values())
    return expenses.create_expense(
        group,
        description="x",
        amount_cents=cents,
        currency=group.currency,
        date=day,
        category=world.groceries,
        payers={me.id: cents},
        splits=split,
        split_type="personal" if preset == "personal" else "equal",
    )


def page(client, world, n, group=None):
    return client.get(f"/api/groups/{(group or world.home).id}/expenses/", {"page": n}).json()


def test_month_total_counts_rows_on_other_pages(world, api_a):
    for i in range(60):
        make(world, world.home, 100, datetime.date(2026, 10, 1 + i % 28))
    first, second = page(api_a, world, 1), page(api_a, world, 2)
    assert len(first["results"]) == 50 and len(second["results"]) == 10
    assert first["month_totals"] == {"2026-10": 6000}
    assert second["month_totals"] == {"2026-10": 6000}


def test_month_total_excludes_deleted_and_other_groups(world, api_a):
    keep = make(world, world.home, 100, datetime.date(2026, 10, 3))
    gone = make(world, world.home, 700, datetime.date(2026, 10, 4))
    make(world, world.rome, 900, datetime.date(2026, 10, 5))
    expenses.delete_expense(gone)
    assert keep.pk
    assert page(api_a, world, 1)["month_totals"] == {"2026-10": 100}


def test_month_total_includes_personal_rows_and_splits_months(world, api_a):
    make(world, world.home, 250, datetime.date(2026, 10, 31))
    make(world, world.home, 400, datetime.date(2026, 11, 1), preset="personal")
    assert page(api_a, world, 1)["month_totals"] == {"2026-10": 250, "2026-11": 400}


def test_expense_page_query_count_is_constant_with_month_totals(world, api_a):
    def queries():
        with CaptureQueriesContext(connection) as ctx:
            assert api_a.get(f"/api/groups/{world.home.id}/expenses/").status_code == 200
        return len(ctx)

    make(world, world.home, 100, datetime.date(2026, 9, 1))
    few = queries()
    for i in range(12):
        make(world, world.home, 100, datetime.date(2026, 1 + i % 9, 1))
    assert queries() == few
