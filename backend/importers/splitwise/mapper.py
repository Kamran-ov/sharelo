"""Splitwise expense JSON -> rows for the ledger services. Pure: no DB, no network.

Amounts arrive as decimal strings ("12.5"); they are parsed to integer cents from the string
halves, never through float. A foreign-currency row is converted with the ECB rate for its day
(`rate_for`) and both sides are rescaled with `split_shares`, the one rounding rule.
"""

import datetime
import logging
import re
import zoneinfo
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ledger.errors import LedgerError
from ledger.models import SplitType
from ledger.services.rates import convert_with_rate
from ledger.services.splits import split_equal, split_shares

logger = logging.getLogger(__name__)

ROME = zoneinfo.ZoneInfo("Europe/Rome")
DESCRIPTION_MAX = 300
_AMOUNT_RE = re.compile(r"^(\d+)(?:\.(\d{1,2}))?$")

RateFor = Callable[[datetime.date, str], Decimal]


@dataclass(frozen=True)
class CentAdjustment:
    """One cent moved to close a Splitwise rounding gap.

    `delta` is the effect on that member's net compared with Splitwise's own figures: +1 for a
    cent added to what they paid (or taken from what they owe), -1 for the opposite.
    `currency` is the Splitwise row's currency, the one Splitwise's balance is kept in.
    """

    sw_id: int
    member_id: int
    delta: int
    currency: str


@dataclass
class MappedExpense:
    sw_id: int
    date: datetime.date
    utc_date: datetime.date
    sw_currency: str
    description: str
    notes: str
    category_id: int
    unknown_category: str | None
    split_type: str
    amount_cents: int
    payers: dict[int, int]
    splits: dict[int, int]
    original_amount_cents: int | None = None
    original_currency: str | None = None
    rate_used: Decimal | None = None
    adjustments: list[CentAdjustment] = field(default_factory=list)

    @property
    def external_id(self) -> str:
        return str(self.sw_id)


@dataclass
class MappedSettlement:
    sw_id: int
    date: datetime.date
    utc_date: datetime.date
    sw_currency: str
    from_member_id: int
    to_member_id: int
    amount_cents: int
    notes: str
    adjustments: list[CentAdjustment] = field(default_factory=list)

    @property
    def external_id(self) -> str:
        return str(self.sw_id)


@dataclass
class Skipped:
    sw_id: int
    reason: str  # deleted | zero_cost | existing

    @property
    def external_id(self) -> str:
        return str(self.sw_id)


Mapped = MappedExpense | MappedSettlement | Skipped


