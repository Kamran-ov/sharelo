"""Spending analytics, computed on every call from expenses; nothing is stored.

"Spending" is a member's OWED share (`ExpenseSplit.owed_cents`), never what they paid, so a
personal expense counts fully for its owner and a 50/50 dinner counts half per person. A
personal expense already carries a 100% split to its payer, so it needs no special case.
Settlements are never queried: moving money between people is not spending.

Date ranges are inclusive on both ends. Soft-deleted expenses are excluded. Category `level=1`
rolls a child into its parent inside the same query; `level=2` keeps the expense's own category.
Every function is a single query.
"""

import datetime

from django.db.models import F, OuterRef, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth

from ledger.errors import LedgerError
from ledger.models import ExpenseSplit, Group, Member


def _splits_in_range(
    group: Group, date_from: datetime.date, date_to: datetime.date, member: Member | None
) -> QuerySet[ExpenseSplit]:
    _check_member(group, member)
    splits = ExpenseSplit.objects.filter(
        expense__group=group,
        expense__deleted_at__isnull=True,
        expense__date__gte=date_from,
        expense__date__lte=date_to,
    )
    return splits if member is None else splits.filter(member_id=member.id)


def _check_member(group: Group, member: Member | None) -> None:
    if member is not None and member.group_id != group.id:
        raise LedgerError("member_not_in_group", f"member {member.id} is not in group {group.id}")


def _category_key(level: int):
    if level == 1:
        return Coalesce("expense__category__parent_id", "expense__category_id")
    if level == 2:
        return F("expense__category_id")
    raise LedgerError("invalid_level", f"level={level}")


def spending_by_member(
    group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    member: Member | None = None,
) -> dict[int, int]:
    _check_member(group, member)
    # The conditions sit inside the subquery so members with no spending stay in the result as 0.
    owed = (
        _splits_in_range(group, date_from, date_to, None)
        .filter(member_id=OuterRef("pk"))
        .values("member_id")
        .annotate(total=Sum("owed_cents"))
        .values("total")
    )
    members = Member.objects.filter(group=group)
    if member is not None:
        members = members.filter(pk=member.id)
    rows = members.annotate(total=Coalesce(Subquery(owed), 0)).values_list("id", "total")
    return dict(rows)


def spending_by_category(
    group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    member: Member | None = None,
    level: int = 1,
) -> dict[int, int]:
    rows = (
        _splits_in_range(group, date_from, date_to, member)
        .annotate(cat=_category_key(level))
        .values("cat")
        .annotate(total=Sum("owed_cents"))
        .values_list("cat", "total")
    )
    return dict(rows)


def spending_by_month(
    group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    member: Member | None = None,
) -> dict[str, int]:
    # TruncMonth on a DateField applies no timezone shift: the group's day is the date given.
    rows = (
        _splits_in_range(group, date_from, date_to, member)
        .annotate(month=TruncMonth("expense__date"))
        .values("month")
        .annotate(total=Sum("owed_cents"))
        .values_list("month", "total")
    )
    return {month.strftime("%Y-%m"): total for month, total in rows}


def spending_by_member_and_category(
    group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    member: Member | None = None,
    level: int = 1,
) -> dict[int, dict[int, int]]:
    rows = (
        _splits_in_range(group, date_from, date_to, member)
        .annotate(cat=_category_key(level))
        .values("member_id", "cat")
        .annotate(total=Sum("owed_cents"))
        .values_list("member_id", "cat", "total")
    )
    result: dict[int, dict[int, int]] = {}
    for member_id, category_id, total in rows:
        result.setdefault(member_id, {})[category_id] = total
    return result
