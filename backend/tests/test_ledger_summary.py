import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger.models import Group, Member
from ledger.services import balances
from ledger.services.balances import record_settlement
from ledger.services.expenses import create_expense_from_preset, delete_expense
from ledger.services.summary import group_summary

pytestmark = pytest.mark.django_db


def add(group, category, day, payer, amount, preset="equal", description="x"):
    return create_expense_from_preset(
        group,
        preset=preset,
        payer_id=payer.id,
        description=description,
        amount_cents=amount,
        currency="EUR",
        date=day,
        category=category,
    )


def test_summary_numbers_equal_net_balances_and_simplify_debts(group, members, category, day):
    ann, ben, cy = members
    add(group, category, day, ann, 1000)
    add(group, category, day, ben, 4500)
    record_settlement(group, cy, ann, 100, day)
    s = group_summary(group)
    nets = balances.net_balances(group)
    assert {r["member_id"]: r["net"] for r in s["per_member"]} == nets
    assert [(t["from_member"], t["to_member"], t["amount_cents"]) for t in s["transfers"]] == (
        balances.simplify_debts(nets)
    )
    assert sum(r["net"] for r in s["per_member"]) == 0
    assert [r["display_name"] for r in s["per_member"]] == ["Ann", "Ben", "Cy"]


def test_member_summaries_equal_member_summary_for_every_member(group, members, category, day):
    ann, ben, cy = members
    add(group, category, day, ann, 1000)
    add(group, category, day, cy, 700, "personal")
    record_settlement(group, ben, ann, 200, day)
    bulk = balances.member_summaries(group)
    assert bulk == {m.id: balances.member_summary(group, m) for m in members}


def test_summary_total_spent_counts_every_live_expense_including_personal(
    group, members, category, day
):
    ann, ben, _ = members
    add(group, category, day, ann, 1000)
    add(group, category, day, ben, 700, "personal")
    delete_expense(add(group, category, day, ann, 9900))
    s = group_summary(group)
    assert s["total_spent_cents"] == 1700
    assert s["total_spent_cents"] == sum(r["owed_share"] for r in s["per_member"])


def test_summary_total_is_zero_for_a_group_without_expenses(group, members):
    s = group_summary(group)
    assert s["total_spent_cents"] == 0
    assert s["transfers"] == []
    assert s["recent_expenses"] == []


def test_summary_recent_expenses_are_the_last_ten_live_newest_first(group, members, category, day):
    ann, ben, _ = members
    made = []
    for i in range(12):
        payer = ann if i % 2 == 0 else ben
        made.append(add(group, category, day + datetime.timedelta(days=i // 2), payer, 100 + i))
    delete_expense(made[10])
    rows = group_summary(group)["recent_expenses"]
    live = [e for e in made if e is not made[10]]
    expected = sorted(live, key=lambda e: (e.date, e.id), reverse=True)[:10]
    assert [r["id"] for r in rows] == [e.id for e in expected]
    assert made[10].id not in [r["id"] for r in rows]
    assert rows[0]["id"] == made[11].id
    assert rows[0]["paid_by"] == [ben.id]


def _queries(group):
    with CaptureQueriesContext(connection) as ctx:
        group_summary(group)
    return len(ctx.captured_queries)


def test_summary_query_count_is_constant(category, day):
    small = Group.objects.create(name="S", currency="EUR")
    s_members = [Member.objects.create(group=small, display_name=n) for n in "AB"]
    for i in range(3):
        add(small, category, day, s_members[i % 2], 100)
    big = Group.objects.create(name="B", currency="EUR")
    b_members = [Member.objects.create(group=big, display_name=n) for n in "ABCDE"]
    for i in range(12):
        add(big, category, day, b_members[i % 5], 100)
    assert _queries(small) == _queries(big)
