import datetime
import inspect
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ledger.errors import LedgerError
from ledger.models import Expense, Group, Member, RecurringRule
from ledger.services import recurring
from ledger.services.balances import net_balances
from ledger.services.expenses import create_expense_from_preset
from ledger.services.recurring import (
    create_rule,
    delete_rule,
    first_occurrence,
    generate_due,
    job_status,
    next_occurrence,
    pause_rule,
    record_job_run,
    resume_rule,
    skip_next,
    update_rule,
)

D = datetime.date


def make_rule(group, payer, category, **kw):
    fields = {
        "description": "Rent",
        "amount_cents": 1000,
        "payer": payer,
        "split_type": "equal",
        "category": category,
        "frequency": "monthly",
        "day_of_month": 1,
        "start_date": D(2026, 7, 1),
    }
    fields.update(kw)
    return create_rule(group, **fields)


def walk(rule, start, n):
    out, cur = [], first_occurrence(start, rule)
    for _ in range(n):
        out.append(cur)
        cur = next_occurrence(cur, rule)
    return out


@pytest.fixture
def ann(members):
    return members[0]


def test_monthly_day_31_clamps_to_month_end(group, ann, category):
    rule = make_rule(group, ann, category, day_of_month=31, start_date=D(2027, 1, 31))
    assert walk(rule, D(2027, 1, 31), 4) == [
        D(2027, 1, 31),
        D(2027, 2, 28),
        D(2027, 3, 31),
        D(2027, 4, 30),
    ]
    leap = make_rule(group, ann, category, day_of_month=31, start_date=D(2028, 1, 31))
    assert walk(leap, D(2028, 1, 31), 2)[1] == D(2028, 2, 29)


def test_yearly_feb_29_clamps_in_non_leap_years(group, ann, category):
    rule = make_rule(
        group, ann, category, frequency="yearly", month=2, day_of_month=29, start_date=D(2027, 1, 1)
    )
    assert walk(rule, D(2027, 1, 1), 3) == [D(2027, 2, 28), D(2028, 2, 29), D(2029, 2, 28)]


def test_rewound_rule_does_not_duplicate_expense(group, ann, category):
    rule = make_rule(group, ann, category)
    today = D(2026, 7, 15)
    assert len(generate_due(today).created) == 1
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 8, 1)
    RecurringRule.objects.filter(pk=rule.pk).update(
        next_date=D(2026, 7, 1)
    )  # crashed before advancing
    second = generate_due(today)
    assert second.created == [] and second.failed == []
    assert Expense.objects.filter(recurring_rule=rule).count() == 1
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 8, 1)


def test_generate_due_twice_creates_nothing_the_second_time(group, ann, category):
    make_rule(group, ann, category)
    assert len(generate_due(D(2026, 7, 15)).created) == 1
    assert generate_due(D(2026, 7, 15)).created == []
    assert len(generate_due(D(2026, 8, 2)).created) == 1


def test_duplicate_external_id_is_refused_by_the_database(group, ann, category):
    rule = make_rule(group, ann, category)
    generate_due(D(2026, 7, 1))
    with pytest.raises(LedgerError) as exc:
        create_expense_from_preset(
            group,
            preset="equal",
            payer_id=ann.id,
            description="x",
            amount_cents=1000,
            currency="EUR",
            date=D(2026, 7, 1),
            category=category,
            source="recurring",
            external_id=f"rule:{rule.pk}:2026-07-01",
        )
    assert exc.value.code == "duplicate_external_id"


def test_catch_up_creates_one_expense_per_missed_occurrence(group, ann, category):
    rule = make_rule(group, ann, category, start_date=D(2026, 7, 1))
    result = generate_due(D(2026, 9, 20))
    assert sorted(e.date for e in result.created) == [D(2026, 7, 1), D(2026, 8, 1), D(2026, 9, 1)]
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 10, 1)


def test_not_yet_due_rule_creates_nothing(group, ann, category):
    make_rule(group, ann, category, start_date=D(2026, 12, 1))
    assert generate_due(D(2026, 10, 18)).created == []


def test_paused_rule_creates_nothing(group, ann, category):
    rule = make_rule(group, ann, category)
    pause_rule(rule)
    assert generate_due(D(2026, 10, 18)).created == []


def test_resume_does_not_backfill_paused_months(group, ann, category):
    rule = make_rule(group, ann, category)
    pause_rule(rule)
    resume_rule(rule, D(2026, 10, 18))
    assert rule.next_date == D(2026, 11, 1)
    created = generate_due(D(2026, 11, 2)).created
    assert [e.date for e in created] == [D(2026, 11, 1)]


def test_unpaused_rule_backfills_the_same_period(group, ann, category):
    make_rule(group, ann, category)
    assert len(generate_due(D(2026, 10, 18)).created) == 4


def test_skip_next_advances_one_occurrence_without_expense(group, ann, category):
    rule = make_rule(group, ann, category)
    skip_next(rule)
    assert rule.next_date == D(2026, 8, 1)
    assert Expense.objects.count() == 0


