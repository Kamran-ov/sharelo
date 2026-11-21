"""Wise statement CSV → money-out BankRows.

`Amount` is the balance movement, fees included (to be confirmed on a real export: see the
production checks in docs/specs/020.md), so no fee column is added.
"""

import datetime

from importers.banks.common import BadRows, BankRow, CsvLine, collapse_spaces, parse_cents

_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d")


def _parse_date(text: str) -> datetime.date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def row_id(transferwise_id: str) -> str:
    # FROZEN recipe (docs/adr/002-bank-row-ids.md).
    return "wise:" + transferwise_id.strip()


def parse(lines: list[CsvLine]) -> list[BankRow]:
    bad = BadRows()
    rows: list[BankRow] = []
    for line in lines:
        v = line.values
        try:
            amount = parse_cents(v["Amount"])
        except ValueError:
            bad.add(line, "Amount", v["Amount"])
            continue
        if amount >= 0:
            continue  # money in
        try:
            day = _parse_date(v["Date"])
        except ValueError:
            bad.add(line, "Date", v["Date"])
            continue
        tw_id = v["TransferWise ID"].strip()
        if not tw_id:
            bad.add(line, "TransferWise ID", v["TransferWise ID"])
            continue
        currency = v["Currency"].strip().upper()
        if len(currency) != 3:
            bad.add(line, "Currency", v["Currency"])
            continue
        rows.append(
            BankRow(
                date=day,
                amount_cents=-amount,
                currency=currency,
                description=collapse_spaces(v["Description"]),
                merchant=collapse_spaces(v["Merchant"]),
                external_id=row_id(tw_id),
                raw=dict(v),
                kind=tw_id.split("-", 1)[0] if "-" in tw_id else "",
            )
        )
    bad.raise_if_any()
    return rows
