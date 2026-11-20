"""017 API: add person, join preview, claim by link, sign-in adoption, guest logout."""

import pytest
from rest_framework.test import APIClient

from accounts.services import google
from ledger.models import Expense, GroupLink, Member
from ledger.services import groups

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"


@pytest.fixture
def flat(world):
    """Ann's Flat group with placeholders Janet and Cami and a 30.00 equal expense among 3."""
    ann = world.a
    flat = groups.create_group(ann, "Flat", "EUR")
    me = world.member(ann, flat)
    api = world.login(ann)
    janet = api.post(f"/api/groups/{flat.id}/members/", {"display_name": "Janet"}, format="json")
    cami = api.post(f"/api/groups/{flat.id}/members/", {"display_name": "Cami"}, format="json")
    assert (janet.status_code, cami.status_code) == (201, 201)
    body = {
        "description": "Groceries",
        "amount_cents": 3000,
        "date": "2026-10-01",
        "category": world.groceries.id,
        "payer_member": me.id,
        "preset": "equal",
    }
    assert api.post(f"/api/groups/{flat.id}/expenses/", body, format="json").status_code == 201
    return flat, Member.objects.get(pk=janet.json()["id"]), Member.objects.get(pk=cami.json()["id"])


def claim(client, group, member_id):
    return client.post(
        f"/api/join/{group.share_token}/claim", {"member_id": member_id}, format="json"
    )


def session_ids(client) -> list[int]:
    return list(client.session.get("guest_member_ids") or [])


def test_claiming_a_claimed_member_is_refused_and_changes_nothing(flat):
    group, janet, _ = flat
    a, b = APIClient(), APIClient()
    assert claim(a, group, janet.id).status_code == 200
    before = Member.objects.values().get(pk=janet.id)

    res = claim(b, group, janet.id)

    assert res.status_code == 400
    assert res.json()["code"] == "member_already_claimed"
    assert Member.objects.values().get(pk=janet.id) == before
    assert session_ids(b) == []
    assert b.get(f"/api/groups/{group.id}/").status_code == 404


def test_claiming_an_unclaimed_member_succeeds(flat):
    group, janet, _ = flat
    a = APIClient()
    res = claim(a, group, janet.id)
    assert res.status_code == 200
    assert res.json() == {"group_id": group.id, "member_id": janet.id}
    assert Member.objects.get(pk=janet.id).guest_claimed_at is not None
    assert session_ids(a) == [janet.id]
    detail = a.get(f"/api/groups/{group.id}/")
    assert detail.status_code == 200 and detail.json()["my_member_id"] == janet.id
    assert a.get(f"/api/groups/{group.id}/expenses/").json()["results"][0]["amount_cents"] == 3000


def test_unclaimed_members_listed_in_join_preview(flat):
    group, janet, cami = flat
    preview = APIClient().get(f"/api/join/{group.share_token}/").json()
    assert preview["unclaimed_members"] == [
        {"id": janet.id, "display_name": "Janet"},
        {"id": cami.id, "display_name": "Cami"},
    ]
    assert preview["member_names"] == ["Ann", "Janet", "Cami"]


def test_claimed_member_disappears_from_join_preview(flat):
    group, janet, cami = flat
    claim(APIClient(), group, janet.id)
    preview = APIClient().get(f"/api/join/{group.share_token}/").json()
    assert preview["unclaimed_members"] == [{"id": cami.id, "display_name": "Cami"}]


def test_claim_member_of_other_group_is_404(world, flat):
    group, _, _ = flat
    res = claim(APIClient(), group, world.gus.id)
    assert res.status_code == 404
    assert Member.objects.get(pk=world.gus.id).claim_state == "guest"


def test_claim_unknown_token_is_404(flat):
    _, janet, _ = flat
    res = APIClient().post("/api/join/nope/claim", {"member_id": janet.id}, format="json")
    assert res.status_code == 404


