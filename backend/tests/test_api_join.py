import pytest
from rest_framework.test import APIClient

from accounts.services.auth import register
from ledger.models import GroupLink, Member
from ledger.services import groups

pytestmark = pytest.mark.django_db


def test_join_preview_is_public_and_unknown_token_404(world):
    res = APIClient().get(f"/api/join/{world.rome.share_token}/")
    assert res.status_code == 200
    assert res.json() == {
        "group_name": "Rome",
        "currency": "EUR",
        "member_names": ["Ann", "Bea", "Gus"],
    }
    assert APIClient().get("/api/join/nope/").status_code == 404


def test_anonymous_join_adds_guest_membership_to_me(world):
    client = APIClient()
    res = client.post(
        f"/api/join/{world.home.share_token}/", {"display_name": "Zed"}, format="json"
    )
    assert res.status_code == 200
    member = Member.objects.get(group=world.home, display_name="Zed")
    assert member.profile_id is None
    assert res.json() == {"group_id": world.home.id, "member_id": member.id}
    assert client.get("/api/me").json()["guest_memberships"] == [member.id]
    assert client.get(f"/api/groups/{world.home.id}/").status_code == 200


def test_guest_joining_twice_returns_same_member(world):
    client = APIClient()
    url = f"/api/join/{world.home.share_token}/"
    first = client.post(url, {"display_name": "Zed"}, format="json").json()
    second = client.post(url, {"display_name": "Zed"}, format="json").json()
    assert first == second
    assert Member.objects.filter(group=world.home, display_name="Zed").count() == 1


def test_second_visitor_with_taken_name_gets_name_taken(world):
    url = f"/api/join/{world.home.share_token}/"
    APIClient().post(url, {"display_name": "Zed"}, format="json")
    res = APIClient().post(url, {"display_name": "Zed"}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "name_taken"


def test_signed_in_join_uses_profile_and_links(world):
    d = register("d@example.com", "correct-horse-battery-9", "Dee")
    groups.create_group(d, "Dee Home", "EUR", as_main=True)
    client = world.login(d)
    res = client.post(
        f"/api/join/{world.rome.share_token}/", {"display_name": "Dee"}, format="json"
    )
    assert res.status_code == 200
    member = Member.objects.get(pk=res.json()["member_id"])
    assert member.profile_id == d.id
    assert GroupLink.objects.filter(profile=d, sub_group=world.rome, active=True).exists()
    assert client.get("/api/me").json()["guest_memberships"] == []


def test_join_post_without_csrf_token_is_403_and_with_token_succeeds(world):
    client = APIClient(enforce_csrf_checks=True)
    url = f"/api/join/{world.home.share_token}/"
    blocked = client.post(url, {"display_name": "Zed"}, format="json")
    assert blocked.status_code == 403 and blocked.json()["code"] == "csrf_failed"
    token = client.get(url).cookies["csrftoken"].value
    ok = client.post(url, {"display_name": "Zed"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert ok.status_code == 200


def test_group_writes_without_csrf_token_are_403_and_with_token_succeed(world):
    a_client = APIClient(enforce_csrf_checks=True)
    a_client.force_login(world.a.user)
    blocked = a_client.post("/api/groups/", {"name": "X", "currency": "EUR"}, format="json")
    assert blocked.status_code == 403 and blocked.json()["code"] == "csrf_failed"

    guest = APIClient(enforce_csrf_checks=True)
    session = guest.session
    session["guest_member_ids"] = [world.gus.id]
    session.save()
    body = {"from_member": world.gus.id, "to_member": 1, "amount_cents": 1, "date": "2026-10-01"}
    res = guest.post(f"/api/groups/{world.rome.id}/settlements/", body, format="json")
    assert res.status_code == 403 and res.json()["code"] == "csrf_failed"

    token = a_client.get("/api/me").cookies["csrftoken"].value
    ok = a_client.post(
        "/api/groups/", {"name": "X", "currency": "EUR"}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert ok.status_code == 201
