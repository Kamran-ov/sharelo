import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.services.auth import register
from ledger.models import Category, Group, GroupLink

pytestmark = pytest.mark.django_db


def new_user(name="d"):
    profile = register(f"{name}@example.com", "correct-horse-battery-9", name.title())
    client = APIClient()
    client.force_login(profile.user)
    return profile, client


def test_first_group_becomes_main_group(db):
    profile, client = new_user()
    res = client.post("/api/groups/", {"name": "Home", "currency": "EUR"}, format="json")
    assert res.status_code == 201
    assert res.json()["is_main"] is True
    profile.refresh_from_db()
    assert profile.main_group_id == res.json()["id"]
    assert GroupLink.objects.count() == 0


def test_second_group_is_linked_active(db):
    profile, client = new_user()
    client.post("/api/groups/", {"name": "Home", "currency": "EUR"}, format="json")
    res = client.post("/api/groups/", {"name": "Trip", "currency": "EUR"}, format="json")
    assert res.status_code == 201
    assert res.json()["is_main"] is False
    assert res.json()["link_active"] is True
    assert GroupLink.objects.filter(profile=profile, sub_group_id=res.json()["id"]).exists()


def test_as_main_on_second_group_is_refused_and_main_unchanged(db):
    profile, client = new_user()
    first = client.post("/api/groups/", {"name": "Home", "currency": "EUR"}, format="json")
    res = client.post(
        "/api/groups/", {"name": "Other", "currency": "EUR", "as_main": True}, format="json"
    )
    assert res.status_code == 400
    assert res.json()["code"] == "main_group_exists"
    profile.refresh_from_db()
    assert profile.main_group_id == first.json()["id"]
    assert Group.objects.count() == 1
    assert GroupLink.objects.count() == 0


def test_guest_cannot_create_group_or_set_link(world, api_a):
    guest = world.guest_client()
    res = guest.post("/api/groups/", {"name": "X", "currency": "EUR"}, format="json")
    assert res.status_code == 401 and res.json()["code"] == "not_authenticated"
    res = guest.post(f"/api/groups/{world.rome.id}/link", {"active": False}, format="json")
    assert res.status_code == 401
    ok = api_a.post("/api/groups/", {"name": "X", "currency": "EUR"}, format="json")
    assert ok.status_code == 201


def test_invalid_currency_and_blank_name_are_refused(db):
    _, client = new_user()
    assert (
        client.post("/api/groups/", {"name": "X", "currency": "eur"}, format="json").status_code
        == 400
    )
    assert (
        client.post("/api/groups/", {"name": "", "currency": "EUR"}, format="json").status_code
        == 400
    )


def test_link_toggle_roundtrip(world, api_b):
    url = f"/api/groups/{world.rome.id}"
    assert api_b.get(url + "/").json()["link_active"] is True
    assert api_b.post(url + "/link", {"active": False}, format="json").json() == {
        "link_active": False
    }
    assert api_b.get(url + "/").json()["link_active"] is False
    assert api_b.post(url + "/link", {"active": True}, format="json").json() == {
        "link_active": True
    }


def test_link_on_main_group_is_refused(world, api_a):
    res = api_a.post(f"/api/groups/{world.home.id}/link", {"active": False}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "no_link"


def test_group_detail_fields(world, api_a):
    res = api_a.get(f"/api/groups/{world.home.id}/").json()
    assert res["is_main"] is True and res["link_active"] is None
    assert res["my_member_id"] == world.member(world.a, world.home).id
    assert [m["display_name"] for m in res["members"]] == ["Ann", "Bea"]
    rome = api_a.get(f"/api/groups/{world.rome.id}/").json()
    assert rome["is_main"] is False and rome["link_active"] is True
    assert [m["is_guest"] for m in rome["members"]] == [False, False, True]
    assert rome["share_token"] == world.rome.share_token


def test_group_list_has_profile_and_guest_groups(world, api_c):
    ids = [g["id"] for g in world.login(world.a).get("/api/groups/").json()]
    assert ids == [world.rome.id, world.home.id]
    guest_ids = [g["id"] for g in world.guest_client().get("/api/groups/").json()]
    assert guest_ids == [world.rome.id]
    assert api_c.get("/api/groups/").json() == []
    assert APIClient().get("/api/groups/").json() == []


def test_categories_tree_is_two_levels(db):
    tree = APIClient().get("/api/categories/").json()
    assert tree and all(set(c) == {"id", "name", "children"} for c in tree)
    food = next(c for c in tree if c["name"] == "Food and drink")
    assert "Groceries" in [k["name"] for k in food["children"]]
    assert all("children" not in k for k in food["children"])
    assert Category.objects.filter(parent__isnull=True).count() == len(tree)


def test_category_defaults_roundtrip_stores_half_as_equal(world, api_a):
    url = f"/api/groups/{world.home.id}/category-defaults/"
    cat = world.groceries.id
    res = api_a.put(url, {str(cat): {"preset": "half"}}, format="json")
    assert res.status_code == 200
    assert api_a.get(url).json() == {str(cat): {"preset": "equal", "params": {}}}
    assert api_a.put(url, {}, format="json").status_code == 200
    assert api_a.get(url).json() == {}


def test_category_defaults_bad_preset_refused_and_nothing_saved(world, api_a):
    url = f"/api/groups/{world.home.id}/category-defaults/"
    cat = str(world.groceries.id)
    bad = api_a.put(url, {cat: {"preset": "nonsense"}}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "unknown_preset"
    assert api_a.get(url).json() == {}
    good = api_a.put(url, {cat: {"preset": "personal"}}, format="json")
    assert good.status_code == 200


def test_group_list_carries_link_active_per_group(world, api_a):
    rome_link = GroupLink.objects.get(profile=world.a, sub_group=world.rome)
    rows = {g["id"]: g for g in api_a.get("/api/groups/").json()}
    assert rows[world.home.id]["link_active"] is None
    assert rows[world.rome.id]["link_active"] is True
    rome_link.active = False
    rome_link.save()
    rows = {g["id"]: g for g in api_a.get("/api/groups/").json()}
    assert rows[world.rome.id]["link_active"] is False
    guest_rows = world.guest_client().get("/api/groups/").json()
    assert [g["link_active"] for g in guest_rows] == [None]


def test_group_list_query_count_is_constant_with_link_field(db):
    profile, client = new_user("q")
    client.post("/api/groups/", {"name": "Home", "currency": "EUR"}, format="json")

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/groups/").status_code == 200
        return len(ctx)

    for i in range(2):
        client.post("/api/groups/", {"name": f"T{i}", "currency": "EUR"}, format="json")
    few = count_queries()
    for i in range(7):
        client.post("/api/groups/", {"name": f"U{i}", "currency": "EUR"}, format="json")
    assert count_queries() == few
