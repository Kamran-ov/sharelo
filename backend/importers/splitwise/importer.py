"""Splitwise group -> one of our groups. The service layer of the import (rule 8).

Order matters and is the safety of the import: fetch everything, check the user map, map every
row collecting every error, look up ids already imported, and only then write, all inside one
transaction. A refusal at any step writes nothing.
"""

import datetime
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ledger.errors import LedgerError
from ledger.models import (
    Category,
    Expense,
    ExpensePayer,
    ExpenseSplit,
    Group,
    ImportBatch,
    Member,
    Settlement,
    Source,
)
from ledger.services import rates
from ledger.services.balances import record_settlement
from ledger.services.expenses import create_expense

from .client import SplitwiseClient
from .mapper import (
    CategoryMap,
    CentAdjustment,
    Mapped,
    MappedExpense,
    MappedSettlement,
    Skipped,
    format_cents,
    map_expense,
    parse_cents,
)

SOURCE = Source.SPLITWISE


@dataclass
class ImportResult:
    sw_group_id: int
    sw_group_name: str
    dry_run: bool
    seen: int = 0
    rows: list[Mapped] = field(default_factory=list)
    # Refusals; at most one kind is non-empty, and any of them means nothing was written.
    unmapped_users: list[tuple[int, str]] = field(default_factory=list)
    errors: list[tuple[int, str, str]] = field(default_factory=list)
    other_groups: dict[int, int] = field(default_factory=dict)
    batch: ImportBatch | None = None
    balance_lines: list[str] = field(default_factory=list)
    balance_mismatches: int = 0

    @property
    def refused(self) -> bool:
        return bool(self.unmapped_users or self.errors or self.other_groups)

    @property
    def to_write(self) -> list[MappedExpense | MappedSettlement]:
        return [r for r in self.rows if not isinstance(r, Skipped)]

    @property
    def skipped(self) -> Counter:
        return Counter(r.reason for r in self.rows if isinstance(r, Skipped))

    @property
    def expenses(self) -> list[MappedExpense]:
        return [r for r in self.rows if isinstance(r, MappedExpense)]

    @property
    def settlements(self) -> list[MappedSettlement]:
        return [r for r in self.rows if isinstance(r, MappedSettlement)]

    @property
    def adjustments(self) -> list[CentAdjustment]:
        return [a for r in self.to_write for a in r.adjustments]

    @property
    def unknown_categories(self) -> list[tuple[int, str]]:
        return [(r.sw_id, r.unknown_category) for r in self.expenses if r.unknown_category]

    @property
    def date_shifted(self) -> list[MappedExpense | MappedSettlement]:
        return [r for r in self.to_write if r.date != r.utc_date]


def parse_signed_cents(value: Any) -> int:
    text = str(value).strip()
    if text.startswith("-"):
        return -parse_cents(text[1:])
    return parse_cents(text)


def _user_name(user: Mapping[str, Any]) -> str:
    return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p) or "?"


def _check_map(group: Group, user_map: Mapping[int, int]) -> None:
    targets = list(user_map.values())
    if len(set(targets)) != len(targets):
        raise LedgerError("map_not_one_to_one", "two Splitwise users map to one member")
    in_group = set(Member.objects.filter(group=group, id__in=targets).values_list("id", flat=True))
    if in_group != set(targets):
        raise LedgerError("member_not_in_group", f"ids {sorted(set(targets) - in_group)}")


def _unmapped_users(
    sw_group: Mapping[str, Any], expenses: Iterable[Mapping[str, Any]], user_map: Mapping[int, int]
) -> list[tuple[int, str]]:
    names = {int(m["id"]): _user_name(m) for m in sw_group.get("members") or []}
    missing: dict[int, str] = {}
    for raw in expenses:
        if raw.get("deleted_at"):
            continue
        for entry in raw.get("users") or []:
            user_id = int(entry.get("user_id") or entry["user"]["id"])
            if user_id in user_map or user_id in missing:
                continue
            shares = (entry.get("paid_share") or "0", entry.get("owed_share") or "0")
            if any(s not in ("0", "0.0", "0.00") for s in shares):
                # People who left the group are not in its member list; their expense entry
                # still carries the name.
                missing[user_id] = names.get(user_id) or _user_name(entry.get("user") or {})
    return sorted(missing.items())