def test_skip_next_refuses_a_paused_rule(group, ann, category):
    rule = make_rule(group, ann, category)
    pause_rule(rule)
    with pytest.raises(LedgerError) as exc:
        skip_next(rule)
    assert exc.value.code == "rule_paused"
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 7, 1)


def test_skip_after_resume_advances_one_occurrence(group, ann, category):
    rule = make_rule(group, ann, category)
    pause_rule(rule)
    resume_rule(rule, D(2026, 7, 1))
    skip_next(rule)
    assert rule.next_date == D(2026, 8, 1)


def test_update_rule_changes_only_future_expenses(group, ann, category):
    rule = make_rule(group, ann, category)
    generate_due(D(2026, 7, 2))
    update_rule(rule, amount_cents=2000)
    generate_due(D(2026, 8, 2))
    amounts = list(Expense.objects.order_by("date").values_list("amount_cents", flat=True))
    assert amounts == [1000, 2000]


def test_schedule_edit_recomputes_next_date_without_double_billing(group, ann, category):
    rule = make_rule(group, ann, category, start_date=D(2026, 10, 1))
    generate_due(D(2026, 10, 1))
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 11, 1)
    update_rule(rule, today=D(2026, 10, 18), day_of_month=20)
    assert rule.next_date == D(2026, 11, 20)
    assert generate_due(D(2026, 10, 31)).created == []
    assert [e.date for e in generate_due(D(2026, 11, 20)).created] == [D(2026, 11, 20)]


def test_amount_only_edit_leaves_next_date_untouched(group, ann, category):
    rule = make_rule(group, ann, category)
    before = rule.next_date
    update_rule(rule, amount_cents=5000)
    rule.refresh_from_db()
    assert rule.next_date == before and rule.amount_cents == 5000


def test_schedule_edit_without_today_refused(group, ann, category):
    rule = make_rule(group, ann, category)
    with pytest.raises(LedgerError) as exc:
        update_rule(rule, day_of_month=20)
    assert exc.value.code == "today_required"
    update_rule(rule, today=D(2026, 7, 2), day_of_month=20)


def test_delete_rule_keeps_past_expenses(group, ann, category):
    rule = make_rule(group, ann, category)
    generate_due(D(2026, 7, 2))
    delete_rule(rule)
    expense = Expense.objects.get()
    assert expense.recurring_rule.pk == rule.pk
    assert generate_due(D(2026, 12, 1)).created == []
    assert Expense.objects.count() == 1


def test_end_date_stops_generation(group, ann, category):
    make_rule(group, ann, category, end_date=D(2026, 8, 1))
    assert [e.date for e in generate_due(D(2026, 12, 1)).created] == [D(2026, 7, 1), D(2026, 8, 1)]


def test_bad_rule_fails_alone(group, ann, category):
    other = Member.objects.create(
        group=Group.objects.create(name="Other", currency="EUR"), display_name="Zed"
    )
    good = make_rule(group, ann, category)
    broken = make_rule(group, ann, category, description="Broken")
    RecurringRule.objects.filter(pk=broken.pk).update(payer=other)  # stands in for a removed member
    result = generate_due(D(2026, 7, 2))
    assert result.failed == [(broken.pk, "member_not_in_group")]
    assert [e.recurring_rule_id for e in result.created] == [good.pk]
    broken.refresh_from_db()
    assert broken.next_date == D(2026, 7, 1)  # failed rule does not advance


def test_failed_rule_does_not_advance_next_date(group, ann, category):
    other = Member.objects.create(
        group=Group.objects.create(name="O", currency="EUR"), display_name="Zed"
    )
    rule = make_rule(group, ann, category)
    RecurringRule.objects.filter(pk=rule.pk).update(payer=other)
    generate_due(D(2026, 9, 1))
    rule.refresh_from_db()
    assert rule.next_date == D(2026, 7, 1)
    RecurringRule.objects.filter(pk=rule.pk).update(payer=ann)  # twin: fixed rule catches up
    assert len(generate_due(D(2026, 9, 1)).created) == 3


def test_run_daily_prints_counts(group, ann, category, monkeypatch):
    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", lambda: 5)
    make_rule(group, ann, category)
    out = StringIO()
    call_command("run_daily", "--today=2026-08-02", stdout=out)
    assert out.getvalue().splitlines() == [
        "rates upserted: 5",
        "expenses created: 2",
        "rules failed: 0",
    ]


def test_run_daily_records_last_run(group, ann, category, monkeypatch):
    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", lambda: 0)
    assert job_status("run_daily") is None
    call_command("run_daily", "--today=2026-08-02", stdout=StringIO())
    assert job_status("run_daily") is not None


def test_run_daily_records_last_run_even_when_a_rule_fails(group, ann, category, monkeypatch):
    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", lambda: 0)
    other = Member.objects.create(
        group=Group.objects.create(name="O", currency="EUR"), display_name="Zed"
    )
    rule = make_rule(group, ann, category)
    RecurringRule.objects.filter(pk=rule.pk).update(payer=other)
    with pytest.raises(CommandError):
        call_command("run_daily", "--today=2026-08-02", stdout=StringIO())
    assert job_status("run_daily") is not None


