"""The bank review list (021): suggest a category and split per row, turn a tap into an expense.

The only writer of a row's decision. Every decision is one transaction: the row, its expense
and an optional shop rule are written together or not at all.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from importers.banks import shop_rules
from importers.models import BankRowStatus, PendingBankRow, ShopRule
from ledger.errors import LedgerError
from ledger.models import Category, CategoryDefault, Expense, Group, Member, SplitType
from ledger.services.expenses import (
    create_expense_from_preset,
    delete_expense,
    revive_expense_from_preset,
)
from ledger.services.splits import split_for_preset

SHARED = "shared"
PERSONAL = "personal"
SKIP = "skip"
DECISIONS = (SHARED, PERSONAL, SKIP)

Split = tuple[str, dict[str, Any]]


@dataclass
class Suggestion:
    category: Category
    decision: str  # which button is highlighted: shared | personal
    preset: str  # the split the Shared button uses; never `personal`
    params: dict[str, Any] = field(default_factory=dict)
    basis: str = "default"  # rule | history | default
    rule: ShopRule | None = None


@dataclass
class Resolved:
    row: PendingBankRow
    expense: Expense | None
    rule: ShopRule | None


def default_category() -> Category:
    return Category.objects.get(name="General", parent__name="Uncategorized")


def leaf_categories() -> list[Category]:
    return list(Category.objects.filter(children__isnull=True).order_by("id"))


def _valid(group_member_ids: list[int], payer_id: int, preset: str, params: Mapping) -> bool:
    try:
        split_for_preset(preset, 100, group_member_ids, payer_id, params)
    except LedgerError:
        return False
    return True


def _shared(split_type: str, params: Mapping[str, Any]) -> Split:
    if split_type == SplitType.PERSONAL:
        return SplitType.EQUAL.value, {}
    return split_type, dict(params)


def shared_split_for(group: Group, category: Category, payer_id: int | None = None) -> Split:
    """The Shared split for a category: its default, `equal` when that is personal or unusable.

    The one place this rule lives; `shared_splits_for_group` applies it to every category.
    """
    return shared_splits_for_group(group, payer_id, [category])[category.id]


def shared_splits_for_group(
    group: Group, payer_id: int | None = None, categories: Iterable[Category] | None = None
) -> dict[int, Split]:
    cats = list(categories) if categories is not None else leaf_categories()
    member_ids = sorted(group.members.values_list("id", flat=True))
    payer = payer_id if payer_id is not None else (member_ids[0] if member_ids else 0)
    defaults = {
        d.category_id: (d.split_type, d.split_params)
        for d in CategoryDefault.objects.filter(group=group, category__in=cats)
    }
    out: dict[int, Split] = {}
    for c in cats:
        preset, params = _shared(*defaults.get(c.id, (SplitType.EQUAL.value, {})))
        # A default saved before the members changed can hold stale params: never offer a split
        # the tap would refuse.
        if not _valid(member_ids, payer, preset, params):
            preset, params = SplitType.EQUAL.value, {}
        out[c.id] = (preset, params)
    return out


def _history(group: Group) -> dict[str, PendingBankRow]:
    """Latest decided row per shop key: preset/params from the row, category from its expense."""
    rows = (
        PendingBankRow.objects.filter(
            group=group,
            status__in=[BankRowStatus.SHARED, BankRowStatus.PERSONAL],
            expense__isnull=False,
            expense__deleted_at__isnull=True,
        )
        .select_related("expense__category")
        .order_by("-expense__updated_at", "-id")
    )
    latest: dict[str, PendingBankRow] = {}
    for r in rows:
        latest.setdefault(shop_rules.match_key(shop_rules.row_text(r)), r)
    return latest


def suggest_many(group: Group, rows: Iterable[PendingBankRow]) -> dict[int, Suggestion]:
    rows = list(rows)
    if not rows:
        return {}
    rules = list(ShopRule.objects.filter(group=group).select_related("category"))
    history = _history(group)
    member_ids = sorted(group.members.values_list("id", flat=True))
    general = default_category()
    split_cache: dict[tuple[int, int], Split] = {}

    def category_split(category: Category, payer_id: int) -> Split:
        key = (category.id, payer_id)
        if key not in split_cache:
            split_cache[key] = shared_split_for(group, category, payer_id)
        return split_cache[key]

    out: dict[int, Suggestion] = {}
    for row in rows:
        payer_id = row.uploaded_by_id
        rule = shop_rules.find_rule(rules, row)
        past = history.get(shop_rules.match_key(shop_rules.row_text(row)))
        if rule is not None:
            category, basis = rule.category, "rule"
            decided, params = rule.preset, rule.params
        elif past is not None:
            category, basis = past.expense.category, "history"
            decided, params = past.split_preset, past.split_params
        else:
            category, basis = general, "default"
            decided, params = category_split(general, payer_id)
        decision = PERSONAL if decided == SplitType.PERSONAL else SHARED
        if decided == SplitType.PERSONAL or not _valid(member_ids, payer_id, decided, params):
            preset, params = category_split(category, payer_id)
        else:
            preset, params = decided, dict(params)
        out[row.id] = Suggestion(category, decision, preset, params, basis, rule)
    return out


def suggest(row: PendingBankRow) -> Suggestion:
    return suggest_many(row.group, [row])[row.id]


def _locked(row: PendingBankRow) -> PendingBankRow:
    # of=self: the expense join is an outer join, which Postgres refuses to lock.
    rows = PendingBankRow.objects.select_for_update(of=("self",)).select_related("expense")
    return rows.get(pk=row.pk)


def _own_row(row: PendingBankRow, member: Member) -> None:
    # A statement is personal (020): only its uploader reads or decides its rows.
    if row.uploaded_by_id != member.id or row.group_id != member.group_id:
        raise LedgerError("not_found")


def resolve_row(
    row: PendingBankRow,
    member: Member,
    decision: str,
    *,
    category: Category | None = None,
    preset: str | None = None,
    params: Mapping[str, Any] | None = None,
    payer: Member | None = None,
    remember: bool = False,
) -> Resolved:
    _own_row(row, member)
    if decision not in DECISIONS:
        raise LedgerError("invalid_request", f"decision must be one of {', '.join(DECISIONS)}")
    if remember and decision == SKIP:
        raise LedgerError("remember_needs_category", "a skipped row has nothing to remember")
    group = row.group
    payer = payer or row.uploaded_by
    if payer.group_id != group.id:
        raise LedgerError("member_not_in_group", "the payer must belong to the group")

    with transaction.atomic():
        row = _locked(row)
        if row.status != BankRowStatus.PENDING:
            raise LedgerError("row_already_resolved", f"row {row.pk} is {row.status}")
        if decision == SKIP:
            row.status = BankRowStatus.SKIPPED
            row.save(update_fields=["status"])
            return Resolved(row, None, None)

        hint = suggest(row)
        category = category or hint.category
        if decision == PERSONAL:
            preset, params = SplitType.PERSONAL.value, {}
        elif preset is None:
            # Same rule as the page's rowChoice: the suggested category keeps the suggested
            # split, any other category takes its own Shared split.
            if category.id == hint.category.id:
                preset, params = hint.preset, hint.params
            else:
                preset, params = shared_split_for(group, category, payer.id)
        elif preset == SplitType.PERSONAL:
            raise LedgerError("shared_needs_split", "Shared needs a split other than personal")
        params = dict(params or {})

        amount: dict[str, Any]
        if row.currency == group.currency:
            amount = {"amount_cents": row.amount_cents}
        else:
            amount = {"original_amount_cents": row.amount_cents, "original_currency": row.currency}
        values = {
            "preset": preset,
            "payer_id": payer.id,
            "params": params,
            "description": shop_rules.row_text(row)[:300],
            "date": row.date,
            "category": category,
            **amount,
        }
        if row.expense is not None:
            expense = revive_expense_from_preset(row.expense, **values)
        else:
            expense = create_expense_from_preset(
                group,
                currency=group.currency,
                source=row.source,
                external_id=row.external_id,
                import_batch=row.import_batch,
                **values,
            )
        row.status = BankRowStatus.SHARED if decision == SHARED else BankRowStatus.PERSONAL
        row.expense = expense
        row.split_preset = preset
        row.split_params = params
        row.save(update_fields=["status", "expense", "split_preset", "split_params"])

        rule = None
        if remember:
            rule = shop_rules.save_rule(
                group,
                member,
                match_text=shop_rules.row_text(row),
                category=category,
                preset=preset,
                params=params,
                upsert=True,
            )
        elif hint.rule is not None:
            rule = hint.rule
        if rule is not None:
            shop_rules.touch(rule)
    return Resolved(row, expense, rule)


def undo_row(row: PendingBankRow, member: Member) -> PendingBankRow:
    _own_row(row, member)
    with transaction.atomic():
        row = _locked(row)
        if row.status == BankRowStatus.PENDING:
            raise LedgerError("row_not_resolved", f"row {row.pk} has no decision to undo")
        if row.expense is not None:
            delete_expense(row.expense)
        row.status = BankRowStatus.PENDING
        row.split_preset = ""
        row.split_params = {}
        row.save(update_fields=["status", "split_preset", "split_params"])
    return row
