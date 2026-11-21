"""Shared pieces of the bank CSV parsers. Pure: no DB, no network.

Money is parsed from the text into integer cents with integer arithmetic only; a grep test
keeps binary floating point and decimal types out of this package.
"""

import csv
import datetime
import io
import re
from dataclasses import dataclass, field

from ledger.errors import LedgerError

REVOLUT = "revolut"
WISE = "wise"

REQUIRED: dict[str, list[str]] = {
    REVOLUT: [
        "Type",
        "Product",
        "Started Date",
        "Completed Date",
        "Description",
        "Amount",
        "Fee",
        "Currency",
        "State",
        "Balance",
    ],
    WISE: ["TransferWise ID", "Date", "Amount", "Currency", "Description", "Merchant"],
}

_AMOUNT = re.compile(r"^(-?)(\d+)(?:\.(\d{1,2}))?$")


@dataclass(frozen=True)
class BankRow:
    date: datetime.date
    amount_cents: int  # always positive: money out of the account
    currency: str
    description: str
    merchant: str
    external_id: str
    raw: dict[str, str] = field(compare=False)
    kind: str = field(default="", compare=False)  # Revolut Type / Wise id prefix, for reports


@dataclass(frozen=True)
class CsvLine:
    number: int  # 1-based line number in the file, for error messages
    values: dict[str, str]


def parse_cents(text: str) -> int:
    """`"-12.5"` → -1250. Anything that is not plain `[-]digits[.d[d]]` raises ValueError."""
    match = _AMOUNT.match(text.strip())
    if match is None:
        raise ValueError(text)
    sign, whole, frac = match.groups()
    cents = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -cents if sign else cents


def read_csv(data: bytes) -> tuple[list[str], list[CsvLine]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LedgerError("unknown_bank_format", "file is not UTF-8 text") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    header: list[str] = []
    lines: list[CsvLine] = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue
        if not header:
            header = [c.strip() for c in cells]
            continue
        values = {name: (cells[i] if i < len(cells) else "") for i, name in enumerate(header)}
        lines.append(CsvLine(reader.line_num, values))
    return header, lines


def detect(header: list[str]) -> str:
    present = set(header)
    missing = {bank: [c for c in cols if c not in present] for bank, cols in REQUIRED.items()}
    for bank, cols in missing.items():
        if not cols:
            return bank
    detail = "; ".join(f"{bank} missing: {', '.join(cols)}" for bank, cols in missing.items())
    raise LedgerError("unknown_bank_format", detail)


class BadRows:
    """Collects every unreadable row, so one error lists them all."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, line: CsvLine, column: str, value: str) -> None:
        self.problems.append(f"line {line.number}: {column} {value!r}")

    def raise_if_any(self) -> None:
        if self.problems:
            raise LedgerError("bad_bank_row", "; ".join(self.problems))


def collapse_spaces(text: str) -> str:
    return " ".join(text.split())
