"""Exchange rates and conversion into a group's currency.

Units: `ExchangeRate.rate_to_eur` is units of that currency per 1 EUR (USD 1.10 means EUR 1 =
USD 1.10). `rate(date, a, b)` is units of `b` per 1 `a`, derived through EUR. An expense's
`rate_used` has the same direction (group units per 1 original unit), so
`amount_cents = original_amount_cents * rate_used`, rounded half-even to a whole cent.

Rates are the only Decimals here; amounts go in and out as `int` cents. Weekend and holiday
dates use the latest earlier rate, but never one older than MAX_RATE_AGE_DAYS.
"""

import datetime
import urllib.request
import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_EVEN, Decimal

from django.db import transaction

from ledger.errors import LedgerError
from ledger.models import ExchangeRate, Group

MAX_RATE_AGE_DAYS = 7
RATE_QUANTUM = Decimal("0.00000001")
_ECB_BASE = "https://www.ecb.europa.eu/stats/eurofxref/"


def quantize_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_QUANTUM, rounding=ROUND_HALF_EVEN)


def convert_with_rate(amount_cents: int, rate_value: Decimal) -> int:
    scaled = Decimal(amount_cents) * quantize_rate(rate_value)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _eur_per_unit(currency: str, date: datetime.date) -> Decimal:
    """EUR per 1 unit of `currency` from the latest rate within the allowed age."""
    if currency == "EUR":
        return Decimal(1)
    row = (
        ExchangeRate.objects.filter(
            currency=currency,
            date__lte=date,
            date__gte=date - datetime.timedelta(days=MAX_RATE_AGE_DAYS),
        )
        .order_by("-date")
        .first()
    )
    if row is None:
        raise LedgerError("no_rate", f"{currency} on {date}")
    return 1 / row.rate_to_eur


def rate(date: datetime.date, from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        return Decimal(1)
    return quantize_rate(_eur_per_unit(from_currency, date) / _eur_per_unit(to_currency, date))


def convert(amount_cents: int, date: datetime.date, from_currency: str, to_currency: str) -> int:
    return convert_with_rate(amount_cents, rate(date, from_currency, to_currency))


def resolve_foreign_amount(
    group: Group,
    date: datetime.date,
    original_amount_cents: int,
    original_currency: str,
    rate_used: Decimal | None = None,
) -> tuple[int, Decimal]:
    """Converted `amount_cents` and the stored rate. An explicit `rate_used` overrides lookup."""
    if original_currency == group.currency:
        return original_amount_cents, Decimal(1)
    used = quantize_rate(rate_used) if rate_used is not None else None
    if used is None:
        used = rate(date, original_currency, group.currency)
    return convert_with_rate(original_amount_cents, used), used


def parse_ecb_xml(text: str) -> dict[datetime.date, dict[str, Decimal]]:
    out: dict[datetime.date, dict[str, Decimal]] = {}
    for day in ET.fromstring(text).iter():
        if not day.tag.endswith("Cube") or "time" not in day.attrib:
            continue
        date = datetime.date.fromisoformat(day.attrib["time"])
        out[date] = {
            c.attrib["currency"]: Decimal(c.attrib["rate"]) for c in day if "currency" in c.attrib
        }
    return out


def _ecb_url(since: datetime.date | None, today: datetime.date) -> str:
    if since is None:
        return _ECB_BASE + "eurofxref-daily.xml"
    if since >= today - datetime.timedelta(days=90):
        return _ECB_BASE + "eurofxref-hist-90d.xml"
    return _ECB_BASE + "eurofxref-hist.xml"


def _download(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed ECB https URLs
        return response.read().decode("utf-8")


def fetch_ecb_rates(since: datetime.date | None = None) -> int:
    """Upsert ECB rates (all of them, or those on/after `since`); returns rows written."""
    parsed = parse_ecb_xml(_download(_ecb_url(since, datetime.date.today())))
    rows = [
        ExchangeRate(date=d, currency=cur, rate_to_eur=value)
        for d, rates in parsed.items()
        if since is None or d >= since
        for cur, value in rates.items()
    ]
    with transaction.atomic():
        ExchangeRate.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["date", "currency"],
            update_fields=["rate_to_eur"],
        )
    return len(rows)
