"""Exchange rates and conversion into a group's currency.

Units: `ExchangeRate.rate_to_eur` is units of that currency per 1 EUR (USD 1.10 means EUR 1 =
USD 1.10). `rate(date, a, b)` is units of `b` per 1 `a`, derived through EUR. An expense's
`rate_used` has the same direction (group units per 1 original unit), so
`amount_cents = original_amount_cents * rate_used`, rounded half-even to a whole cent.

Rates are the only Decimals here; amounts go in and out as `int` cents. Weekend and holiday
dates use the latest earlier rate, but never one older than MAX_RATE_AGE_DAYS.
"""

import bisect
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
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


def rate_resolver(
    from_currency: str, to_currency: str, date_from: datetime.date, date_to: datetime.date
) -> Callable[[datetime.date], Decimal]:
    """`rate()` for many dates in at most one query; same rule, same quantisation.

    A date outside [date_from, date_to] is a caller bug, not a missing rate, so the window
    is the contract: rows are loaded for [date_from - MAX_RATE_AGE_DAYS, date_to].
    """
    needed = {c for c in (from_currency, to_currency) if c != "EUR"}
    if from_currency == to_currency or not needed:
        return lambda date: Decimal(1)
    window_start = date_from - datetime.timedelta(days=MAX_RATE_AGE_DAYS)
    rows = (
        ExchangeRate.objects.filter(currency__in=needed, date__gte=window_start, date__lte=date_to)
        .order_by("date")
        .values_list("currency", "date", "rate_to_eur")
    )
    dates: dict[str, list[datetime.date]] = {c: [] for c in needed}
    values: dict[str, list[Decimal]] = {c: [] for c in needed}
    for currency, date, rate_to_eur in rows:
        dates[currency].append(date)
        values[currency].append(rate_to_eur)

    def eur_per_unit(currency: str, date: datetime.date) -> Decimal:
        if currency == "EUR":
            return Decimal(1)
        i = bisect.bisect_right(dates[currency], date) - 1
        if i < 0 or dates[currency][i] < date - datetime.timedelta(days=MAX_RATE_AGE_DAYS):
            raise LedgerError("no_rate", f"{currency} on {date}")
        return 1 / values[currency][i]

    def resolve(date: datetime.date) -> Decimal:
        return quantize_rate(eur_per_unit(from_currency, date) / eur_per_unit(to_currency, date))

    return resolve


def range_converter(
    from_currency: str, to_currency: str, date_from: datetime.date, date_to: datetime.date
) -> Callable[[datetime.date, int], int]:
    """`convert()` for many (date, cents) pairs; rounds through `convert_with_rate` like it."""
    resolve = rate_resolver(from_currency, to_currency, date_from, date_to)
    return lambda date, cents: convert_with_rate(cents, resolve(date))


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
