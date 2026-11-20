import datetime
import io
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from importers.splitwise import importer
from importers.splitwise.client import SplitwiseClient
from importers.splitwise.mapper import CentAdjustment
from ledger.errors import LedgerError
from ledger.models import (
    Category,
    ExchangeRate,
    Expense,
    ExpensePayer,
    ExpenseSplit,
    Group,
    ImportBatch,
    Member,
    Settlement,
)
from ledger.services import expenses as expenses_service
from ledger.services.balances import net_balances
from tests.splitwise_fakes import ALICE, BEA, CARL, SW_GROUP_ID, FakeClient, sw_expense, sw_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def casa():
    group = Group.objects.create(name="Casa", currency="EUR")
    a, b, c = (Member.objects.create(group=group, display_name=n) for n in ("Alice", "Bea", "Carl"))
    return group, a, b, c


@pytest.fixture
def usd_rate():
    # 1 EUR = 1.25 USD on the Rome day of fixture id 8, so 10.00 USD = 8.00 EUR.
    ExchangeRate.objects.create(
        date=datetime.date(2021, 8, 10), currency="USD", rate_to_eur=Decimal("1.25")
    )


@pytest.fixture
def fake(monkeypatch):
    holder = {"client": FakeClient()}
    monkeypatch.setattr(SplitwiseClient, "from_env", classmethod(lambda cls: holder["client"]))
    return holder


def map_args(a, b, c) -> list[str]:
    return [f"--map={ALICE}={a.pk}", f"--map={BEA}={b.pk}", f"--map={CARL}={c.pk}"]


def run(group, members, *extra) -> str:
    out = io.StringIO()
    call_command(
        "import_splitwise",
        f"--group={SW_GROUP_ID}",
        f"--into={group.pk}",
        *map_args(*members),
        *extra,
        stdout=out,
    )
    return out.getvalue()


def run_refused(group, members, *extra) -> tuple[str, str]:
    out = io.StringIO()
    with pytest.raises(CommandError) as err:
        call_command(
            "import_splitwise",
            f"--group={SW_GROUP_ID}",
            f"--into={group.pk}",
            *map_args(*members),
            *extra,
            stdout=out,
        )
    return out.getvalue(), str(err.value)


def table_counts() -> dict[str, int]:
    return {
        "expense": Expense.all_objects.count(),
        "payer": ExpensePayer.objects.count(),
        "split": ExpenseSplit.objects.count(),
        "settlement": Settlement.all_objects.count(),
        "batch": ImportBatch.objects.count(),
    }


def imported(group, sw_id: int) -> Expense:
    return Expense.objects.get(group=group, source="splitwise", external_id=str(sw_id))


def shares(expense: Expense, related: str, field: str) -> dict[int, int]:
    return {r.member_id: getattr(r, field) for r in getattr(expense, related).all()}


