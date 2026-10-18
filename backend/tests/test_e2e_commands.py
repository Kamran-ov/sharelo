import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import Profile
from ledger.management.commands import e2e_reset
from ledger.models import Category, ExchangeRate, Group, GroupLink, Member
from sharelo.e2e import check_e2e_settings

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def e2e_on(monkeypatch, settings):
    monkeypatch.setenv("E2E", "1")
    settings.E2E = True


@pytest.fixture
def as_e2e_database(monkeypatch):
    monkeypatch.setattr(e2e_reset, "database_name", lambda: "sharelo_e2e")


@pytest.fixture
def precious_user(db):
    return User.objects.create_user("keep@example.com", "keep@example.com", "x-y-z-123456")


def test_e2e_reset_refuses_without_e2e_flag(as_e2e_database, precious_user):
    with pytest.raises(CommandError, match="E2E=1"):
        call_command("e2e_reset")
    assert User.objects.filter(username="keep@example.com").exists()


def test_e2e_reset_refuses_when_database_name_does_not_end_in_e2e(e2e_on, precious_user):
    with pytest.raises(CommandError, match="_e2e"):
        call_command("e2e_reset")
    assert User.objects.filter(username="keep@example.com").exists()


def test_e2e_reset_wipes_and_seeds_fixture_on_e2e_database(e2e_on, as_e2e_database, precious_user):
    categories = Category.objects.count()
    ExchangeRate.objects.create(date="2026-10-01", currency="USD", rate_to_eur="1.1")
    ExchangeRate.objects.create(date="2026-10-01", currency="GBP", rate_to_eur="0.85")
    call_command("e2e_reset")
    assert not User.objects.filter(username="keep@example.com").exists()
    alice = Profile.objects.get(user__email="a@example.com")
    assert Profile.objects.count() == 2 and Group.objects.count() == 2
    assert alice.main_group.name == "Home"
    assert alice.user.check_password("password1234")
    assert set(alice.main_group.members.values_list("display_name", flat=True)) == {"Alice", "Bea"}
    rome = Group.objects.get(share_token="e2e-rome-token")
    assert list(Member.objects.filter(group=rome).values_list("display_name", flat=True)) == ["Bea"]
    assert GroupLink.objects.filter(sub_group=rome).count() == 1
    assert Category.objects.count() == categories
    # Reference data survives the wipe: the old USD row stays, today's is added, GBP is removed.
    assert ExchangeRate.objects.filter(currency="GBP").count() == 0
    assert ExchangeRate.objects.filter(currency="USD").count() == 2
    default = alice.main_group.category_defaults.get()
    assert (default.category.name, default.split_type) == ("General", "equal")


def test_e2e_reset_twice_gives_same_fixture(e2e_on, as_e2e_database):
    call_command("e2e_reset")
    call_command("e2e_reset")
    assert ExchangeRate.objects.filter(currency="USD").count() == 1
    assert Profile.objects.count() == 2
    assert Group.objects.get(share_token="e2e-rome-token").name == "Rome trip"
    assert Group.objects.get(name="Home").id == 1


def test_e2e_settings_refuse_foreign_allowed_hosts():
    with pytest.raises(ImproperlyConfigured, match="allows only"):
        check_e2e_settings("sharelo_e2e", "example.com")
    with pytest.raises(ImproperlyConfigured, match="_e2e"):
        check_e2e_settings("sharelo", None)
    check_e2e_settings("sharelo_e2e", "localhost,127.0.0.1")
    check_e2e_settings("sharelo_e2e", None)
