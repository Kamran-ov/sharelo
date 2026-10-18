import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger.models import Category, CategoryDefault, ExchangeRate, Expense
from ledger.services import expenses

pytestmark = pytest.mark.django_db


def url(world, group=None, suffix=""):
    return f"/api/groups/{(group or world.home).id}/expenses/{suffix}"


def post(client, world, group=None, payer=None, **over):
    group = group or world.home
    return client.post(
        url(world, group), world.expense_body(group, payer or world.a, **over), format="json"
    )


def splits_of(res):
    return {s["member"]: s["owed_cents"] for s in res.json()["splits"]}


def test_half_preset_splits_5000_into_2500_2500(world, api_a):
    res = post(api_a, world)
    assert res.status_code == 201, res.content
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    assert splits_of(res) == {ann.id: 2500, bea.id: 2500}
    assert res.json()["payers"] == [{"member": ann.id, "paid_cents": 5000}]
    assert res.json()["split_type"] == "equal"
    assert res.json()["rate_used"] == "1.00000000"


def test_omitted_preset_uses_category_default(world, api_a):
    ann = world.member(world.a, world.home)
    CategoryDefault.objects.create(
        group=world.home, category=world.groceries, split_type="personal", split_params={}
    )
    body = world.expense_body(world.home, world.a)
    del body["preset"]
    res = api_a.post(url(world), body, format="json")
    assert splits_of(res) == {ann.id: 5000}
    CategoryDefault.objects.all().delete()
    res = api_a.post(url(world), body, format="json")
    assert sorted(splits_of(res).values()) == [2500, 2500]


def test_percentage_preset_maps_percent_payer_to_basis_points(world, api_a):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    res = post(api_a, world, amount_cents=10001, preset="percentage", params={"percent_payer": 30})
    assert res.status_code == 201, res.content
    assert splits_of(res) == {ann.id: 3001, bea.id: 7000}  # leftover cent: lowest member id


def test_percent_payer_non_integer_refused(world, api_a):
    for bad in (30.5, "30", True, 101, -1):
        res = post(api_a, world, preset="percentage", params={"percent_payer": bad})
        assert res.status_code == 400 and res.json()["code"] == "invalid_params", bad
    assert post(api_a, world, preset="percentage", params={"percent_payer": 30}).status_code == 201


def test_percent_payer_in_three_member_group_refused(world, api_a):
    res = post(api_a, world, world.rome, preset="percentage", params={"percent_payer": 30})
    assert res.status_code == 400 and res.json()["code"] == "invalid_params"


def test_half_with_three_members_refused(world, api_a):
    res = post(api_a, world, world.rome, preset="half")
    assert res.status_code == 400 and res.json()["code"] == "invalid_params"
    ok = post(api_a, world, world.rome, preset="equal")
    assert ok.status_code == 201 and sorted(splits_of(ok).values()) == [1666, 1667, 1667]


def test_foreign_currency_stores_rate_used_and_converted_amount(world, api_a):
    ExchangeRate.objects.create(
        date=datetime.date(2026, 10, 1), currency="USD", rate_to_eur=Decimal("1.2")
    )
    body = world.expense_body(
        world.home, world.a, original_currency="USD", original_amount_cents=1200
    )
    del body["amount_cents"]
    res = api_a.post(url(world), body, format="json")
    assert res.status_code == 201, res.content
    assert res.json()["amount_cents"] == 1000
    assert res.json()["rate_used"] == "0.83333333"
    assert res.json()["original_amount_cents"] == 1200 and res.json()["original_currency"] == "USD"
    assert sorted(splits_of(res).values()) == [500, 500]
    body["date"] = "2026-01-01"
    no_rate = api_a.post(url(world), body, format="json")
    assert no_rate.status_code == 400 and no_rate.json()["code"] == "no_rate"