def test_import_creates_exactly_the_fixture_rows(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    assert sorted(int(e.external_id) for e in Expense.objects.filter(group=group)) == [
        1, 2, 3, 4, 5, 8, 9, 10,
    ]  # fmt: skip
    expected = {
        1: (3000, "equal", {a.pk: 3000}, {a.pk: 1000, b.pk: 1000, c.pk: 1000}, "Groceries"),
        2: (5000, "exact", {b.pk: 5000}, {a.pk: 2000, b.pk: 2000, c.pk: 1000}, "Dining out"),
        3: (1200, "full_for_other", {a.pk: 1200}, {c.pk: 1200}, "Taxi"),
        4: (2500, "personal", {c.pk: 2500}, {c.pk: 2500}, "Clothing"),
        5: (
            100000,
            "equal",
            {a.pk: 60000, b.pk: 40000},
            {a.pk: 33334, b.pk: 33333, c.pk: 33333},
            "Rent",
        ),
        8: (800, "exact", {b.pk: 800}, {a.pk: 268, b.pk: 266, c.pk: 266}, "Hotel"),
        9: (900, "equal", {a.pk: 900}, {a.pk: 300, b.pk: 300, c.pk: 300}, "General"),
        10: (600, "exact", {b.pk: 600}, {a.pk: 400, b.pk: 200}, "Other"),
    }
    batch = ImportBatch.objects.get()
    for sw_id, (amount, split_type, payers, splits, category) in expected.items():
        e = imported(group, sw_id)
        assert e.amount_cents == amount, sw_id
        assert e.split_type == split_type, sw_id
        assert shares(e, "payers", "paid_cents") == payers, sw_id
        assert shares(e, "splits", "owed_cents") == splits, sw_id
        assert e.category.name == category, sw_id
        assert e.currency == "EUR" and e.import_batch == batch
    assert imported(group, 10).category.parent.name == "Home"
    assert imported(group, 9).category.parent.name == "Uncategorized"
    usd = imported(group, 8)
    assert (usd.original_amount_cents, usd.original_currency) == (1000, "USD")
    assert usd.rate_used == Decimal("0.8")
    assert imported(group, 3).date == datetime.date(2021, 7, 4)  # 22:30Z is the 4th in Rome

    settlement = Settlement.objects.get(group=group)
    assert (settlement.from_member, settlement.to_member, settlement.amount_cents) == (c, a, 2000)
    assert (settlement.source, settlement.external_id) == ("splitwise", "6")
    assert settlement.import_batch == batch


def test_balances_after_import_equal_splitwise_net_balances(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    # Splitwise net_balance sums over the EUR rows: A +260.67, B +87.67, C -348.33 (sum +0.01,
    # from id 5's unadjusted 333.33 x 3). Plus the cent adjustment on id 5 (A -1).
    # Plus the USD row converted here: A -2.68, B +5.34, C -2.66.
    expected = {a.pk: 26067 - 1 - 268, b.pk: 8767 + 534, c.pk: -34833 - 266}
    assert expected == {a.pk: 25798, b.pk: 9301, c.pk: -35099}
    assert net_balances(group) == expected
    assert sum(expected.values()) == 0

    fake_rows = FakeClient().expenses
    eur_net_balance_sum = {ALICE: 0, BEA: 0, CARL: 0}
    for row in fake_rows:
        if row["deleted_at"] or row["currency_code"] != "EUR":
            continue
        for u in row["users"]:
            eur_net_balance_sum[u["user_id"]] += importer.parse_signed_cents(u["net_balance"])
    assert eur_net_balance_sum == {ALICE: 26067, BEA: 8767, CARL: -34833}


def test_import_batch_counts_seen_created_skipped(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    batch = ImportBatch.objects.get()
    assert (batch.rows_seen, batch.rows_created, batch.rows_skipped) == (10, 9, 1)
    assert batch.finished_at is not None
    assert batch.source == "splitwise" and batch.group == group


def test_second_run_creates_nothing_and_skips_every_row(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    before = table_counts()
    nets = net_balances(group)

    out = run(group, (a, b, c))

    second = ImportBatch.objects.order_by("-pk").first()
    assert (second.rows_seen, second.rows_created, second.rows_skipped) == (10, 0, 10)
    after = table_counts()
    assert after == {**before, "batch": before["batch"] + 1}
    assert net_balances(group) == nets
    assert "expenses 0, settlements 0 / skipped: existing 9, deleted 1" in out


def test_soft_deleted_imported_expense_is_not_reimported(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    expenses_service.delete_expense(imported(group, 1))
    run(group, (a, b, c))
    assert Expense.all_objects.filter(source="splitwise", external_id="1").count() == 1
    assert not Expense.objects.filter(source="splitwise", external_id="1").exists()


def test_rows_existing_in_another_group_are_reported_with_that_group(casa, usd_rate, fake):
    group_a, a, b, c = casa
    run(group_a, (a, b, c))
    group_b = Group.objects.create(name="Casa again", currency="EUR")
    members_b = [Member.objects.create(group=group_b, display_name=n) for n in ("A", "B", "C")]
    before = table_counts()

    out, error = run_refused(group_b, members_b)

    assert f"group {group_a.pk}: 9 rows" in out
    assert "another group" in error
    assert table_counts() == before
    assert not Expense.all_objects.filter(group=group_b).exists()


def test_unmapped_user_refuses_before_writing_and_lists_users(casa, usd_rate, fake):
    group, a, b, c = casa
    before = table_counts()
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command(
            "import_splitwise",
            f"--group={SW_GROUP_ID}",
            f"--into={group.pk}",
            f"--map={ALICE}={a.pk}",
            f"--map={BEA}={b.pk}",
            stdout=out,
        )
    text = out.getvalue()
    assert "Unmapped Splitwise users:" in text
    assert "103  Carl Verdi" in text
    assert f"{c.pk}  Carl" in text  # our members, to copy into --map
    assert table_counts() == before


def test_user_who_left_the_group_is_listed_with_the_name_from_the_expense(casa, usd_rate, fake):
    group, a, b, c = casa
    fake["client"] = FakeClient(
        [sw_expense(60, "4.00", [sw_user(ALICE, "4.00", "2.00"), sw_user(104, "0", "2.00")])]
    )
    out, _ = run_refused(group, (a, b, c))
    assert "104  Dan X" in out


def test_map_to_member_of_another_group_is_refused(casa, usd_rate, fake):
    group, a, b, c = casa
    other = Group.objects.create(name="Other", currency="EUR")
    stranger = Member.objects.create(group=other, display_name="Zed")
    before = table_counts()
    _, error = run_refused(group, (a, b, stranger))
    assert "member_not_in_group" in error
    assert table_counts() == before


def test_two_users_mapped_to_one_member_is_refused(casa, usd_rate, fake):
    group, a, b, c = casa
    before = table_counts()
    _, error = run_refused(group, (a, b, b))
    assert "map_not_one_to_one" in error
    assert table_counts() == before


def test_dry_run_writes_nothing_and_prints_counts_and_first_rows(casa, usd_rate, fake):
    group, a, b, c = casa
    before = table_counts()
    out = run(group, (a, b, c), "--dry-run")
    assert table_counts() == before
    assert "seen 10 / to create: expenses 8, settlements 1 / skipped: existing 0, deleted 1" in out
    rows = out.split("First 10 rows:\n")[1].split("Dry run")[0].strip().splitlines()
    assert len(rows) == 9
    assert "Hotel NYC  8.00  exact  Bea 8.00 → Alice 2.68, Bea 2.66, Carl 2.66" in rows[0]
    assert "payment  20.00  Carl → Alice" in out
    assert "Unknown categories (→ Uncategorized/General): 1" in out
    assert "9  Crypto" in out
    assert "Cent adjustments: 1" in out
    assert "Dry run: nothing written." in out


def test_dry_run_reports_dates_shifted_by_rome(casa, usd_rate, fake):
    group, a, b, c = casa
    out = run(group, (a, b, c), "--dry-run")
    assert "Dates shifted by Europe/Rome: 1" in out
    assert "3  UTC 2021-07-03  Rome 2021-07-04" in out


def test_missing_rate_aborts_whole_run_without_writes(casa, fake):
    group, a, b, c = casa  # no USD rate stored
    before = table_counts()
    out, _ = run_refused(group, (a, b, c))
    assert "8  no_rate" in out
    assert table_counts() == before


def test_every_mapping_error_is_listed_and_nothing_is_written(casa, usd_rate, fake):
    group, a, b, c = casa
    fake["client"] = FakeClient(
        [
            sw_expense(11, "-5.00", [sw_user(ALICE, "-5.00", "-5.00")], description="Refund"),
            sw_expense(12, "1000.00", [sw_user(BEA, "1000.00", "1000.00")], currency_code="ARS"),
        ]
    )
    before = table_counts()
    for extra in ((), ("--dry-run",)):
        out, error = run_refused(group, (a, b, c), *extra)
        assert "Rows that cannot be imported (2):" in out
        assert "11  splitwise_amount" in out
        assert "12  no_rate" in out
        assert "mapping errors" in error
        assert table_counts() == before


def test_failure_midway_rolls_back_every_row_and_the_batch(casa, usd_rate, fake, monkeypatch):
    group, a, b, c = casa
    calls = {"n": 0}
    real = importer.create_expense

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise LedgerError("boom", "third row")
        return real(*args, **kwargs)

    monkeypatch.setattr(importer, "create_expense", flaky)
    before = table_counts()
    _, error = run_refused(group, (a, b, c))
    assert "boom" in error
    assert table_counts() == before


def test_missing_api_key_exits_non_zero(casa, monkeypatch):
    group, a, b, c = casa
    monkeypatch.setenv("SPLITWISE_API_KEY", "")
    _, error = run_refused(group, (a, b, c))
    assert "missing_api_key" in error


def test_malformed_map_is_refused(casa, fake):
    group, *_ = casa
    with pytest.raises(CommandError):
        call_command(
            "import_splitwise", f"--group={SW_GROUP_ID}", f"--into={group.pk}", "--map=101:1"
        )


# ---- balance check ----


def balance_lines(out: str) -> dict[str, str]:
    block = out.split("Balance check (imported rows only):\n")[1]
    return {
        line.strip().split("  ")[0] + " " + line.strip().split("  ")[1]: line.strip()
        for line in block.splitlines()
        if line.startswith("  ")
    }


def test_balance_check_matches_group_currency_and_labels_foreign(casa, usd_rate, fake):
    group, a, b, c = casa
    out = run(group, (a, b, c))
    lines = balance_lines(out)
    assert lines["EUR Alice"] == (
        "EUR  Alice  splitwise +260.67  ours +260.66  = after cent adjustment (sw ids 5)"
    )
    assert lines["EUR Bea"] == "EUR  Bea  splitwise +87.67  ours +87.67"
    assert lines["EUR Carl"] == "EUR  Carl  splitwise -348.33  ours -348.33"
    assert lines["USD Alice"] == (
        "USD  Alice  Splitwise -3.34 USD; ours -2.68 EUR at ECB rates, not compared"
    )
    assert lines["USD Bea"].endswith("not compared") and "✗" not in lines["USD Bea"]
    assert not [line for line in lines.values() if "✗" in line]
    assert "Balance check: 0 ✗" in out


def check(group, a, b, c, sw_group=None):
    client = FakeClient()
    rows = [r for r in client.expenses if not r["deleted_at"]]
    currency_by_sw_id = {r["id"]: r["currency_code"] for r in rows}
    user_map = {ALICE: a.pk, BEA: b.pk, CARL: c.pk}
    adjustments = [CentAdjustment(sw_id=5, member_id=a.pk, delta=-1, currency="EUR")]
    return importer.balance_check(
        group, sw_group or client.group, currency_by_sw_id, adjustments, user_map
    )


def test_balance_check_marks_unexplained_difference(casa, usd_rate, fake):
    group, a, b, c = casa
    run(group, (a, b, c))
    lines, mismatches = check(group, a, b, c)
    assert mismatches == 0

    # One imported split of id 2 moved by a cent: C owes 10.01, B 19.99 (total still 50.00).
    expense = imported(group, 2)
    ExpenseSplit.objects.filter(expense=expense, member=c).update(owed_cents=1001)
    ExpenseSplit.objects.filter(expense=expense, member=b).update(owed_cents=1999)
    lines, mismatches = check(group, a, b, c)
    by_name = {line.split("  ")[0] + " " + line.split("  ")[1]: line for line in lines}
    assert mismatches == 2
    assert by_name["EUR Bea"].endswith("✗") and by_name["EUR Carl"].endswith("✗")
    assert by_name["EUR Alice"].endswith("= after cent adjustment (sw ids 5)")

    # Splitwise's own balance off by 0.02 for Carl.
    ExpenseSplit.objects.filter(expense=expense, member=c).update(owed_cents=1000)
    ExpenseSplit.objects.filter(expense=expense, member=b).update(owed_cents=2000)
    sw_group = FakeClient().group
    carl = next(m for m in sw_group["members"] if m["id"] == CARL)
    carl["balance"] = [
        {"currency_code": "EUR", "amount": "-348.35"},
        {"currency_code": "USD", "amount": "-3.33"},
    ]
    lines, mismatches = check(group, a, b, c, sw_group)
    assert mismatches == 1
    assert [line for line in lines if line.endswith("✗")] == [
        "EUR  Carl  splitwise -348.35  ours -348.33  ✗"
    ]


def test_category_seed_has_every_pair_the_fixture_uses():
    for parent, name in [("Home", "Other"), ("Entertainment", "Other"), ("Home", "Rent")]:
        assert Category.objects.filter(parent__name=parent, name=name).exists()
