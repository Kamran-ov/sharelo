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


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    from django.core.cache import cache

    cache.clear()


# ---- API world: shared by test_api_*.py ----


class World:
    """A and B share Home and the Rome trip (Gus is a guest there); C is in nothing."""

    def __init__(self):
        from accounts.services.auth import register
        from ledger.services import groups

        self.a = register("a@example.com", "correct-horse-battery-9", "Ann")
        self.b = register("b@example.com", "correct-horse-battery-9", "Bea")
        self.c = register("c@example.com", "correct-horse-battery-9", "Cyd")
        self.home = groups.create_group(self.a, "Home", "EUR", as_main=True)
        groups.join_group_by_token(self.home.share_token, "Bea", self.b, as_main=True)
        self.rome = groups.create_group(self.a, "Rome", "EUR")
        groups.join_group_by_token(self.rome.share_token, "Bea", self.b)
        self.gus = groups.join_group_by_token(self.rome.share_token, "Gus", None)
        self.groceries = Category.objects.get(name="Groceries")

    def member(self, profile, group):
        return Member.objects.get(group=group, profile=profile)

    @staticmethod
    def login(profile):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_login(profile.user)
        return client

    def guest_client(self):
        from rest_framework.test import APIClient

        client = APIClient()
        session = client.session
        session["guest_member_ids"] = [self.gus.id]
        session.save()
        return client

    def expense_body(self, group, payer_profile, **over):
        body = {
            "description": "Dinner",
            "amount_cents": 5000,
            "date": "2026-10-01",
            "category": self.groceries.id,
            "payer_member": self.member(payer_profile, group).id,
            "preset": "half",
        }
        body.update(over)
        return body


@pytest.fixture
def world(db):
    return World()


@pytest.fixture
def api_a(world):
    return world.login(world.a)


@pytest.fixture
def api_b(world):
    return world.login(world.b)


@pytest.fixture
def api_c(world):
    return world.login(world.c)