def test_signed_in_claim_uses_profile(world, flat):
    group, janet, _ = flat
    res = claim(world.login(world.b), group, janet.id)
    assert res.status_code == 200
    assert Member.objects.get(pk=janet.id).profile_id == world.b.id
    assert GroupLink.objects.get(profile=world.b, sub_group=group).active is True


def test_signed_in_claim_refused_when_profile_already_in_group(world, flat):
    group, janet, _ = flat
    res = claim(world.login(world.a), group, janet.id)
    assert res.status_code == 400 and res.json()["code"] == "profile_already_in_group"
    assert Member.objects.get(pk=janet.id).claim_state == "unclaimed"


def test_profile_claim_race_into_unique_constraint_is_400_not_500(world, flat, monkeypatch):
    group, janet, _ = flat
    Member.objects.create(group=group, display_name="Bea", profile=world.b)
    monkeypatch.setattr(groups, "_profile_in_group", lambda profile, group: False)
    res = claim(world.login(world.b), group, janet.id)
    assert res.status_code == 400 and res.json()["code"] == "profile_already_in_group"
    assert Member.objects.get(pk=janet.id).claim_state == "unclaimed"


def test_guest_session_cannot_claim_a_second_member_in_same_group(flat):
    group, janet, cami = flat
    a = APIClient()
    claim(a, group, janet.id)
    res = claim(a, group, cami.id)
    assert res.status_code == 400 and res.json()["code"] == "already_in_group"
    assert session_ids(a) == [janet.id]


def test_claim_without_csrf_token_is_403_for_signed_in_and_guest_succeeds(world, flat):
    group, janet, _ = flat
    strict = APIClient(enforce_csrf_checks=True)
    strict.force_login(world.b.user)
    assert claim(strict, group, janet.id).status_code == 403
    assert claim(APIClient(), group, janet.id).status_code == 200


def test_any_member_can_add_placeholder_including_guest(world):
    guest = world.guest_client()
    res = guest.post(
        f"/api/groups/{world.rome.id}/members/", {"display_name": "Janet"}, format="json"
    )
    assert res.status_code == 201
    assert res.json()["status"] == "unclaimed" and res.json()["profile_id"] is None


def test_add_placeholder_with_taken_name_is_refused(world, flat):
    group, _, _ = flat
    res = world.login(world.a).post(
        f"/api/groups/{group.id}/members/", {"display_name": "Janet"}, format="json"
    )
    assert res.status_code == 400 and res.json()["code"] == "name_taken"


def test_add_placeholder_blank_name_is_refused(world, flat):
    group, _, _ = flat
    res = world.login(world.a).post(
        f"/api/groups/{group.id}/members/", {"display_name": "   "}, format="json"
    )
    assert res.status_code == 400
    assert Member.objects.filter(group=group).count() == 3


def test_add_placeholder_by_non_member_is_404(world, flat):
    group, _, _ = flat
    res = world.login(world.c).post(
        f"/api/groups/{group.id}/members/", {"display_name": "Zed"}, format="json"
    )
    assert res.status_code == 404


def test_group_detail_member_status_joined_guest_unclaimed(world, flat):
    group, janet, _ = flat
    claim(APIClient(), group, janet.id)
    rows = world.login(world.a).get(f"/api/groups/{group.id}/").json()["members"]
    assert [(m["display_name"], m["status"], m["is_guest"]) for m in rows] == [
        ("Ann", "joined", False),
        ("Janet", "guest", True),
        ("Cami", "unclaimed", True),
    ]


def test_balances_list_both_placeholders_before_they_join(world, flat):
    group, janet, cami = flat
    ann = world.member(world.a, group)
    nets = world.login(world.a).get(f"/api/groups/{group.id}/balances/").json()["nets"]
    assert nets == {str(ann.id): 2000, str(janet.id): -1000, str(cami.id): -1000}


def _register(client, email="janet@example.com", name="Janet"):
    return client.post(
        "/api/auth/register",
        {"email": email, "password": PASSWORD, "display_name": name},
        format="json",
    )