def test_run_daily_with_invalid_today_records_nothing(db):
    with pytest.raises(CommandError):
        call_command("run_daily", "--today=nope", stdout=StringIO())
    assert job_status("run_daily") is None


def test_record_job_run_keeps_one_row_per_name(db):
    first = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    second = datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC)
    record_job_run("run_daily", first)
    record_job_run("run_daily", second)
    assert job_status("run_daily") == second


@pytest.mark.parametrize(
    "bad",
    [
        {"amount_cents": 0},
        {"month": 3},
        {"day_of_month": 32},
        {"frequency": "yearly"},
        {"end_date": D(2026, 1, 1)},
        {"split_type": "percentage", "split_params": {}},
    ],
)
def test_create_rule_refuses_invalid(group, ann, category, bad):
    with pytest.raises(LedgerError):
        make_rule(group, ann, category, **bad)
    assert make_rule(group, ann, category).pk


def test_create_rule_refuses_payer_from_another_group(group, ann, category):
    other = Member.objects.create(
        group=Group.objects.create(name="O", currency="EUR"), display_name="Zed"
    )
    with pytest.raises(LedgerError) as exc:
        make_rule(group, other, category)
    assert exc.value.code == "not_a_member"


def test_generated_expense_balances_and_currency(group, members, category):
    ann, ben, cy = members
    make_rule(group, ann, category, start_date=D(2026, 7, 1))
    expense = generate_due(D(2026, 7, 1)).created[0]
    assert expense.source == "recurring" and expense.currency == group.currency
    assert expense.external_id == f"rule:{expense.recurring_rule_id}:2026-07-01"
    owed = sorted(expense.splits.values_list("owed_cents", flat=True))
    assert owed == [333, 333, 334] and sum(owed) == expense.amount_cents
    assert sum(net_balances(group).values()) == 0


def test_run_daily_still_generates_when_rates_fail(group, ann, category, monkeypatch):
    make_rule(group, ann, category)

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", boom)
    out = StringIO()
    call_command("run_daily", "--today=2026-07-02", stdout=out)
    assert "expenses created: 1" in out.getvalue()
    assert Expense.objects.count() == 1


def test_run_daily_exits_nonzero_when_a_rule_fails(group, ann, category, monkeypatch):
    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", lambda: 3)
    other = Member.objects.create(
        group=Group.objects.create(name="O", currency="EUR"), display_name="Zed"
    )
    good = make_rule(group, ann, category)
    broken = make_rule(group, ann, category, description="Broken")
    out = StringIO()
    call_command("run_daily", "--today=2026-07-02", stdout=out)  # twin: all fine, no error
    assert "rates upserted: 3" in out.getvalue() and "rules failed: 0" in out.getvalue()
    RecurringRule.objects.filter(pk=broken.pk).update(payer=other)
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("run_daily", "--today=2026-08-02", stdout=out)
    assert "expenses created: 1" in out.getvalue() and "rules failed: 1" in out.getvalue()
    assert good.expenses.count() == 2


def test_production_fixture_of_five_rules(group, members, category, monkeypatch):
    monkeypatch.setattr("ledger.management.commands.run_daily.fetch_ecb_rates", lambda: 0)
    ann, ben, cy = members
    other = Member.objects.create(
        group=Group.objects.create(name="O", currency="EUR"), display_name="Zed"
    )
    start = D(2026, 7, 1)
    make_rule(group, ann, category, description="Rent", amount_cents=120000, start_date=start)
    make_rule(
        group,
        ann,
        category,
        description="Netflix",
        amount_cents=1599,
        day_of_month=31,
        start_date=start,
    )
    make_rule(
        group,
        ben,
        category,
        description="Insurance",
        amount_cents=30000,
        frequency="yearly",
        month=3,
        day_of_month=15,
        start_date=start,
    )
    gym = make_rule(
        group, cy, category, description="Gym", amount_cents=2500, day_of_month=5, start_date=start
    )
    pause_rule(gym)
    broken = make_rule(group, ann, category, description="Broken", start_date=start)
    RecurringRule.objects.filter(pk=broken.pk).update(payer=other)

    for expected_created in (7, 0):
        out = StringIO()
        with pytest.raises(CommandError):
            call_command("run_daily", "--today=2026-10-18", stdout=out)
        assert f"expenses created: {expected_created}" in out.getvalue()
        assert "rules failed: 1" in out.getvalue()
    nets = net_balances(group)
    assert (nets[ann.id], nets[ben.id], nets[cy.id]) == (323198, -161599, -161599)
    assert sum(nets.values()) == 0
    assert Expense.objects.filter(description="Netflix").count() == 3
    assert RecurringRule.objects.get(description="Rent").next_date == D(2026, 11, 1)
    assert RecurringRule.objects.get(description="Netflix").next_date == D(2026, 10, 31)


def test_recurring_module_has_no_float_or_decimal():
    source = inspect.getsource(recurring)
    for banned in ("float(", "Decimal(", "round(", " / "):
        assert banned not in source, banned
