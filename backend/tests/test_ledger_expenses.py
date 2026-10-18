import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from ledger.errors import LedgerError
from ledger.models import Expense, ExpensePayer, ExpenseSplit, Group, Member
from ledger.services import expenses
from ledger.services.expenses import create_expense, delete_expense, update_expense

pytestmark = pytest.mark.django_db


def refused(group, expense_kwargs, code, **override):
    with pytest.raises(LedgerError) as exc:
        create_expense(group, **{**expense_kwargs, **override})
    assert exc.value.code == code
    assert Expense.all_objects.count() == 0


def test_payers_sum_to_total(group, members, expense_kwargs):
    ann, ben, _ = members
    refused(group, expense_kwargs, "payers_sum_mismatch", payers={ann.id: 999})
    expense = create_expense(group, **{**expense_kwargs, "payers": {ann.id: 600, ben.id: 400}})
    assert sum(p.paid_cents for p in expense.payers.all()) == 1000


def test_splits_sum_to_total(group, members, expense_kwargs):
    ann, ben, cy = members
    refused(
        group, expense_kwargs, "splits_sum_mismatch", splits={ann.id: 333, ben.id: 333, cy.id: 333}
    )
    refused(
        group, expense_kwargs, "splits_sum_mismatch", splits={ann.id: 334, ben.id: 334, cy.id: 333}
    )
    expense = create_expense(group, **expense_kwargs)
    assert sorted(s.owed_cents for s in expense.splits.all()) == [333, 333, 334]


def test_members_belong_to_group(group, members, expense_kwargs):
    other = Group.objects.create(name="Trip", currency="EUR")
    stranger = Member.objects.create(group=other, display_name="Zed")
    ann, ben, cy = members
    refused(group, expense_kwargs, "member_not_in_group", payers={stranger.id: 1000})
    refused(
        group,
        expense_kwargs,
        "member_not_in_group",
        splits={ann.id: 500, stranger.id: 500},
    )
    assert create_expense(group, **expense_kwargs).pk


def test_amount_must_be_positive(group, members, expense_kwargs):
    ann = members[0]
    for bad in (0, -1):
        refused(
            group,
            expense_kwargs,
            "amount_not_positive",
            amount_cents=bad,
            payers={ann.id: bad},
            splits={ann.id: bad},
        )
    expense = create_expense(
        group, **{**expense_kwargs, "amount_cents": 1, "payers": {ann.id: 1}, "splits": {ann.id: 1}}
    )
    assert expense.amount_cents == 1


@pytest.mark.parametrize("bad", ["EU", "eur", "EU1", "EURO", ""])
def test_currency_must_be_valid_three_letter_code(group, expense_kwargs, bad):
    refused(group, expense_kwargs, "invalid_currency", currency=bad)


def test_valid_currency_code_is_accepted(group, expense_kwargs):
    assert create_expense(group, **expense_kwargs).currency == "EUR"


def test_expense_currency_matches_group_currency(group, expense_kwargs):
    refused(group, expense_kwargs, "currency_mismatch", currency="USD")
    expense = create_expense(
        group,
        **expense_kwargs,
        original_amount_cents=1100,
        original_currency="USD",
        rate_used=Decimal("0.90909091"),
    )
    assert (expense.currency, expense.original_currency) == ("EUR", "USD")
    assert expense.rate_used == Decimal("0.90909091")


def test_same_currency_expense_stores_identity_original(group, expense_kwargs):
    expense = create_expense(group, **expense_kwargs)
    assert (expense.original_amount_cents, expense.original_currency) == (1000, "EUR")
    assert expense.rate_used == Decimal(1)


def test_original_fields_come_together(group, expense_kwargs):
    refused(group, expense_kwargs, "incomplete_original", original_currency="USD")


def test_negative_and_empty_shares_are_refused(group, members, expense_kwargs):
    ann, ben, _ = members
    refused(group, expense_kwargs, "negative_share", splits={ann.id: 1100, ben.id: -100})
    refused(group, expense_kwargs, "empty_payers", payers={})
    refused(group, expense_kwargs, "empty_splits", splits={})
    # zero entries are legitimate, e.g. a personal expense in a three-person group
    ok = create_expense(
        group, **{**expense_kwargs, "splits": {ann.id: 1000, ben.id: 0}, "split_type": "personal"}
    )
    assert ok.splits.count() == 2


def test_enum_values_are_checked(group, expense_kwargs):
    refused(group, expense_kwargs, "invalid_split_type", split_type="thirds")
    refused(group, expense_kwargs, "invalid_source", source="venmo")
    assert create_expense(group, **{**expense_kwargs, "source": "wise", "external_id": "w1"}).pk


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_failed_split_leaves_no_rows(group, members, expense_kwargs, monkeypatch):
    ann, ben, _ = members
    # Bypass validation so the failure comes from the DB CHECK on the split row, after the
    # expense and payer rows were written: only atomicity can leave zero rows behind.
    monkeypatch.setattr(expenses, "_validate", lambda *a, **k: None)
    bad = {**expense_kwargs, "splits": {ann.id: 1100, ben.id: -100}}
    with pytest.raises(IntegrityError) as exc:
        create_expense(group, **bad)
    assert not isinstance(exc.value, LedgerError)  # a CHECK violation is not "duplicate"
    assert Expense.all_objects.count() == 0
    assert ExpensePayer.objects.count() == 0
    assert ExpenseSplit.objects.count() == 0


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_successful_create_writes_expense_payers_and_splits(group, expense_kwargs):
    create_expense(group, **expense_kwargs)
    assert (Expense.all_objects.count(), ExpensePayer.objects.count()) == (1, 1)
    assert ExpenseSplit.objects.count() == 3


