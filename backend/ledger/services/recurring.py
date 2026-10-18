"""Recurring rules: fixed bills (rent, Netflix) that turn into expenses on their due date.

`next_date` is the cursor: the next occurrence that has not been turned into an expense yet.
Idempotency does not rely on the cursor alone: every expense carries
`external_id = "rule:<id>:<date>"` under the `(source, external_id)` unique constraint, so a
cursor left behind by a crash or an overlapping cron run heals instead of duplicating.

Services never read the clock; callers pass `today`.
"""

import calendar
import datetime
import logging
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from ledger.errors import LedgerError
from ledger.models import Frequency, Group, Member, RecurringRule, Source
from ledger.services.expenses import create_expense_from_preset
from ledger.services.splits import split_for_preset

logger = logging.getLogger(__name__)

_SCHEDULE_FIELDS = ("day_of_month", "month", "frequency", "start_date")
_EDITABLE = {
    "description",
    "amount_cents",
    "payer",
    "split_type",
    "split_params",
    "category",
    "end_date",
    *_SCHEDULE_FIELDS,
}


@dataclass
class GenerateResult:
    created: list = field(default_factory=list)
    failed: list[tuple[int, str]] = field(default_factory=list)


def _occurrence_in_month(year: int, month: int, day_of_month: int) -> datetime.date:
    return datetime.date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))


def next_occurrence(after: datetime.date, rule: RecurringRule) -> datetime.date:
    """First occurrence strictly after `after`. The day is clamped to the month's length each
    time from the rule's own day, so Jan 31 -> Feb 28 -> Mar 31 never drifts."""
    if rule.frequency == Frequency.YEARLY:
        assert rule.month is not None
        year = after.year
        while True:
            candidate = _occurrence_in_month(year, rule.month, rule.day_of_month)
            if candidate > after:
                return candidate
            year += 1
    year, month = after.year, after.month
    while True:
        candidate = _occurrence_in_month(year, month, rule.day_of_month)
        if candidate > after:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def first_occurrence(on_or_after: datetime.date, rule: RecurringRule) -> datetime.date:
    return next_occurrence(on_or_after - datetime.timedelta(days=1), rule)


def _check(rule: RecurringRule) -> None:
    if rule.amount_cents <= 0:
        raise LedgerError("amount_not_positive", f"amount_cents={rule.amount_cents}")
    if rule.frequency not in Frequency.values:
        raise LedgerError("invalid_frequency", repr(rule.frequency))
    if not 1 <= rule.day_of_month <= 31:
        raise LedgerError("invalid_day", f"day_of_month={rule.day_of_month}")
    if rule.frequency == Frequency.MONTHLY and rule.month is not None:
        raise LedgerError("invalid_month", "month is for yearly rules only")
    if rule.frequency == Frequency.YEARLY and (rule.month is None or not 1 <= rule.month <= 12):
        raise LedgerError("invalid_month", f"month={rule.month}")
    if rule.end_date is not None and rule.end_date < rule.start_date:
        raise LedgerError("invalid_end_date", "end_date is before start_date")
    if rule.payer.group_id != rule.group_id:
        raise LedgerError("not_a_member", f"payer {rule.payer_id} is not in the group")
    member_ids = list(Member.objects.filter(group_id=rule.group_id).values_list("id", flat=True))
    # Dry run so a bad preset or params fails when the rule is saved, not on the due date.
    split_for_preset(
        rule.split_type, rule.amount_cents, member_ids, rule.payer_id, rule.split_params
    )


def create_rule(group: Group, **fields: Any) -> RecurringRule:
    rule = RecurringRule(group=group, **fields)
    rule.next_date = rule.start_date
    _check(rule)
    rule.next_date = first_occurrence(rule.start_date, rule)
    rule.save()
    return rule


