import datetime

import pytest

from ledger.models import Expense, RecurringRule
from ledger.services import recurring

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 10, 18)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("ledger.api.views.today", lambda: TODAY)


def base(world, **over):
    body = {
        "description": "Rent",
        "amount_cents": 90000,
        "payer": world.member(world.a, world.home).id,
        "split_type": "equal",
        "split_params": {},
        "category": world.groceries.id,
        "frequency": "monthly",
        "day_of_month": 1,
        "start_date": "2026-10-01",
    }
    body.update(over)
    return body


def url(world, suffix=""):
    return f"/api/groups/{world.home.id}/recurring/{suffix}"


def test_recurring_create_pause_skip_resume_roundtrip(world, api_a):
    created = api_a.post(url(world), base(world), format="json")
    assert created.status_code == 201, created.content
    rid = created.json()["id"]
    rule = RecurringRule.objects.get(pk=rid)
    # the same inputs through the service give the same cursor
    expected = recurring.first_occurrence(datetime.date(2026, 10, 1), rule)
    assert created.json()["next_date"] == expected.isoformat() == "2026-10-01"

    paused = api_a.post(url(world, f"{rid}/pause")).json()
    assert paused["paused"] is True and paused["next_date"] == "2026-10-01"

    # Skipping while paused is refused (test_api_skip_paused_rule_is_400_with_detail), so the
    # roundtrip resumes first; the property "skip works while paused" is dropped on purpose.
    resumed = api_a.post(url(world, f"{rid}/resume")).json()
    assert resumed["paused"] is False and resumed["next_date"] == "2026-11-01"

    skipped = api_a.post(url(world, f"{rid}/skip")).json()
    rule.refresh_from_db()
    assert (
        skipped["next_date"]
        == recurring.next_occurrence(datetime.date(2026, 11, 1), rule).isoformat()
        == "2026-12-01"
    )
    assert [r["id"] for r in api_a.get(url(world)).json()] == [rid]


def test_recurring_resume_jumps_to_first_occurrence_from_today(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    api_a.post(url(world, f"{rid}/pause"))
    resumed = api_a.post(url(world, f"{rid}/resume")).json()
    assert resumed["next_date"] == "2026-11-01"  # today is Oct 18: Oct 1 is not back-filled


def test_recurring_patch_amount_does_not_touch_existing_expenses(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    rule = RecurringRule.objects.get(pk=rid)
    recurring.generate_due(datetime.date(2026, 10, 1))
    assert Expense.objects.filter(recurring_rule=rule).count() == 1
    res = api_a.patch(url(world, f"{rid}/"), {"amount_cents": 95000}, format="json")
    assert res.status_code == 200 and res.json()["amount_cents"] == 95000
    assert Expense.objects.get(recurring_rule=rule).amount_cents == 90000


def test_recurring_delete_hides_rule(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    assert api_a.delete(url(world, f"{rid}/")).status_code == 204
    assert api_a.get(url(world)).json() == []
    assert api_a.patch(url(world, f"{rid}/"), {"amount_cents": 1}, format="json").status_code == 404


def test_recurring_rule_of_other_group_is_404(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    other = f"/api/groups/{world.rome.id}/recurring/{rid}/"
    assert api_a.patch(other, {"amount_cents": 1}, format="json").status_code == 404
    assert api_a.post(other + "skip").status_code == 404
    assert RecurringRule.objects.get(pk=rid).amount_cents == 90000


def test_recurring_refuses_payer_outside_group_and_bad_schedule(world, api_a):
    bad = api_a.post(
        url(world), base(world, payer=world.member(world.a, world.rome).id), format="json"
    )
    assert bad.status_code == 400 and bad.json()["code"] == "not_a_member"
    bad = api_a.post(url(world), base(world, frequency="yearly"), format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_month"
    ok = api_a.post(url(world), base(world, frequency="yearly", month=3), format="json")
    assert ok.status_code == 201


def test_api_skip_paused_rule_is_400_with_detail(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    api_a.post(url(world, f"{rid}/pause"))
    refused = api_a.post(url(world, f"{rid}/skip"))
    assert refused.status_code == 400
    assert refused.json()["code"] == "rule_paused" and refused.json()["detail"]
    assert RecurringRule.objects.get(pk=rid).next_date == datetime.date(2026, 10, 1)


def test_api_skip_active_rule_advances_cursor(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    skipped = api_a.post(url(world, f"{rid}/skip"))
    assert skipped.status_code == 200 and skipped.json()["next_date"] == "2026-11-01"


def test_expense_out_carries_recurring_rule_id_or_null(world, api_a):
    rid = api_a.post(url(world), base(world), format="json").json()["id"]
    recurring.generate_due(TODAY)
    res = api_a.post(
        f"/api/groups/{world.home.id}/expenses/",
        world.expense_body(world.home, world.a, amount_cents=1000, description="Taxi"),
        format="json",
    )
    assert res.status_code == 201, res.content
    rows = api_a.get(f"/api/groups/{world.home.id}/expenses/").json()["results"]
    by_description = {r["description"]: r["recurring_rule"] for r in rows}
    assert by_description["Rent"] == rid
    assert all(v is None for k, v in by_description.items() if k != "Rent")


def test_recurring_status_returns_last_run_or_null(world, api_a):
    status_url = url(world, "status/")
    assert api_a.get(status_url).json() == {"last_run_at": None}
    at = datetime.datetime(2026, 10, 18, 7, 13, tzinfo=datetime.UTC)
    recurring.record_job_run("run_daily", at)
    assert api_a.get(status_url).json()["last_run_at"].startswith("2026-10-18T07:13:00")


def test_recurring_status_requires_membership(world, api_a, api_c):
    assert api_a.get(url(world, "status/")).status_code == 200
    assert api_c.get(url(world, "status/")).status_code == 404