def test_delete_is_soft_and_hidden_from_default_manager(group, expense_kwargs):
    gone = create_expense(group, **expense_kwargs)
    kept = create_expense(group, **{**expense_kwargs, "description": "Other"})
    delete_expense(gone)
    assert gone.deleted_at is not None
    assert list(Expense.objects.all()) == [kept]
    assert Expense.all_objects.count() == 2
    first = Expense.all_objects.get(pk=gone.pk).deleted_at
    delete_expense(gone)
    assert Expense.all_objects.get(pk=gone.pk).deleted_at == first


def test_duplicate_source_external_id_rejected(group, expense_kwargs):
    base = {**expense_kwargs, "source": "splitwise", "external_id": "sw-1"}
    create_expense(group, **base)
    with pytest.raises(LedgerError) as exc:
        create_expense(group, **base)
    assert exc.value.code == "duplicate_external_id"
    assert Expense.all_objects.count() == 1
    assert ExpensePayer.objects.count() == 1 and ExpenseSplit.objects.count() == 3
    create_expense(group, **{**base, "external_id": "sw-2"})
    create_expense(group, **{**base, "source": "revolut"})
    assert Expense.all_objects.count() == 3


def test_soft_deleted_expense_still_blocks_reimport(group, expense_kwargs):
    base = {**expense_kwargs, "source": "splitwise", "external_id": "sw-1"}
    delete_expense(create_expense(group, **base))
    with pytest.raises(LedgerError) as exc:
        create_expense(group, **base)
    assert exc.value.code == "duplicate_external_id"


def test_null_external_id_is_not_unique(group, expense_kwargs):
    create_expense(group, **expense_kwargs)
    create_expense(group, **expense_kwargs)
    assert Expense.objects.count() == 2


def test_update_replaces_payers_and_splits(group, members, expense_kwargs):
    ann, ben, cy = members
    expense = create_expense(group, **expense_kwargs)
    kwargs = {k: v for k, v in expense_kwargs.items()}
    kwargs.update(
        amount_cents=900, payers={ben.id: 900}, splits={ann.id: 300, ben.id: 300, cy.id: 300}
    )
    update_expense(expense, **kwargs)
    expense.refresh_from_db()
    assert expense.amount_cents == 900
    assert {p.member_id: p.paid_cents for p in expense.payers.all()} == {ben.id: 900}
    assert sorted(s.owed_cents for s in expense.splits.all()) == [300, 300, 300]


def test_update_refuses_invalid_and_deleted(group, members, expense_kwargs):
    expense = create_expense(group, **expense_kwargs)
    bad = {**expense_kwargs, "splits": {members[0].id: 1}}
    with pytest.raises(LedgerError) as exc:
        update_expense(expense, **bad)
    assert exc.value.code == "splits_sum_mismatch"
    assert expense.splits.count() == 3
    delete_expense(expense)
    with pytest.raises(LedgerError) as exc:
        update_expense(expense, **expense_kwargs)
    assert exc.value.code == "expense_deleted"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_update_replaces_payers_and_splits_atomically(group, members, expense_kwargs, monkeypatch):
    ann, ben, _ = members
    expense = create_expense(group, **expense_kwargs)
    monkeypatch.setattr(expenses, "_validate", lambda *a, **k: None)
    with pytest.raises(IntegrityError):
        update_expense(expense, **{**expense_kwargs, "splits": {ann.id: 1100, ben.id: -100}})
    assert {p.member_id: p.paid_cents for p in expense.payers.all()} == {ann.id: 1000}
    assert sorted(s.owed_cents for s in expense.splits.all()) == [333, 333, 334]
    assert Expense.all_objects.get(pk=expense.pk).amount_cents == 1000


def test_db_constraints_hold_without_service(group, members, expense_kwargs, category, day):
    ann, ben, _ = members
    expense = create_expense(group, **expense_kwargs)
    from ledger.models import Settlement

    with pytest.raises(IntegrityError), transaction.atomic():
        ExpensePayer.objects.create(expense=expense, member=ben, paid_cents=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        ExpenseSplit.objects.create(
            expense=expense, member=ann, owed_cents=1
        )  # (expense, member) twice
    with pytest.raises(IntegrityError), transaction.atomic():
        Expense.objects.create(
            group=group,
            description="x",
            amount_cents=0,
            currency="EUR",
            original_amount_cents=0,
            original_currency="EUR",
            date=day,
            category=category,
            split_type="equal",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Settlement.objects.create(
            group=group, from_member=ann, to_member=ann, amount_cents=5, currency="EUR", date=day
        )
    assert Settlement.objects.create(
        group=group, from_member=ann, to_member=ben, amount_cents=5, currency="EUR", date=day
    ).pk


def test_settlement_source_external_id_is_unique(group, members, day):
    from ledger.models import Settlement

    ann, ben, _ = members
    make = lambda ext: Settlement.objects.create(  # noqa: E731
        group=group,
        from_member=ann,
        to_member=ben,
        amount_cents=5,
        currency="EUR",
        date=day,
        source="splitwise",
        external_id=ext,
    )
    make("s1")
    with pytest.raises(IntegrityError), transaction.atomic():
        make("s1")
    assert make("s2").pk


def test_member_name_unique_within_group_only(group, members):
    with pytest.raises(IntegrityError), transaction.atomic():
        Member.objects.create(group=group, display_name="Ann")
    other = Group.objects.create(name="Trip", currency="EUR")
    assert Member.objects.create(group=other, display_name="Ann").pk


def test_share_token_is_unique_and_url_safe():
    a, b = (Group.objects.create(name=n, currency="EUR") for n in "ab")
    assert a.share_token != b.share_token
    assert all(c.isalnum() or c in "-_" for c in a.share_token)
    assert len(a.share_token) >= 16
    assert isinstance(a.created_at, datetime.datetime)
