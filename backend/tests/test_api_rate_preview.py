import datetime
from decimal import Decimal

import pytest

from ledger.models import ExchangeRate

pytestmark = pytest.mark.django_db

DAY = datetime.date(2026, 10, 1)


def rate_url(world, group=None):
    return f"/api/groups/{(group or world.home).id}/rate/"


def seed_usd(date=DAY):
    ExchangeRate.objects.create(date=date, currency="USD", rate_to_eur=Decimal("1.10"))


def test_rate_preview_returns_the_stored_rate_as_string(world, api_a):
    seed_usd()
    res = api_a.get(rate_url(world), {"currency": "USD", "date": "2026-10-01"})
    assert res.status_code == 200, res.content
    assert res.json() == {"currency": "USD", "date": "2026-10-01", "rate": "0.90909091"}


def test_rate_preview_without_a_rate_is_no_rate_400(world, api_a):
    seed_usd(date=DAY - datetime.timedelta(days=30))
    res = api_a.get(rate_url(world), {"currency": "USD", "date": "2026-10-01"})
    assert res.status_code == 400
    assert res.json()["code"] == "no_rate"


def test_rate_preview_refuses_non_member_with_404(world, api_c):
    seed_usd()
    res = api_c.get(rate_url(world), {"currency": "USD", "date": "2026-10-01"})
    assert res.status_code == 404


def test_rate_preview_same_currency_is_invalid_request(world, api_a):
    res = api_a.get(rate_url(world), {"currency": "EUR", "date": "2026-10-01"})
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_request"


def test_rate_preview_matches_the_rate_the_post_stores(world, api_a):
    seed_usd()
    body = world.expense_body(world.home, world.a)
    del body["amount_cents"]
    res = api_a.post(
        f"/api/groups/{world.home.id}/expenses/",
        {**body, "original_currency": "USD", "original_amount_cents": 10000},
        format="json",
    )
    assert res.status_code == 201, res.content
    preview = api_a.get(rate_url(world), {"currency": "USD", "date": "2026-10-01"}).json()
    assert Decimal(res.json()["rate_used"]) == Decimal(preview["rate"])
    assert res.json()["amount_cents"] == 9091
