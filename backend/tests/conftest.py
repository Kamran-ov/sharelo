import datetime

import pytest

from ledger.models import Category, Group, Member


@pytest.fixture
def group(db):
    return Group.objects.create(name="Home", currency="EUR")


@pytest.fixture
def members(group):
    return [Member.objects.create(group=group, display_name=n) for n in ("Ann", "Ben", "Cy")]


@pytest.fixture
def category(db):
    return Category.objects.get(name="Groceries")


@pytest.fixture
def day():
    return datetime.date(2026, 10, 1)


@pytest.fixture
def expense_kwargs(members, category, day):
    ann, ben, cy = members
    return {
        "description": "Groceries",
        "amount_cents": 1000,
        "currency": "EUR",
        "date": day,
        "category": category,
        "payers": {ann.id: 1000},
        "splits": {ann.id: 334, ben.id: 333, cy.id: 333},
        "split_type": "equal",
    }