def _existing(ids: list[str]) -> dict[str, int]:
    """external id -> group id, for every Splitwise row we already hold (deleted ones too)."""
    out: dict[str, int] = {}
    for model in (Expense, Settlement):
        rows = model.all_objects.filter(source=SOURCE, external_id__in=ids)
        out.update(dict(rows.values_list("external_id", "group_id")))
    return out


def import_group(
    client: SplitwiseClient,
    *,
    splitwise_group_id: int,
    group: Group,
    user_map: Mapping[int, int],
    dry_run: bool,
) -> ImportResult:
    sw_group = client.get_group(splitwise_group_id)
    categories_json = client.get_categories()
    raw_expenses = client.get_expenses(splitwise_group_id)
    result = ImportResult(
        sw_group_id=splitwise_group_id,
        sw_group_name=str(sw_group.get("name") or ""),
        dry_run=dry_run,
        seen=len(raw_expenses),
    )

    _check_map(group, user_map)
    result.unmapped_users = _unmapped_users(sw_group, raw_expenses, user_map)
    if result.unmapped_users:
        return result

    categories = CategoryMap.build(
        categories_json, Category.objects.values_list("id", "parent__name", "name")
    )

    def rate_for(day: datetime.date, currency: str):
        return rates.rate(day, currency, group.currency)

    for raw in raw_expenses:
        try:
            result.rows.append(
                map_expense(
                    raw,
                    user_map=user_map,
                    categories=categories,
                    group_currency=group.currency,
                    rate_for=rate_for,
                )
            )
        except LedgerError as exc:
            result.errors.append((int(raw.get("id") or 0), exc.code, str(exc)))
    if result.errors:
        return result

    # Every Splitwise row we already hold is skipped: this lookup is what makes a re-run create
    # nothing. A row held by another group stops the run instead of reading as "created 0".
    existing = _existing([r.external_id for r in result.to_write])
    for group_id in existing.values():
        if group_id != group.pk:
            result.other_groups[group_id] = result.other_groups.get(group_id, 0) + 1
    if result.other_groups:
        return result
    currency_by_sw_id = {r.sw_id: r.sw_currency for r in result.to_write}
    adjustments = result.adjustments
    result.rows = [
        Skipped(r.sw_id, "existing")
        if not isinstance(r, Skipped) and r.external_id in existing
        else r
        for r in result.rows
    ]

    if dry_run:
        return result

    _write(result, group)
    result.balance_lines, result.balance_mismatches = balance_check(
        group, sw_group, currency_by_sw_id, adjustments, user_map
    )
    return result


def _write(result: ImportResult, group: Group) -> None:
    categories = Category.objects.in_bulk()
    members = Member.objects.filter(group=group).in_bulk()
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            group=group,
            source=SOURCE,
            label=f"splitwise group {result.sw_group_id} {result.sw_group_name}"[:200],
        )
        for row in result.to_write:
            if isinstance(row, MappedExpense):
                create_expense(
                    group,
                    description=row.description,
                    amount_cents=row.amount_cents,
                    currency=group.currency,
                    date=row.date,
                    category=categories[row.category_id],
                    payers=row.payers,
                    splits=row.splits,
                    split_type=row.split_type,
                    source=SOURCE,
                    external_id=row.external_id,
                    original_amount_cents=row.original_amount_cents,
                    original_currency=row.original_currency,
                    rate_used=row.rate_used,
                    import_batch=batch,
                    notes=row.notes,
                )
            else:
                record_settlement(
                    group,
                    members[row.from_member_id],
                    members[row.to_member_id],
                    row.amount_cents,
                    row.date,
                    row.notes,
                    source=SOURCE,
                    external_id=row.external_id,
                    import_batch=batch,
                )
        batch.rows_seen = result.seen
        batch.rows_created = len(result.to_write)
        batch.rows_skipped = sum(result.skipped.values())
        if batch.rows_seen != batch.rows_created + batch.rows_skipped:
            raise LedgerError("import_count_mismatch", f"{batch.rows_seen} seen")
        batch.finished_at = timezone.now()
        batch.save()
    result.batch = batch