def test_register_attaches_guest_member_same_id_and_splits(flat):
    group, janet, _ = flat
    splits_before = list(
        Expense.objects.filter(group=group).values_list("splits__member_id", "splits__owed_cents")
    )
    c = APIClient()
    claim(c, group, janet.id)

    res = _register(c)

    assert res.status_code == 200
    for me in (res.json(), c.get("/api/me").json()):
        assert me["authenticated"] is True
        assert me["guest_memberships"] == []
        assert me["guest_refused"] == []
        assert me["profile"]["main_group_id"] is None
    janet.refresh_from_db()
    assert janet.profile_id == res.json()["profile"]["id"]
    assert session_ids(c) == []
    assert (
        list(
            Expense.objects.filter(group=group).values_list(
                "splits__member_id", "splits__owed_cents"
            )
        )
        == splits_before
    )
    listed = c.get("/api/groups/").json()
    assert [(g["id"], g["is_main"], g["link_active"]) for g in listed] == [(group.id, False, None)]
    detail = c.get(f"/api/groups/{group.id}/").json()
    assert detail["my_member_id"] == janet.id
    assert GroupLink.objects.filter(profile_id=janet.profile_id).count() == 0


def test_login_attaches_guest_member(world, flat):
    group, janet, _ = flat
    c = APIClient()
    claim(c, group, janet.id)
    res = c.post("/api/auth/login", {"email": "c@example.com", "password": PASSWORD}, format="json")
    assert res.status_code == 200 and res.json()["guest_refused"] == []
    assert Member.objects.get(pk=janet.id).profile_id == world.c.id
    assert session_ids(c) == []


def test_google_sign_in_attaches_guest_member(world, flat, settings, monkeypatch):
    settings.GOOGLE_CLIENT_ID = "client-id"
    claims = {"email": "c@example.com", "sub": "sub-c", "name": "Cyd", "email_verified": True}
    monkeypatch.setattr(google, "verify_id_token", lambda token: claims)
    group, janet, _ = flat
    c = APIClient()
    claim(c, group, janet.id)
    res = c.post("/api/auth/google", {"id_token": "tok"}, format="json")
    assert res.status_code == 200
    assert Member.objects.get(pk=janet.id).profile_id == world.c.id


def test_login_refuses_takeover_when_profile_already_in_group_and_keeps_guest(world, flat):
    group, janet, _ = flat
    c = APIClient()
    claim(c, group, janet.id)
    res = c.post("/api/auth/login", {"email": "a@example.com", "password": PASSWORD}, format="json")
    assert res.status_code == 200
    assert res.json()["guest_refused"] == [
        {"member_id": janet.id, "group_id": group.id, "code": "profile_already_in_group"}
    ]
    assert res.json()["guest_memberships"] == [janet.id]
    assert Member.objects.get(pk=janet.id).claim_state == "guest"
    assert session_ids(c) == [janet.id]


def test_attach_applies_group_link_rule(world, flat):
    group, janet, _ = flat
    c = APIClient()
    claim(c, group, janet.id)
    c.post("/api/auth/login", {"email": "b@example.com", "password": PASSWORD}, format="json")
    link = GroupLink.objects.get(profile=world.b, sub_group=group)
    assert (link.main_group_id, link.active) == (world.home.id, True)


def test_guest_logout_makes_name_claimable_again(flat):
    group, janet, _ = flat
    c = APIClient()
    claim(c, group, janet.id)
    assert c.post("/api/auth/logout").status_code == 200
    preview = APIClient().get(f"/api/join/{group.share_token}/").json()
    assert {"id": janet.id, "display_name": "Janet"} in preview["unclaimed_members"]
    assert claim(APIClient(), group, janet.id).status_code == 200


def test_signed_in_logout_does_not_release_joined_member(world, flat):
    group, _, _ = flat
    api = world.login(world.a)
    api.post("/api/auth/logout")
    assert world.member(world.a, group).claim_state == "joined"
    names = [
        m["display_name"]
        for m in APIClient().get(f"/api/join/{group.share_token}/").json()["unclaimed_members"]
    ]
    assert "Ann" not in names
