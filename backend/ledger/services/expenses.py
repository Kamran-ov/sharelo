import datetime
import re
from decimal import Decimal

from django.db import IntegrityError, transaction
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
    RecurringRule,
    Source,
    SplitType,
)

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_DUPLICATE_CONSTRAINT = "uniq_expense_source_external_id"


def _validate(
    group: Group,
    *,
    amount_cents: int,
    currency: str,
    split_type: str,
    source: str,
    payers: dict[int, int],
    splits: dict[int, int],
    original_amount_cents: int | None,
    original_currency: str | None,
    rate_used: Decimal | None,
) -> None:
    if amount_cents <= 0:
        raise LedgerError("amount_not_positive", f"amount_cents={amount_cents}")
    if not _CURRENCY_RE.match(currency):
        raise LedgerError("invalid_currency", repr(currency))
    if currency != group.currency:
        raise LedgerError("currency_mismatch", f"{currency} in a {group.currency} group")
    if split_type not in SplitType.values:
        raise LedgerError("invalid_split_type", repr(split_type))
    if source not in Source.values:
        raise LedgerError("invalid_source", repr(source))

    given = [original_amount_cents, original_currency, rate_used]
    if any(v is not None for v in given) and any(v is None for v in given):
        raise LedgerError("incomplete_original", "give original amount, currency and rate together")
    if original_currency is not None and not _CURRENCY_RE.match(original_currency):
        raise LedgerError("invalid_currency", repr(original_currency))

    if not payers:
        raise LedgerError("empty_payers")
    if not splits:
        raise LedgerError("empty_splits")
    if any(v < 0 for v in [*payers.values(), *splits.values()]):
        raise LedgerError("negative_share")

    member_ids = set(payers) | set(splits)
    in_group = set(
        Member.objects.filter(group=group, id__in=member_ids).values_list("id", flat=True)
    )
    if in_group != member_ids:
        raise LedgerError("member_not_in_group", f"ids {sorted(member_ids - in_group)}")

    if sum(payers.values()) != amount_cents:
        raise LedgerError("payers_sum_mismatch", f"{sum(payers.values())} != {amount_cents}")
    if sum(splits.values()) != amount_cents:
        raise LedgerError("splits_sum_mismatch", f"{sum(splits.values())} != {amount_cents}")


def _constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)


def _original_fields(
    amount_cents: int,
    currency: str,
    original_amount_cents: int | None,
    original_currency: str | None,
    rate_used: Decimal | None,
) -> dict:
    if original_amount_cents is None:
        return {
            "original_amount_cents": amount_cents,
            "original_currency": currency,
            "rate_used": Decimal(1),
        }
    return {
        "original_amount_cents": original_amount_cents,
        "original_currency": original_currency,
        "rate_used": rate_used,
    }


def _write_rows(expense: Expense, payers: dict[int, int], splits: dict[int, int]) -> None:
    ExpensePayer.objects.bulk_create(
        [ExpensePayer(expense=expense, member_id=m, paid_cents=c) for m, c in payers.items()]
    )
    ExpenseSplit.objects.bulk_create(
        [ExpenseSplit(expense=expense, member_id=m, owed_cents=c) for m, c in splits.items()]
    )


def create_expense(
    group: Group,
    *,
    description: str,
    amount_cents: int,
    currency: str,
    date: datetime.date,
    category: Category,
    payers: dict[int, int],
    splits: dict[int, int],
    split_type: str,
    source: str = Source.MANUAL,
    external_id: str | None = None,
    original_amount_cents: int | None = None,
    original_currency: str | None = None,
    rate_used: Decimal | None = None,
    import_batch: ImportBatch | None = None,
    recurring_rule: RecurringRule | None = None,
    notes: str = "",
) -> Expense:
    _validate(
        group,
        amount_cents=amount_cents,
        currency=currency,
        split_type=split_type,
        source=source,
        payers=payers,
        splits=splits,
        original_amount_cents=original_amount_cents,
        original_currency=original_currency,
        rate_used=rate_used,
    )
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: keeps the outer transaction usable
                expense = Expense.objects.create(
                    group=group,
                    description=description,
                    amount_cents=amount_cents,
                    currency=currency,
                    date=date,
                    category=category,
                    split_type=split_type,
                    source=source,
                    external_id=external_id,
                    import_batch=import_batch,
                    recurring_rule=recurring_rule,
                    notes=notes,
                    **_original_fields(
                        amount_cents, currency, original_amount_cents, original_currency, rate_used
                    ),
                )
        except IntegrityError as exc:
            if _constraint_name(exc) == _DUPLICATE_CONSTRAINT:
                raise LedgerError("duplicate_external_id", f"{source}/{external_id}") from exc
            raise
        _write_rows(expense, payers, splits)
    return expense


def update_expense(
    expense: Expense,
    *,
    description: str,
    amount_cents: int,
    currency: str,
    date: datetime.date,
    category: Category,
    payers: dict[int, int],
    splits: dict[int, int],
    split_type: str,
    original_amount_cents: int | None = None,
    original_currency: str | None = None,
    rate_used: Decimal | None = None,
    notes: str = "",
) -> Expense:
    if expense.deleted_at is not None:
        raise LedgerError("expense_deleted", f"expense {expense.pk}")
    _validate(
        expense.group,
        amount_cents=amount_cents,
        currency=currency,
        split_type=split_type,
        source=expense.source,
        payers=payers,
        splits=splits,
        original_amount_cents=original_amount_cents,
        original_currency=original_currency,
        rate_used=rate_used,
    )
    with transaction.atomic():
        expense.description = description
        expense.amount_cents = amount_cents
        expense.currency = currency
        expense.date = date
        expense.category = category
        expense.split_type = split_type
        expense.notes = notes
        for field, value in _original_fields(
            amount_cents, currency, original_amount_cents, original_currency, rate_used
        ).items():
            setattr(expense, field, value)
        expense.save()
        expense.payers.all().delete()
        expense.splits.all().delete()
        _write_rows(expense, payers, splits)
    return expense


def delete_expense(expense: Expense) -> None:
    if expense.deleted_at is not None:
        return  # keep the real deletion time
    expense.deleted_at = timezone.now()
    expense.save(update_fields=["deleted_at", "updated_at"])