def parse_cents(value: Any) -> int:
    """ "12.5" -> 1250. Only non-negative decimals with at most two places are accepted."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise LedgerError("splitwise_amount", repr(value))
    text = str(value).strip()
    match = _AMOUNT_RE.match(text)
    if match is None:
        raise LedgerError("splitwise_amount", repr(value))
    units, fraction = match.group(1), (match.group(2) or "").ljust(2, "0")
    return int(units) * 100 + int(fraction)


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def rome_date(value: str) -> tuple[datetime.date, datetime.date]:
    """(Europe/Rome date, UTC date) of a Splitwise ISO instant."""
    try:
        moment = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LedgerError("splitwise_date", repr(value)) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.UTC)
    return moment.astimezone(ROME).date(), moment.astimezone(datetime.UTC).date()


class CategoryMap:
    """Splitwise category id -> our category id, matched by (parent name, child name).

    By pair, not by name alone: "Other" exists under six parents.
    """

    def __init__(self, by_sw_id: Mapping[int, int], fallback_id: int) -> None:
        self.by_sw_id = dict(by_sw_id)
        self.fallback_id = fallback_id

    @classmethod
    def build(
        cls,
        categories_json: Iterable[Mapping[str, Any]],
        ours: Iterable[tuple[int, str | None, str]],
    ) -> "CategoryMap":
        """`ours` is (id, parent name or None, name) for every category we have."""
        by_path = {(parent, name): cid for cid, parent, name in ours}
        fallback = by_path[("Uncategorized", "General")]
        by_sw_id: dict[int, int] = {}
        for top in categories_json:
            if (None, top["name"]) in by_path:
                by_sw_id[int(top["id"])] = by_path[(None, top["name"])]
            for sub in top.get("subcategories") or []:
                if (top["name"], sub["name"]) in by_path:
                    by_sw_id[int(sub["id"])] = by_path[(top["name"], sub["name"])]
        return cls(by_sw_id, fallback)

    def resolve(self, category: Mapping[str, Any] | None) -> tuple[int, str | None]:
        """(our id, the Splitwise name when it is unknown and the fallback was used)."""
        sw_id = (category or {}).get("id")
        if sw_id is not None and int(sw_id) in self.by_sw_id:
            return self.by_sw_id[int(sw_id)], None
        return self.fallback_id, str((category or {}).get("name") or sw_id)


def _shares(raw: Mapping[str, Any], key: str, user_map: Mapping[int, int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for entry in raw.get("users") or []:
        cents = parse_cents(entry.get(key) or "0")
        if cents == 0:
            continue
        user_id = int(entry.get("user_id") or entry["user"]["id"])
        if user_id not in user_map:
            raise LedgerError("unmapped_user", f"Splitwise user {user_id}")
        member_id = user_map[user_id]
        out[member_id] = out.get(member_id, 0) + cents
    return out


def _close_gap(
    shares: dict[int, int], cost: int, *, side: str, sw_id: int, currency: str
) -> list[CentAdjustment]:
    gap = cost - sum(shares.values())
    if gap == 0:
        return []
    if abs(gap) > 1 or not shares:
        raise LedgerError(
            "splitwise_sum_mismatch", f"{side} {format_cents(sum(shares.values()))} != cost"
        )
    member = min(shares)
    shares[member] += gap
    if shares[member] == 0:
        del shares[member]
    # A cent more paid raises the net; a cent more owed lowers it.
    delta = gap if side == "paid" else -gap
    logger.warning(
        "splitwise %s: %s side off by %+d cent, moved to member %s", sw_id, side, gap, member
    )
    return [CentAdjustment(sw_id=sw_id, member_id=member, delta=delta, currency=currency)]


def _split_type(payers: Mapping[int, int], splits: Mapping[int, int], amount: int) -> str:
    owers = set(splits)
    if len(payers) == 1 and len(owers) == 1:
        return SplitType.PERSONAL if owers == set(payers) else SplitType.FULL_FOR_OTHER
    if dict(splits) == split_equal(amount, owers):
        return SplitType.EQUAL
    return SplitType.EXACT


def map_expense(
    raw: Mapping[str, Any],
    *,
    user_map: Mapping[int, int],
    categories: CategoryMap,
    group_currency: str,
    rate_for: RateFor,
) -> Mapped:
    """One Splitwise expense -> a row to write, or why it is skipped. Raises LedgerError."""
    sw_id = int(raw["id"])
    if raw.get("deleted_at"):
        return Skipped(sw_id, "deleted")
    cost = parse_cents(raw.get("cost"))
    if cost == 0:
        return Skipped(sw_id, "zero_cost")
    day, utc_day = rome_date(raw.get("date"))
    currency = str(raw.get("currency_code") or "")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise LedgerError("invalid_currency", repr(currency))

    payers = _shares(raw, "paid_share", user_map)
    splits = _shares(raw, "owed_share", user_map)
    adjustments = _close_gap(payers, cost, side="paid", sw_id=sw_id, currency=currency)
    adjustments += _close_gap(splits, cost, side="owed", sw_id=sw_id, currency=currency)

    amount = cost
    rate: Decimal | None = None
    if currency != group_currency:
        rate = rate_for(day, currency)
        amount = convert_with_rate(cost, rate)
        if amount <= 0:
            raise LedgerError("converted_to_zero", f"{format_cents(cost)} {currency}")
        payers = split_shares(amount, payers)
        splits = split_shares(amount, splits)

    if raw.get("payment"):
        if len(payers) != 1 or len(splits) != 1 or set(payers) == set(splits):
            raise LedgerError(
                "splitwise_payment_shape",
                f"{len(payers)} payer(s), {len(splits)} receiver(s)",
            )
        notes = "" if rate is None else f"Splitwise: {format_cents(cost)} {currency}"
        return MappedSettlement(
            sw_id=sw_id,
            date=day,
            utc_date=utc_day,
            sw_currency=currency,
            from_member_id=next(iter(payers)),
            to_member_id=next(iter(splits)),
            amount_cents=amount,
            notes=notes,
            adjustments=adjustments,
        )

    category_id, unknown = categories.resolve(raw.get("category"))
    return MappedExpense(
        sw_id=sw_id,
        date=day,
        utc_date=utc_day,
        sw_currency=currency,
        description=str(raw.get("description") or "")[:DESCRIPTION_MAX],
        notes=str(raw.get("details") or ""),
        category_id=category_id,
        unknown_category=unknown,
        split_type=_split_type(payers, splits, amount),
        amount_cents=amount,
        payers=payers,
        splits=splits,
        original_amount_cents=cost if rate is not None else None,
        original_currency=currency if rate is not None else None,
        rate_used=rate,
        adjustments=adjustments,
    )