def test_invalid_sums_return_service_code_400(world, api_a):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    base = {
        "description": "Rent",
        "amount_cents": 1000,
        "date": "2026-10-01",
        "category": world.groceries.id,
        "split_type": "exact",
        "payers": {str(ann.id): 1000},
        "splits": {str(ann.id): 400, str(bea.id): 500},
    }
    bad = api_a.post(url(world), base, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "splits_sum_mismatch"
    base["payers"] = {str(ann.id): 900}
    base["splits"] = {str(ann.id): 400, str(bea.id): 600}
    assert api_a.post(url(world), base, format="json").json()["code"] == "payers_sum_mismatch"
    base["payers"] = {str(ann.id): 1000}
    ok = api_a.post(url(world), base, format="json")
    assert ok.status_code == 201 and splits_of(ok) == {ann.id: 400, bea.id: 600}


def test_amounts_must_be_json_integers(world, api_a):
    for bad in (50.0, "50", True):
        assert post(api_a, world, amount_cents=bad).status_code == 400, bad


def test_preset_and_payers_together_refused(world, api_a):
    ann = world.member(world.a, world.home)
    res = post(
        api_a,
        world,
        payers={str(ann.id): 5000},
        splits={str(ann.id): 5000},
        split_type="personal",
    )
    assert res.status_code == 400 and res.json()["code"] == "invalid_request"


def test_payer_from_another_group_is_refused(world, api_a):
    res = post(api_a, world, payer_member=world.member(world.a, world.rome).id)
    assert res.status_code == 400 and res.json()["code"] == "member_not_in_group"


def make_expense(world, group, day, category=None, amount=100):
    ann = world.member(world.a, group)
    return expenses.create_expense(
        group,
        description=f"E{day}",
        amount_cents=amount,
        currency="EUR",
        date=day,
        category=category or world.groceries,
        payers={ann.id: amount},
        splits={ann.id: amount},
        split_type="personal",
    )


def test_expense_list_paginates_50_and_orders_newest_first(world, api_a):
    start = datetime.date(2026, 1, 1)
    for i in range(120):
        make_expense(world, world.home, start + datetime.timedelta(days=i))
    first = api_a.get(url(world)).json()
    assert first["count"] == 120 and first["page"] == 1 and len(first["results"]) == 50
    assert first["results"][0]["date"] == "2026-04-30"
    dates = [r["date"] for r in first["results"]]
    assert dates == sorted(dates, reverse=True)
    assert len(api_a.get(url(world) + "?page=3").json()["results"]) == 20
    assert api_a.get(url(world) + "?page=4").status_code == 404
    assert api_a.get(url(world) + "?page=0").status_code == 400
    assert api_a.get(url(world) + "?page=x").status_code == 400


def test_expense_list_filters_from_to_category_member(world, api_a):
    dining = Category.objects.get(name="Dining out")
    food = dining.parent
    rent = Category.objects.get(name="Rent")
    make_expense(world, world.home, datetime.date(2026, 3, 1), dining)
    make_expense(world, world.home, datetime.date(2026, 4, 1), rent)
    bea = world.member(world.b, world.home)
    ann = world.member(world.a, world.home)
    both = expenses.create_expense(
        world.home,
        description="Split",
        amount_cents=200,
        currency="EUR",
        date=datetime.date(2026, 5, 1),
        category=rent,
        payers={ann.id: 200},
        splits={ann.id: 100, bea.id: 100},
        split_type="equal",
    )

    def descriptions(query):
        return [r["description"] for r in api_a.get(url(world) + query).json()["results"]]

    assert descriptions("?from=2026-04-01") == ["Split", "E2026-04-01"]
    assert descriptions("?to=2026-03-31") == ["E2026-03-01"]
    assert descriptions(f"?category={food.id}") == ["E2026-03-01"]  # parent matches its children
    assert descriptions(f"?category={dining.id}") == ["E2026-03-01"]
    assert descriptions(f"?member={bea.id}") == [both.description]
    assert descriptions("?from=2026-06-01&to=2026-01-01") == []
    assert api_a.get(url(world) + "?from=garbage").status_code == 400


def test_expense_list_query_count_is_constant_with_category_filter(world, api_a):
    food = Category.objects.get(name="Groceries").parent

    def count(n_rows):
        for i in range(n_rows):
            make_expense(world, world.home, datetime.date(2026, 1, 1) + datetime.timedelta(days=i))
        with CaptureQueriesContext(connection) as ctx:
            res = api_a.get(url(world) + f"?category={food.id}")
        assert len(res.json()["results"]) == min(Expense.objects.count(), 50)
        return len(ctx)

    assert count(3) == count(27)


def test_deleted_expense_disappears_from_list_and_repeat_delete_is_204(world, api_a):
    eid = post(api_a, world).json()["id"]
    assert api_a.delete(url(world, suffix=f"{eid}/")).status_code == 204
    assert api_a.get(url(world)).json()["count"] == 0
    assert api_a.delete(url(world, suffix=f"{eid}/")).status_code == 204
    assert (
        api_a.patch(url(world, suffix=f"{eid}/"), {"description": "x"}, format="json").status_code
        == 404
    )
    assert Expense.all_objects.get(pk=eid).deleted_at is not None


def test_patch_description_keeps_splits(world, api_a):
    created = post(api_a, world).json()
    res = api_a.patch(
        url(world, suffix=f"{created['id']}/"), {"description": "Lunch"}, format="json"
    )
    assert res.status_code == 200
    assert res.json()["description"] == "Lunch"
    assert res.json()["splits"] == created["splits"] and res.json()["payers"] == created["payers"]


def test_patch_amount_recomputes_splits_and_balances(world, api_a):
    eid = post(api_a, world).json()["id"]
    bal = f"/api/groups/{world.home.id}/balances/"
    ann = str(world.member(world.a, world.home).id)
    assert api_a.get(bal).json()["nets"][ann] == 2500
    res = api_a.patch(url(world, suffix=f"{eid}/"), {"amount_cents": 8001}, format="json")
    assert res.status_code == 200, res.content
    assert splits_of(res)[int(ann)] == 4001
    assert api_a.get(bal).json()["nets"][ann] == 4000


def test_patch_amount_only_on_exact_expense_is_400(world, api_a):
    res = post(
        api_a,
        world,
        preset="exact",
        params={
            "cents": {
                str(world.member(world.a, world.home).id): 1000,
                str(world.member(world.b, world.home).id): 4000,
            }
        },
    )
    assert res.status_code == 201, res.content
    target = url(world, suffix=f"{res.json()['id']}/")
    bad = api_a.patch(target, {"amount_cents": 6000}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_request"
    assert Expense.objects.get(pk=res.json()["id"]).amount_cents == 5000


def test_patch_amount_with_splits_supplied_recomputes_and_changes_balances(world, api_a):
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    res = post(
        api_a, world, preset="exact", params={"cents": {str(ann.id): 1000, str(bea.id): 4000}}
    )
    target = url(world, suffix=f"{res.json()['id']}/")
    body = {
        "amount_cents": 6000,
        "payers": {str(ann.id): 6000},
        "splits": {str(ann.id): 1500, str(bea.id): 4500},
        "split_type": "exact",
    }
    ok = api_a.patch(target, body, format="json")
    assert ok.status_code == 200, ok.content
    assert splits_of(ok) == {ann.id: 1500, bea.id: 4500}
    nets = api_a.get(f"/api/groups/{world.home.id}/balances/").json()["nets"]
    assert nets == {str(ann.id): 4500, str(bea.id): -4500}


def test_patch_amount_on_equal_expense_recomputes_without_a_body_preset(world, api_a):
    eid = post(api_a, world, world.rome, preset="equal").json()["id"]
    res = api_a.patch(url(world, world.rome, f"{eid}/"), {"amount_cents": 3000}, format="json")
    assert res.status_code == 200 and sorted(splits_of(res).values()) == [1000, 1000, 1000]


def test_patch_date_on_foreign_expense_reconverts_at_new_date_rate(world, api_a):
    ExchangeRate.objects.create(
        date=datetime.date(2026, 10, 1), currency="USD", rate_to_eur=Decimal("1.2")
    )
    ExchangeRate.objects.create(
        date=datetime.date(2026, 10, 10), currency="USD", rate_to_eur=Decimal("1.5")
    )
    body = world.expense_body(
        world.home, world.a, original_currency="USD", original_amount_cents=1200
    )
    del body["amount_cents"]
    created = api_a.post(url(world), body, format="json").json()
    assert created["amount_cents"] == 1000
    res = api_a.patch(url(world, suffix=f"{created['id']}/"), {"date": "2026-10-10"}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["rate_used"] == "0.66666667" and res.json()["amount_cents"] == 800
    assert sorted(splits_of(res).values()) == [400, 400]
    assert res.json()["original_amount_cents"] == 1200


def test_patch_date_on_same_currency_expense_keeps_amount(world, api_a):
    created = post(api_a, world).json()
    res = api_a.patch(url(world, suffix=f"{created['id']}/"), {"date": "2026-11-05"}, format="json")
    assert res.status_code == 200
    assert res.json()["amount_cents"] == 5000 and res.json()["date"] == "2026-11-05"
    assert res.json()["splits"] == created["splits"]


def test_patch_date_on_foreign_exact_expense_without_splits_is_400(world, api_a):
    ExchangeRate.objects.create(
        date=datetime.date(2026, 10, 1), currency="USD", rate_to_eur=Decimal("1.2")
    )
    ExchangeRate.objects.create(
        date=datetime.date(2026, 10, 10), currency="USD", rate_to_eur=Decimal("1.5")
    )
    ann, bea = world.member(world.a, world.home), world.member(world.b, world.home)
    body = world.expense_body(
        world.home,
        world.a,
        original_currency="USD",
        original_amount_cents=1200,
        preset="exact",
        params={"cents": {str(ann.id): 400, str(bea.id): 600}},
    )
    del body["amount_cents"]
    created = api_a.post(url(world), body, format="json")
    assert created.status_code == 201, created.content
    res = api_a.patch(
        url(world, suffix=f"{created.json()['id']}/"), {"date": "2026-10-10"}, format="json"
    )
    assert res.status_code == 400 and res.json()["code"] == "invalid_request"
