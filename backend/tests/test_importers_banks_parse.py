import datetime
import re
from pathlib import Path

import pytest

from importers.banks import revolut, wise
from importers.banks.common import detect, parse_cents, read_csv
from ledger.errors import LedgerError

FIXTURES = Path(__file__).parent / "fixtures" / "banks"
BANKS_PKG = Path(__file__).resolve().parents[1] / "importers" / "banks"


def parse_bytes(data: bytes):
    header, lines = read_csv(data)
    bank = detect(header)
    return bank, (revolut.parse if bank == "revolut" else wise.parse)(lines)


def parse_fixture(name: str):
    return parse_bytes((FIXTURES / name).read_bytes())


REVOLUT_HEADER = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
)


def revolut_line(
    amount="-1.00",
    fee="0.00",
    completed="2026-09-01 10:00:00",
    description="Shop",
    currency="EUR",
    balance="100.00",
    state="COMPLETED",
) -> str:
    return (
        f"CARD_PAYMENT,Current,2026-09-01 09:00:00,{completed},{description},{amount},{fee},"
        f"{currency},{state},{balance}\n"
    )


@pytest.mark.parametrize(
    ("text", "cents"), [("-12.5", -1250), ("0.10", 10), ("1000", 100000), ("-0.01", -1)]
)
def test_amount_text_parses_to_exact_cents(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.parametrize("text", ["1,234.56", "12.345", "1e3", "", "abc"])
def test_malformed_amount_text_is_a_bad_row(text):
    data = (REVOLUT_HEADER + revolut_line() + revolut_line(amount=f'"{text}"')).encode()
    with pytest.raises(LedgerError) as exc:
        parse_bytes(data)
    assert exc.value.code == "bad_bank_row"
    assert "line 3: Amount" in str(exc.value)


def test_every_bad_row_is_listed_together():
    data = (
        REVOLUT_HEADER
        + revolut_line(amount='"-1,00"')
        + revolut_line()
        + revolut_line(completed="31/02/2026")
    ).encode()
    with pytest.raises(LedgerError) as exc:
        parse_bytes(data)
    assert "line 2: Amount" in str(exc.value)
    assert "line 4: Completed Date" in str(exc.value)


def test_revolut_keeps_only_completed_money_out():
    bank, rows = parse_fixture("revolut_2026_09.csv")
    assert bank == "revolut"
    descriptions = [r.description for r in rows]
    assert descriptions == [
        "Esselunga",
        "Taxi Milano",
        "Starbucks NYC",
        "Bar Roma",
        "Bar Roma",
        "Metal plan fee",
        "Exchanged to USD",
    ]
    # top-up (money in), reverted and declined rows are not candidates
    for gone in ("Top-up by *1234", "Amazon", "Zara"):
        assert gone not in descriptions
    assert [r.amount_cents for r in rows] == [2340, 1280, 875, 120, 120, 199, 10000]
    assert rows[0].date == datetime.date(2026, 9, 1)
    assert rows[0].merchant == ""


def test_revolut_fee_is_added_to_the_amount():
    _, rows = parse_bytes((REVOLUT_HEADER + revolut_line(amount="-12.50", fee="0.30")).encode())
    assert [r.amount_cents for r in rows] == [1280]


def test_revolut_fee_only_row_is_money_out():
    _, rows = parse_bytes((REVOLUT_HEADER + revolut_line(amount="0.00", fee="1.99")).encode())
    assert [r.amount_cents for r in rows] == [199]


def test_revolut_completed_row_without_balance_is_a_bad_row():
    with pytest.raises(LedgerError) as exc:
        parse_bytes((REVOLUT_HEADER + revolut_line(balance="")).encode())
    assert exc.value.code == "bad_bank_row"
    assert "Balance" in str(exc.value)


def test_revolut_identical_rows_in_one_second_get_distinct_ids():
    _, rows = parse_fixture("revolut_2026_09.csv")
    coffees = [r for r in rows if r.description == "Bar Roma"]
    assert len(coffees) == 2
    assert coffees[0].external_id != coffees[1].external_id
    assert len({r.external_id for r in rows}) == len(rows)


def test_revolut_id_is_stable_across_files_and_number_formats():
    _, sep = parse_fixture("revolut_2026_09.csv")
    _, oct_ = parse_fixture("revolut_2026_10.csv")
    # Oct repeats Sep's last three rows with `-1.2`/`1461.4`, a time without seconds,
    # a padded double-spaced description, `0` for `0.00` and `eur` for `EUR`.
    assert [r.external_id for r in oct_[:3]] == [r.external_id for r in sep[-3:]]
    assert len({r.external_id for r in sep} & {r.external_id for r in oct_}) == 3

    base = revolut_line(amount="-12.50", balance="100.00", description="Cafe Roma")
    variant = revolut_line(
        amount="-12.5",
        balance="100",
        description=" Cafe  Roma ",
        currency="eur",
        completed="2026-09-01 10:00",
    )
    _, a = parse_bytes((REVOLUT_HEADER + base).encode())
    _, b = parse_bytes((REVOLUT_HEADER + variant).encode())
    assert a[0].external_id == b[0].external_id
    assert a[0].external_id.startswith("rv:")


def test_revolut_id_changes_with_any_identifying_value():
    _, a = parse_bytes((REVOLUT_HEADER + revolut_line()).encode())
    for over in (
        {"amount": "-1.01"},
        {"balance": "100.01"},
        {"description": "Shop 2"},
        {"currency": "USD"},
        {"completed": "2026-09-01 10:00:01"},
    ):
        _, b = parse_bytes((REVOLUT_HEADER + revolut_line(**over)).encode())
        assert b[0].external_id != a[0].external_id, over


def test_revolut_header_in_another_order_parses_the_same():
    bank, reordered = parse_fixture("revolut_reordered.csv")
    _, original = parse_fixture("revolut_2026_09.csv")
    assert bank == "revolut"
    assert reordered == original


def test_wise_keeps_only_money_out_with_transferwise_id():
    bank, rows = parse_fixture("wise_2026_09.csv")
    assert bank == "wise"
    assert [r.external_id for r in rows] == [
        "wise:CARD-1001",
        "wise:TRANSFER-2001",
        "wise:CARD-1002",
        "wise:CONVERSION-3001",
    ]
    assert "wise:TRANSFER-2002" not in [r.external_id for r in rows]  # money in
    assert [r.amount_cents for r in rows] == [1820, 20000, 999, 5000]
    assert rows[0].merchant == "Lidl"
    assert [r.kind for r in rows] == ["CARD", "TRANSFER", "CARD", "CONVERSION"]


def test_wise_dates_parse_from_day_month_year():
    _, rows = parse_fixture("wise_2026_09.csv")
    assert rows[0].date == datetime.date(2026, 9, 3)
    assert rows[1].date == datetime.date(2026, 9, 5)


def test_impossible_date_is_a_bad_row():
    data = (
        b"TransferWise ID,Date,Amount,Currency,Description,Merchant\n"
        b"CARD-1,31-02-2026,-1.00,EUR,x,y\n"
    )
    with pytest.raises(LedgerError) as exc:
        parse_bytes(data)
    assert exc.value.code == "bad_bank_row"
    assert "line 2: Date '31-02-2026'" in str(exc.value)


def test_foreign_currency_row_keeps_its_currency():
    _, rv = parse_fixture("revolut_2026_09.csv")
    _, wi = parse_fixture("wise_2026_09.csv")
    assert [(r.currency, r.amount_cents) for r in rv if r.currency != "EUR"] == [("USD", 875)]
    assert [(r.currency, r.amount_cents) for r in wi if r.currency != "EUR"] == [("USD", 999)]


def test_unknown_header_names_missing_columns_for_both_banks():
    header, _ = read_csv((FIXTURES / "unknown.csv").read_bytes())
    with pytest.raises(LedgerError) as exc:
        detect(header)
    assert exc.value.code == "unknown_bank_format"
    detail = str(exc.value)
    assert "revolut missing: Type, Product, Started Date, Completed Date" in detail
    assert "wise missing: TransferWise ID, Currency, Description, Merchant" in detail


def test_each_bank_fixture_is_detected():
    for name, bank in [
        ("revolut_2026_09.csv", "revolut"),
        ("revolut_reordered.csv", "revolut"),
        ("wise_2026_09.csv", "wise"),
    ]:
        assert parse_fixture(name)[0] == bank


def test_empty_file_is_unknown_format():
    with pytest.raises(LedgerError) as exc:
        detect(read_csv(b"")[0])
    assert exc.value.code == "unknown_bank_format"


def test_non_utf8_file_is_unknown_format():
    with pytest.raises(LedgerError) as exc:
        read_csv("Type,Café\n".encode("utf-16"))
    assert exc.value.code == "unknown_bank_format"


def test_bom_and_crlf_are_accepted():
    data = ("﻿" + REVOLUT_HEADER + revolut_line() + "\n").replace("\n", "\r\n")
    bank, rows = parse_bytes(data.encode("utf-8"))
    assert bank == "revolut"
    assert [r.amount_cents for r in rows] == [100]


def test_banks_package_has_no_float_or_round():
    pattern = re.compile(r"\bfloat\(|\bround\(|\bDecimal\b")
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(BANKS_PKG.rglob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