def _imported_nets(group: Group, external_ids: list[str]) -> dict[int, int]:
    """Per member net over this group's live Splitwise rows with these ids."""
    nets: dict[int, int] = {}

    def add(rows, key: str, field_name: str, sign: int) -> None:
        for r in rows.values(key).annotate(total=Sum(field_name)):
            nets[r[key]] = nets.get(r[key], 0) + sign * r["total"]

    live = {
        "expense__group": group,
        "expense__source": SOURCE,
        "expense__external_id__in": external_ids,
        "expense__deleted_at__isnull": True,
    }
    add(ExpensePayer.objects.filter(**live), "member_id", "paid_cents", 1)
    add(ExpenseSplit.objects.filter(**live), "member_id", "owed_cents", -1)
    settlements = Settlement.objects.filter(
        group=group, source=SOURCE, external_id__in=external_ids
    )
    add(settlements, "from_member_id", "amount_cents", 1)
    add(settlements, "to_member_id", "amount_cents", -1)
    return nets


def _signed(cents: int) -> str:
    return ("+" if cents > 0 else "") + format_cents(cents)


def balance_check(
    group: Group,
    sw_group: Mapping[str, Any],
    currency_by_sw_id: Mapping[int, str],
    adjustments: Iterable[CentAdjustment],
    user_map: Mapping[int, int],
) -> tuple[list[str], int]:
    """Our imported nets against Splitwise's member balances, one currency at a time.

    The group-currency line is exact: Splitwise's balance plus the member's cent-adjustment
    deltas (Splitwise keeps its unadjusted shares) must equal ours, otherwise ✗. Foreign
    currencies are converted on our side, so they are printed and labelled, never compared.
    Returns (lines, number of ✗).
    """
    names = dict(Member.objects.filter(group=group).values_list("id", "display_name"))
    ids_by_currency: dict[str, list[str]] = {}
    for sw_id, currency in currency_by_sw_id.items():
        ids_by_currency.setdefault(currency, []).append(str(sw_id))
    delta: dict[int, int] = {}
    delta_ids: dict[int, list[int]] = {}
    for adj in adjustments:
        if adj.currency == group.currency:
            delta[adj.member_id] = delta.get(adj.member_id, 0) + adj.delta
            delta_ids.setdefault(adj.member_id, []).append(adj.sw_id)

    sw_balances: dict[int, dict[str, int]] = {}  # our member id -> currency -> cents
    unmapped_balances: list[tuple[int, str, str, int]] = []
    for m in sw_group.get("members") or []:
        for entry in m.get("balance") or []:
            cents = parse_signed_cents(entry.get("amount") or "0")
            currency = str(entry.get("currency_code"))
            if int(m["id"]) in user_map:
                sw_balances.setdefault(user_map[int(m["id"])], {})[currency] = cents
            elif cents:
                unmapped_balances.append((int(m["id"]), _user_name(m), currency, cents))

    lines: list[str] = []
    mismatches = 0
    gc = group.currency
    ours = _imported_nets(group, ids_by_currency.get(gc, []))
    for member_id in sorted(set(user_map.values())):
        sw = sw_balances.get(member_id, {}).get(gc, 0)
        mine = ours.get(member_id, 0)
        line = f"{gc}  {names[member_id]}  splitwise {_signed(sw)}  ours {_signed(mine)}"
        if mine == sw:
            pass
        elif mine == sw + delta.get(member_id, 0):
            ids = ", ".join(str(i) for i in sorted(delta_ids[member_id]))
            line += f"  = after cent adjustment (sw ids {ids})"
        else:
            line += "  ✗"
            mismatches += 1
        lines.append(line)
    for sw_user, name, currency, cents in unmapped_balances:
        lines.append(f"{currency}  {name} (Splitwise {sw_user}, not mapped)  {_signed(cents)}  ✗")
        mismatches += 1

    foreign = sorted(({c for b in sw_balances.values() for c in b} | set(ids_by_currency)) - {gc})
    for currency in foreign:
        ours_foreign = _imported_nets(group, ids_by_currency.get(currency, []))
        for member_id in sorted(set(user_map.values())):
            sw = sw_balances.get(member_id, {}).get(currency, 0)
            mine = ours_foreign.get(member_id, 0)
            lines.append(
                f"{currency}  {names[member_id]}  Splitwise {_signed(sw)} {currency}; "
                f"ours {_signed(mine)} {gc} at ECB rates, not compared"
            )
    return lines, mismatches
