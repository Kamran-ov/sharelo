import datetime
from decimal import Decimal

import pytest

from importers.splitwise.mapper import (
    CategoryMap,
    CentAdjustment,
    MappedExpense,
    MappedSettlement,
    Skipped,
    map_expense,
    parse_cents,
    rome_date,
)
from ledger.errors import LedgerError
from tests.splitwise_fakes import ALICE, BEA, CARL, fixture_expenses, load, sw_expense, sw_user

# Our member ids for Alice < Bea < Carl.
A, B, C = 11, 12, 13
USER_MAP = {ALICE: A, BEA: B, CARL: C}

# (id, parent name, name) as in our seeded tree; ids are arbitrary here.
OURS = [
    (100, None, "Entertainment"),
    (101, "Entertainment", "Other"),
    (102, "Entertainment", "Games"),
    (110, None, "Food and drink"),
    (111, "Food and drink", "Groceries"),
    (112, "Food and drink", "Dining out"),
    (120, None, "Home"),
    (121, "Home", "Other"),
    (122, "Home", "Rent"),
    (130, None, "Life"),
    (131, "Life", "Clothing"),
    (140, None, "Transportation"),
    (141, "Transportation", "Hotel"),
    (142, "Transportation", "Taxi"),
    (150, None, "Uncategorized"),
    (151, "Uncategorized", "General"),
]
CATEGORIES = CategoryMap.build(load("categories.json")["categories"], OURS)


def eur_per_usd(day: datetime.date, currency: str) -> Decimal:
    assert currency == "USD"
    return Decimal("0.8")


def no_rate(day: datetime.date, currency: str) -> Decimal:
    raise LedgerError("no_rate", f"{currency} on {day}")


def fx(sw_id: int) -> dict:
    return next(e for e in fixture_expenses() if e["id"] == sw_id)


def mapped(raw: dict, rate_for=eur_per_usd):
    return map_expense(
        raw, user_map=USER_MAP, categories=CATEGORIES, group_currency="EUR", rate_for=rate_for
    )


def test_share_strings_parse_to_exact_cents():
    assert parse_cents("12.5") == 1250
    assert parse_cents("0.10") == 10
    assert parse_cents("1000") == 100000
    assert parse_cents("333.33") == 33333
    assert parse_cents(7) == 700


@pytest.mark.parametrize("bad", ["-1.00", "33.333", "1e3", "", " ", "1,50", None, True, 1.5])
def test_malformed_or_negative_amount_strings_are_refused(bad):
    with pytest.raises(LedgerError) as err:
        parse_cents(bad)
    assert err.value.code == "splitwise_amount"


def test_equal_split_maps_to_equal():
    row = mapped(fx(1))
    assert isinstance(row, MappedExpense)
    assert row.split_type == "equal"
    assert row.amount_cents == 3000
    assert row.payers == {A: 3000}
    assert row.splits == {A: 1000, B: 1000, C: 1000}
    assert row.original_currency is None and row.rate_used is None
    assert row.external_id == "1"


def test_unequal_split_maps_to_exact():
    row = mapped(fx(2))
    assert row.split_type == "exact"
    assert row.payers == {B: 5000}
    assert row.splits == {A: 2000, B: 2000, C: 1000}


def test_paid_for_other_maps_to_full_for_other():
    row = mapped(fx(3))
    assert row.split_type == "full_for_other"
    assert row.payers == {A: 1200}
    assert row.splits == {C: 1200}


def test_payer_owing_everything_maps_to_personal():
    row = mapped(fx(4))
    assert row.split_type == "personal"
    assert row.payers == {C: 2500} and row.splits == {C: 2500}


def test_multi_payer_keeps_each_payers_amount():
    row = mapped(fx(5))
    assert row.payers == {A: 60000, B: 40000}
    assert row.notes == "split three ways"


def test_one_cent_gap_goes_to_lowest_member_and_is_reported():
    row = mapped(fx(5))  # owed 333.33 x 3 = 999.99 of 1000.00
    assert row.splits == {A: 33334, B: 33333, C: 33333}
    assert sum(row.splits.values()) == row.amount_cents
    assert row.split_type == "equal"  # the corrected split is exactly our equal rule
    assert row.adjustments == [CentAdjustment(sw_id=5, member_id=A, delta=-1, currency="EUR")]


