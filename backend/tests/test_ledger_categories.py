import pytest
from django.db import IntegrityError, transaction

from ledger.errors import LedgerError
from ledger.models import Category

pytestmark = pytest.mark.django_db

PARENTS = {
    "Entertainment": 5,
    "Food and drink": 4,
    "Home": 9,
    "Life": 8,
    "Transportation": 9,
    "Utilities": 7,
    "Uncategorized": 1,
}


def test_seed_tree_has_parents_with_children():
    roots = Category.objects.filter(parent__isnull=True)
    assert {c.name for c in roots} == set(PARENTS)
    for root in roots:
        assert root.children.count() == PARENTS[root.name] >= 1
    assert Category.objects.filter(parent__isnull=False).count() == 43
    assert Category.objects.count() == 50
    assert Category.objects.filter(parent__parent__isnull=False).count() == 0


def test_category_depth_max_two():
    root = Category.objects.create(name="Pets & co")
    child = Category.objects.create(name="Vet", parent=root)
    assert child.pk
    with pytest.raises(LedgerError) as exc:
        Category.objects.create(name="Shots", parent=child)
    assert exc.value.code == "category_depth"


def test_reparenting_a_category_that_has_children_is_rejected():
    home = Category.objects.get(name="Home")
    other = Category.objects.create(name="Misc")
    home.parent = other
    with pytest.raises(LedgerError) as exc:
        home.save()  # Home's children would end up at depth 3
    assert exc.value.code == "category_depth"
    other.parent = Category.objects.get(name="Life")
    other.save()  # a childless root may move under another root


def test_self_parent_and_cycle_are_rejected_without_looping():
    a = Category.objects.create(name="A")
    b = Category.objects.create(name="B", parent=a)
    a.parent = a
    with pytest.raises(LedgerError):
        a.save()
    a.parent = b
    with pytest.raises(LedgerError):
        a.save()


def test_root_names_are_unique_despite_null_parent():
    Category.objects.create(name="Solo")
    with pytest.raises(IntegrityError), transaction.atomic():
        Category.objects.create(name="Solo")
    parent = Category.objects.create(name="P")
    assert Category.objects.create(name="Solo", parent=parent).pk
