"""Shop rules: merchant text → category and split, for the bank review list (021)."""

from collections.abc import Iterable, Mapping
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from importers.banks.common import collapse_spaces
from importers.models import PendingBankRow, ShopRule
from ledger.errors import LedgerError
from ledger.models import Category, Group, Member
from ledger.services.splits import split_for_preset


def match_key(text: str) -> str:
    return collapse_spaces(text).casefold()


def row_text(row: PendingBankRow) -> str:
    """The shop name of a row: what "remember" stores and what history compares."""
    return collapse_spaces(row.merchant) or collapse_spaces(row.description)


def find_rule(rules: Iterable[ShopRule], row: PendingBankRow) -> ShopRule | None:
    """Longest matching text wins; ties go to the lowest id, so order never matters."""
    haystacks = (match_key(row.merchant), match_key(row.description))
    best: ShopRule | None = None
    for rule in rules:
        needle = match_key(rule.match_text)
        if not needle or not any(needle in h for h in haystacks):
            continue
        if (
            best is None
            or len(needle) > len(match_key(best.match_text))
            or (len(needle) == len(match_key(best.match_text)) and rule.pk < best.pk)
        ):
            best = rule
    return best


def check_split(group: Group, payer_id: int, preset: str, params: Mapping[str, Any]) -> None:
    """Dry run: a bad split fails when it is saved, not on the next bank row."""
    member_ids = sorted(group.members.values_list("id", flat=True))
    split_for_preset(preset, 100, member_ids, payer_id, params)


def _check_category(category: Category) -> None:
    if category.children.exists():
        raise LedgerError("invalid_category", "pick a sub-category, not a main type")


def save_rule(
    group: Group,
    member: Member,
    *,
    match_text: str,
    category: Category,
    preset: str,
    params: Mapping[str, Any] | None = None,
    rule: ShopRule | None = None,
    upsert: bool = False,
) -> ShopRule:
    """Create, or update `rule`. With `upsert` ("remember"), a live rule with the same text is
    updated instead of refused as `duplicate_rule`."""
    if member.group_id != group.id:
        raise LedgerError("member_not_in_group", "the member must belong to the group")
    text = collapse_spaces(match_text)
    if not text:
        raise LedgerError("invalid_request", "the shop text is empty")
    params = dict(params or {})
    _check_category(category)
    check_split(group, member.id, preset, params)
    if rule is None and upsert:
        rule = (
            ShopRule.objects.filter(group=group)
            .annotate(key=Lower("match_text"))
            .filter(key=text.lower())
            .first()
        )
    if rule is None:
        rule = ShopRule(group=group, created_by=member)
    rule.match_text = text
    rule.category = category
    rule.preset = preset
    rule.params = params
    try:
        with transaction.atomic():
            rule.save()
    except IntegrityError as exc:
        raise LedgerError("duplicate_rule", f"a rule for {text!r} already exists") from exc
    return rule


def delete_rule(rule: ShopRule) -> None:
    if rule.deleted_at is not None:
        return
    rule.deleted_at = timezone.now()
    rule.save(update_fields=["deleted_at", "updated_at"])


def touch(rule: ShopRule) -> None:
    rule.last_used_at = timezone.now()
    rule.save(update_fields=["last_used_at", "updated_at"])
