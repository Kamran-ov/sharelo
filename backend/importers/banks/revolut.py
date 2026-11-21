"""Revolut personal-account CSV → money-out BankRows."""

import datetime
import hashlib

from importers.banks.common import BadRows, BankRow, CsvLine, collapse_spaces, parse_cents

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def _parse_completed(text: str) -> datetime.datetime:
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(text)


def row_id(
    completed: datetime.datetime, amount: int, currency: str, description: str, balance: int
) -> str:
    # FROZEN recipe (docs/adr/002-bank-row-ids.md): changing any part re-stages every Revolut
    # row ever imported. Only canonical parsed values go in, never raw text.
    parts = [
        completed.strftime("%Y-%m-%dT%H:%M:%S"),
        str(amount),
        currency.strip().upper(),
        collapse_spaces(description),
        str(balance),
    ]
    return "rv:" + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def parse(lines: list[CsvLine]) -> list[BankRow]:
    bad = BadRows()
    rows: list[BankRow] = []
    for line in lines:
        v = line.values
        if v["State"].strip() != "COMPLETED":
            continue
        try:
            amount = parse_cents(v["Amount"])
        except ValueError:
            bad.add(line, "Amount", v["Amount"])
            continue
        fee_text = v["Fee"].strip() or "0"
        try:
            fee = parse_cents(fee_text)
        except ValueError:
            bad.add(line, "Fee", v["Fee"])
            continue
        out = fee - amount
        if amount > 0 or out <= 0:
            continue  # money in (top-up, refund) or nothing moved
        try:
            completed = _parse_completed(v["Completed Date"])
        except ValueError:
            bad.add(line, "Completed Date", v["Completed Date"])
            continue
        try:
            balance = parse_cents(v["Balance"])
        except ValueError:
            # An empty balance would make the id unstable between exports.
            bad.add(line, "Balance", v["Balance"])
            continue
        currency = v["Currency"].strip().upper()
        if len(currency) != 3:
            bad.add(line, "Currency", v["Currency"])
            continue
        description = collapse_spaces(v["Description"])
        rows.append(
            BankRow(
                date=completed.date(),
                amount_cents=out,
                currency=currency,
                description=description,
                merchant="",
                external_id=row_id(completed, amount, currency, description, balance),
                raw=dict(v),
                kind=v["Type"].strip(),
            )
        )
    bad.raise_if_any()
    return rows
