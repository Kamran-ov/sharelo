import pytest
from django.db import IntegrityError, transaction

from ledger.errors import LedgerError
from ledger.models import Category, CategoryDefault, Expense, Group
from ledger.services.expenses import create_expense_from_preset
from ledger.services.splits import default_split_for

pytestmark = pytest.mark.django_db


def preset_kwargs(category, day, **override):
    return {
        "description": "Groceries",
        "amount_cents": 1000,
        "currency": "EUR",
        "date": day,
        "category": category,
        **override,
    }


def test_personal_preset_expense_has_same_payer_and_sole_split(group, members, category, day):
    ann = members[0]
    expense = create_expense_from_preset(
        group, preset="personal", payer_id=ann.id, **preset_kwargs(category, day)
    )
    payers = list(expense.payers.all())
    splits = list(expense.splits.all())
    assert [(p.member_id, p.paid_cents) for p in payers] == [(ann.id, 1000)]
    assert [(s.member_id, s.owed_cents) for s in splits] == [(ann.id, 1000)]
    assert expense.split_type == "personal"


def test_equal_preset_splits_across_all_group_members(group, members, category, day):
    ann, ben, cy = members
    expense = create_expense_from_preset(
        group, preset="equal", payer_id=ann.id, **preset_kwargs(category, day)
    )
    owed = {s.member_id: s.owed_cents for s in expense.splits.all()}
    assert owed == {ann.id: 334, ben.id: 333, cy.id: 333}


def test_preset_expense_rejects_payer_from_other_group(group, members, category, day):
    other = Group.objects.create(name="Other", currency="EUR")
    stranger = other.members.create(display_name="Zed")
    with pytest.raises(LedgerError) as exc:
        create_expense_from_preset(
            group, preset="equal", payer_id=stranger.id, **preset_kwargs(category, day)
        )
    assert exc.value.code == "member_not_in_group"
    assert Expense.all_objects.count() == 0


def test_default_split_for_returns_group_default_else_equal(group, members):
    groceries = Category.objects.get(name="Groceries")
    other_group = Group.objects.create(name="Other", currency="EUR")
    assert default_split_for(group, groceries) == ("equal", {})

    CategoryDefault.objects.create(
        group=group, category=groceries, split_type="percentage", split_params={"a": 1}
    )
    CategoryDefault.objects.create(group=other_group, category=groceries, split_type="personal")
    assert default_split_for(group, groceries) == ("percentage", {"a": 1})
    assert default_split_for(other_group, groceries) == ("personal", {})

    with pytest.raises(IntegrityError), transaction.atomic():
        CategoryDefault.objects.create(group=group, category=groceries)
    assert CategoryDefault.objects.filter(group=group, category=groceries).count() == 1