def test_one_cent_gap_on_the_paid_side_raises_the_payers_net():
    raw = sw_expense(40, "10.00", [sw_user(ALICE, "4.99", "5.00"), sw_user(BEA, "5.00", "5.00")])
    row = mapped(raw)
    assert row.payers == {A: 500, B: 500}
    assert row.adjustments == [CentAdjustment(sw_id=40, member_id=A, delta=1, currency="EUR")]


def test_gap_over_one_cent_is_refused():
    raw = sw_expense(41, "10.00", [sw_user(ALICE, "10.00", "4.99"), sw_user(BEA, "0", "4.99")])
    with pytest.raises(LedgerError) as err:
        mapped(raw)
    assert err.value.code == "splitwise_sum_mismatch"


def test_payment_maps_to_settlement_from_payer_to_receiver():
    row = mapped(fx(6))  # Carl paid Alice 20.00
    assert isinstance(row, MappedSettlement)
    assert (row.from_member_id, row.to_member_id, row.amount_cents) == (C, A, 2000)
    assert row.notes == ""


def test_payment_with_two_receivers_is_refused():
    raw = sw_expense(
        42,
        "20.00",
        [sw_user(CARL, "20.00", "0"), sw_user(ALICE, "0", "10.00"), sw_user(BEA, "0", "10.00")],
        payment=True,
    )
    with pytest.raises(LedgerError) as err:
        mapped(raw)
    assert err.value.code == "splitwise_payment_shape"


def test_deleted_expense_is_skipped():
    assert mapped(fx(7)) == Skipped(7, "deleted")


def test_zero_cost_expense_is_skipped():
    raw = sw_expense(43, "0.0", [sw_user(ALICE, "0.0", "0.0")])
    assert mapped(raw) == Skipped(43, "zero_cost")


def test_foreign_expense_keeps_original_and_splits_sum_to_converted_amount():
    row = mapped(fx(8))  # 10.00 USD at 0.8 EUR/USD
    assert row.amount_cents == 800
    assert (row.original_amount_cents, row.original_currency) == (1000, "USD")
    assert row.rate_used == Decimal("0.8")
    assert row.payers == {B: 800}
    # split_shares(800, {A: 334, B: 333, C: 333}): floors 267/266/266, leftover cent to A.
    assert row.splits == {A: 268, B: 266, C: 266}
    assert row.sw_currency == "USD"


def test_foreign_expense_without_rate_is_refused():
    with pytest.raises(LedgerError) as err:
        mapped(fx(8), rate_for=no_rate)
    assert err.value.code == "no_rate"


def test_category_maps_by_parent_and_child_name():
    assert mapped(fx(10)).category_id == 121  # Home / Other
    raw = sw_expense(44, "6.00", [sw_user(ALICE, "6.00", "6.00")], category={"id": 5})
    assert mapped(raw).category_id == 101  # Entertainment / Other
    assert mapped(fx(2)).category_id == 112
    assert mapped(fx(2)).unknown_category is None


def test_unknown_category_falls_back_to_general_and_is_reported():
    row = mapped(fx(9))
    assert row.category_id == 151
    assert row.unknown_category == "Crypto"


def test_date_is_the_rome_day_of_the_splitwise_instant():
    assert rome_date("2021-07-03T22:30:00Z") == (
        datetime.date(2021, 7, 4),
        datetime.date(2021, 7, 3),
    )
    assert rome_date("2021-01-03T12:00:00Z")[0] == datetime.date(2021, 1, 3)
    assert rome_date("2021-01-03T23:30:00Z")[0] == datetime.date(2021, 1, 4)  # winter, +1
    assert rome_date("2021-01-03T22:30:00Z")[0] == datetime.date(2021, 1, 3)
    assert mapped(fx(3)).date == datetime.date(2021, 7, 4)


def test_unmapped_user_with_a_share_is_refused():
    raw = sw_expense(45, "6.00", [sw_user(ALICE, "6.00", "3.00"), sw_user(999, "0", "3.00")])
    with pytest.raises(LedgerError) as err:
        mapped(raw)
    assert err.value.code == "unmapped_user"
