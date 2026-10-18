import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Profile
from accounts.services.access import add_guest_member, member_for, require_member
from ledger.errors import LedgerError
from ledger.models import Group, Member

pytestmark = pytest.mark.django_db

User = get_user_model()


class Req:
    """The two attributes the access helpers read."""

    def __init__(self, session, user=None):
        from django.contrib.auth.models import AnonymousUser

        self.session = session
        self.user = user or AnonymousUser()


def session():
    from django.contrib.sessions.backends.db import SessionStore

    return SessionStore()


def profile(name):
    u = User.objects.create_user(username=name)
    return Profile.objects.create(user=u, display_name=name)


@pytest.fixture
def group():
    return Group.objects.create(name="Trip", currency="EUR")


def test_guest_membership_in_session_visible_in_me(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    c = APIClient()
    c.get("/api/me")  # creates no session yet
    s = c.session
    s["guest_member_ids"] = [guest.id]
    s.save()
    assert c.get("/api/me").json()["guest_memberships"] == [guest.id]


def test_me_hides_guest_ids_of_deleted_members(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    c = APIClient()
    s = c.session
    s["guest_member_ids"] = [guest.id, 99999]
    s.save()
    assert c.get("/api/me").json()["guest_memberships"] == [guest.id]


def test_member_for_returns_guest_member_and_other_session_gets_none(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    mine = Req(session())
    add_guest_member(mine, guest)
    assert member_for(mine, group) == guest
    assert member_for(Req(session()), group) is None


def test_member_for_ignores_guest_id_from_another_group(group):
    other = Group.objects.create(name="Other", currency="EUR")
    foreign = Member.objects.create(group=other, display_name="Gus")
    own = Member.objects.create(group=group, display_name="Gus")
    req = Req(session())
    add_guest_member(req, foreign)
    assert member_for(req, group) is None
    add_guest_member(req, own)
    assert member_for(req, group) == own


def test_member_for_prefers_profile_member(group):
    p = profile("ann")
    pm = Member.objects.create(group=group, display_name="Ann", profile=p)
    gm = Member.objects.create(group=group, display_name="Gus")
    req = Req(session(), p.user)
    add_guest_member(req, gm)
    assert member_for(req, group) == pm


def test_member_for_falls_back_to_guest_id_for_authenticated_user_without_profile_member(group):
    p = profile("ann")
    gm = Member.objects.create(group=group, display_name="Gus")
    req = Req(session(), p.user)
    assert member_for(req, group) is None
    add_guest_member(req, gm)
    assert member_for(req, group) == gm


def test_require_member_non_member_is_404_member_is_returned(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    req = Req(session())
    with pytest.raises(LedgerError) as e:
        require_member(req, group)
    assert e.value.code == "not_found"
    add_guest_member(req, guest)
    assert require_member(req, group) == guest


def test_require_member_refusal_maps_to_404_with_same_body_as_missing(group):
    from accounts.api.errors import handler

    r = handler(LedgerError("not_found"), {})
    assert (r.status_code, r.data["code"]) == (404, "not_found")


def test_guest_ids_survive_login_but_not_logout(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    c = APIClient()
    s = c.session
    s["guest_member_ids"] = [guest.id]
    s.save()
    c.post(
        "/api/auth/register",
        {
            "email": "ann@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Ann",
        },
        format="json",
    )
    assert c.get("/api/me").json()["guest_memberships"] == [guest.id]
    c.post("/api/auth/logout")
    assert c.get("/api/me").json()["guest_memberships"] == []


def test_add_guest_member_deduplicates(group):
    guest = Member.objects.create(group=group, display_name="Gus")
    req = Req(session())
    add_guest_member(req, guest)
    add_guest_member(req, guest)
    assert req.session["guest_member_ids"] == [guest.id]