def update_rule(
    rule: RecurringRule, today: datetime.date | None = None, **fields: Any
) -> RecurringRule:
    """Edits the rule only; expenses already created keep their amount.

    A change to day, month, frequency or start date needs `today` and moves the cursor to the
    first occurrence of the new schedule on or after max(next_date, today), so an edit
    mid-month cannot bill the same month twice. Other edits leave `next_date` alone.
    """
    unknown = set(fields) - _EDITABLE
    if unknown:
        raise LedgerError("unknown_field", ", ".join(sorted(unknown)))
    reschedule = any(
        name in fields and fields[name] != getattr(rule, name) for name in _SCHEDULE_FIELDS
    )
    if reschedule and today is None:
        raise LedgerError("today_required", "a schedule change needs today")
    for name, value in fields.items():
        setattr(rule, name, value)
    _check(rule)
    touched = [*fields, "updated_at"]
    if reschedule:
        assert today is not None
        rule.next_date = first_occurrence(max(rule.next_date, today), rule)
        touched.append("next_date")
    # update_fields: a concurrent generate_due may have moved next_date; never write it back stale.
    rule.save(update_fields=touched)
    return rule


def delete_rule(rule: RecurringRule) -> None:
    rule.deleted_at = timezone.now()
    rule.save(update_fields=["deleted_at", "updated_at"])


def pause_rule(rule: RecurringRule) -> None:
    rule.paused = True
    rule.save(update_fields=["paused", "updated_at"])


def resume_rule(rule: RecurringRule, today: datetime.date) -> None:
    """Paused months are not back-filled: the cursor jumps to the first occurrence from today."""
    rule.paused = False
    rule.next_date = first_occurrence(max(rule.next_date, today), rule)
    rule.save(update_fields=["paused", "next_date", "updated_at"])


def skip_next(rule: RecurringRule) -> None:
    rule.next_date = next_occurrence(rule.next_date, rule)
    rule.save(update_fields=["next_date", "updated_at"])


def _is_due(rule: RecurringRule, today: datetime.date) -> bool:
    return (
        not rule.paused
        and rule.next_date <= today
        and (rule.end_date is None or rule.next_date <= rule.end_date)
    )


def _lock(rule_id: int) -> RecurringRule | None:
    # Re-read after the lock: a concurrent run may already have moved the cursor.
    return (
        RecurringRule.objects.select_for_update()
        .select_related("group", "category")
        .filter(pk=rule_id)
        .first()
    )


def _generate_one(rule_id: int, today: datetime.date):
    """One occurrence. Returns (more_to_do, expense_or_None)."""
    try:
        with transaction.atomic():
            rule = _lock(rule_id)
            if rule is None or not _is_due(rule, today):
                return False, None
            expense = create_expense_from_preset(
                rule.group,
                preset=rule.split_type,
                payer_id=rule.payer_id,
                params=rule.split_params,
                description=rule.description,
                amount_cents=rule.amount_cents,
                currency=rule.group.currency,
                date=rule.next_date,
                category=rule.category,
                source=Source.RECURRING,
                external_id=f"rule:{rule.pk}:{rule.next_date.isoformat()}",
                recurring_rule=rule,
            )
            rule.next_date = next_occurrence(rule.next_date, rule)
            rule.save(update_fields=["next_date", "updated_at"])
            return True, expense
    except LedgerError as exc:
        # Caught outside the atomic block above: inside it, the next statement would hit an
        # aborted savepoint.
        if exc.code != "duplicate_external_id":
            raise
    with transaction.atomic():
        rule = _lock(rule_id)
        if rule is not None and _is_due(rule, today):
            rule.next_date = next_occurrence(rule.next_date, rule)
            rule.save(update_fields=["next_date", "updated_at"])
    return True, None


def generate_due(today: datetime.date) -> GenerateResult:
    """Create every expense that is due, catching up missed occurrences. One transaction per
    occurrence; a failing rule is recorded in `failed` and never blocks the others."""
    result = GenerateResult()
    rule_ids = (
        RecurringRule.objects.filter(paused=False, next_date__lte=today)
        .order_by("id")
        .values_list("id", flat=True)
    )
    for rule_id in list(rule_ids):
        more = True
        while more:
            try:
                more, expense = _generate_one(rule_id, today)
            except LedgerError as exc:
                result.failed.append((rule_id, exc.code))
                break
            except Exception:
                logger.exception("recurring rule %s failed", rule_id)
                result.failed.append((rule_id, "unexpected_error"))
                break
            if expense is not None:
                result.created.append(expense)
    return result
