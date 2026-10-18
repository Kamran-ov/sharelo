import datetime
import inspect
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from ledger.errors import LedgerError
from ledger.models import ExchangeRate
from ledger.services import rates
from ledger.services.expenses import create_expense, create_expense_from_preset

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures"
MON = datetime.date(2026, 3, 2)
FRI = datetime.date(2026, 2, 27)
SAT = datetime.date(2026, 2, 28)
SUN = datetime.date(2026, 3, 1)


@pytest.fixture
def hist_rates(monkeypatch):
    monkeypatch.setattr(
        rates, "_download", lambda url: (FIXTURES / "ecb_hist_snippet.xml").read_text()
    )
    rates.fetch_ecb_rates()


def foreign(group, members, category, **kw):
    return create_expense_from_preset(
        group,
        preset="equal",
        payer_id=members[0].id,
        description="Dinner",
        currency="EUR",
        date=MON,
        category=category,
        **kw,
    )


def refused(code, fn, *args, **kwargs):
    with pytest.raises(LedgerError) as exc:
        fn(*args, **kwargs)
    assert exc.value.code == code


def test_usd_expense_converts_at_that_days_rate(hist_rates, group, members, category):
    usd = foreign(group, members, category, original_amount_cents=6000, original_currency="USD")
    assert usd.amount_cents == 5455
    assert usd.rate_used == Decimal("0.90909091")
    assert usd.original_amount_cents == 6000
    assert sum(p.paid_cents for p in usd.payers.all()) == 5455
    assert sum(s.owed_cents for s in usd.splits.all()) == 5455
    gbp = foreign(group, members, category, original_amount_cents=1000, original_currency="GBP")
    assert gbp.amount_cents == 1176


def test_cross_rate_goes_through_eur(hist_rates):
    cross = rates.rate(MON, "USD", "GBP")
    assert abs(cross - (1 / Decimal("1.10")) * Decimal("0.85")) < Decimal("1e-8")


def test_same_currency_rate_is_one_without_lookup():
    assert ExchangeRate.objects.count() == 0
    assert rates.rate(MON, "USD", "USD") == Decimal(1)
    assert rates.convert(1234, MON, "EUR", "EUR") == 1234


def test_weekend_uses_previous_friday_rate(hist_rates):
    friday = rates.rate(FRI, "USD", "EUR")
    assert rates.rate(SAT, "USD", "EUR") == friday
    assert rates.rate(SUN, "USD", "EUR") == friday
    assert friday != rates.rate(MON, "USD", "EUR")


def test_date_with_no_rate_in_previous_7_days_raises_no_rate(hist_rates):
    assert rates.rate(FRI + datetime.timedelta(days=0), "USD", "EUR")
    # newest rate before 02-26 is none; newest on 03-02 is 7 days old at 03-09, 8 at 03-10
    assert rates.rate(MON + datetime.timedelta(days=7), "USD", "EUR")
    refused("no_rate", rates.rate, MON + datetime.timedelta(days=8), "USD", "EUR")


def test_explicit_rate_override_is_stored_and_used(group, members, category):
    expense = foreign(
        group,
        members,
        category,
        original_amount_cents=10000,
        original_currency="XYZ",
        rate_used=Decimal("0.5"),
    )
    assert (expense.amount_cents, expense.rate_used) == (5000, Decimal("0.5"))


def test_unknown_currency_without_override_raises_no_rate(hist_rates, group, members, category):
    refused(
        "no_rate",
        foreign,
        group,
        members,
        category,
        original_amount_cents=100,
        original_currency="XYZ",
    )


def test_convert_rounds_half_even():
    half = Decimal("0.5")
    assert rates.convert_with_rate(5, half) == 2
    assert rates.convert_with_rate(7, half) == 4
    assert rates.convert_with_rate(-5, half) == -2
    assert rates.convert_with_rate(-7, half) == -4


def test_convert_returns_int(hist_rates):
    assert type(rates.convert(6000, MON, "USD", "EUR")) is int


def test_parse_ecb_fixture_real_format():
    daily = rates.parse_ecb_xml((FIXTURES / "ecb_daily.xml").read_text())
    assert list(daily) == [MON]
    assert daily[MON]["USD"] == Decimal("1.1000") and daily[MON]["PLN"] == Decimal("4.2000")
    hist = rates.parse_ecb_xml((FIXTURES / "ecb_hist_snippet.xml").read_text())
    assert sorted(hist) == [datetime.date(2026, 2, 26), FRI, MON]
    assert hist[FRI]["USD"] == Decimal("1.0800")


def test_fetch_is_idempotent_and_updates_changed_rates(monkeypatch):
    text = (FIXTURES / "ecb_daily.xml").read_text()
    monkeypatch.setattr(rates, "_download", lambda url: text)
    assert rates.fetch_ecb_rates() == 5
    assert rates.fetch_ecb_rates() == 5
    assert ExchangeRate.objects.count() == 5
    monkeypatch.setattr(rates, "_download", lambda url: text.replace("1.1000", "1.2000"))
    rates.fetch_ecb_rates()
    assert ExchangeRate.objects.get(date=MON, currency="USD").rate_to_eur == Decimal("1.2")


def test_fetch_since_drops_earlier_days(monkeypatch):
    monkeypatch.setattr(
        rates, "_download", lambda url: (FIXTURES / "ecb_hist_snippet.xml").read_text()
    )
    assert rates.fetch_ecb_rates(since=FRI) == 10
    assert not ExchangeRate.objects.filter(date__lt=FRI).exists()


def test_fetch_rates_command_since_validates_date(monkeypatch):
    seen = []
    monkeypatch.setattr(rates, "fetch_ecb_rates", lambda since=None: seen.append(since) or 0)
    with pytest.raises(CommandError):
        call_command("fetch_rates", since="2026-13-45")
    assert seen == []
    call_command("fetch_rates", since="2026-03-02")
    assert seen == [MON]


def test_ecb_file_choice_by_since():
    today = datetime.date(2026, 6, 1)
    pick = lambda since: rates._ecb_url(since, today).rsplit("/", 1)[1]  # noqa: E731
    assert pick(None) == "eurofxref-daily.xml"
    assert pick(today - datetime.timedelta(days=30)) == "eurofxref-hist-90d.xml"
    assert pick(today - datetime.timedelta(days=90)) == "eurofxref-hist-90d.xml"
    assert pick(today - datetime.timedelta(days=91)) == "eurofxref-hist.xml"
    assert pick(today - datetime.timedelta(days=400)) == "eurofxref-hist.xml"


def test_inconsistent_original_and_amount_is_refused(group, expense_kwargs):
    kwargs = {**expense_kwargs, "amount_cents": 5000, "payers": {}, "splits": {}}
    ann = next(iter(expense_kwargs["payers"]))
    kwargs["payers"] = {ann: 5000}
    kwargs["splits"] = {ann: 5000}
    refused(
        "rate_mismatch",
        create_expense,
        group,
        **kwargs,
        original_amount_cents=6000,
        original_currency="USD",
        rate_used=Decimal("0.90909091"),
    )


def test_consistent_explicit_amount_and_rate_is_accepted(group, expense_kwargs):
    ann = next(iter(expense_kwargs["payers"]))
    kwargs = {**expense_kwargs, "amount_cents": 5455, "payers": {ann: 5455}, "splits": {ann: 5455}}
    expense = create_expense(
        group,
        **kwargs,
        original_amount_cents=6000,
        original_currency="USD",
        rate_used=Decimal("0.90909091"),
    )
    assert expense.amount_cents == 5455


def test_rate_mismatch_uses_the_rate_as_stored(group, expense_kwargs):
    ann = next(iter(expense_kwargs["payers"]))

    def make(amount):
        kwargs = {**expense_kwargs, "amount_cents": amount, "payers": {ann: amount}}
        kwargs["splits"] = {ann: amount}
        return create_expense(
            group,
            **kwargs,
            original_amount_cents=5,
            original_currency="USD",
            rate_used=Decimal("0.500000004"),
        )

    # unquantized 5 * 0.500000004 rounds to 3, but the stored 8-dp rate 0.5 gives 2 (half-even)
    refused("rate_mismatch", make, 3)
    expense = make(2)
    assert expense.rate_used == Decimal("0.5")


def test_unique_rate_per_date_and_currency(db):
    ExchangeRate.objects.create(date=MON, currency="USD", rate_to_eur=Decimal("1.1"))
    ExchangeRate.objects.create(date=FRI, currency="USD", rate_to_eur=Decimal("1.1"))
    with pytest.raises(IntegrityError), transaction.atomic():
        ExchangeRate.objects.create(date=MON, currency="USD", rate_to_eur=Decimal("1.2"))


def test_rates_module_has_no_float():
    assert "float(" not in inspect.getsource(rates)


@pytest.fixture
def jpy_usd_rates():
    for day, jpy, usd in ((FRI, "160", "1.10"), (datetime.date(2026, 2, 10), "150", "1.08")):
        ExchangeRate.objects.create(date=day, currency="JPY", rate_to_eur=Decimal(jpy))
        ExchangeRate.objects.create(date=day, currency="USD", rate_to_eur=Decimal(usd))


def test_rate_resolver_agrees_with_rate_function(jpy_usd_rates):
    for day in (FRI, SAT, SUN, MON, datetime.date(2026, 2, 10)):
        for pair in (("JPY", "EUR"), ("EUR", "JPY"), ("JPY", "USD")):
            resolve = rates.rate_resolver(*pair, FRI - datetime.timedelta(days=20), MON)
            assert resolve(day) == rates.rate(day, *pair)
    to_usd = rates.range_converter("JPY", "USD", FRI, MON)
    assert to_usd(MON, 123457) == rates.convert(123457, MON, "JPY", "USD")


def test_rate_resolver_refuses_after_8_day_gap(jpy_usd_rates):
    ok = rates.rate_resolver("JPY", "EUR", FRI, FRI + datetime.timedelta(days=8))
    assert ok(FRI + datetime.timedelta(days=7)) == rates.rate(
        FRI + datetime.timedelta(days=7), "JPY", "EUR"
    )
    with pytest.raises(LedgerError) as exc:
        ok(FRI + datetime.timedelta(days=8))
    assert exc.value.code == "no_rate"


def test_rate_resolver_same_currency_and_eur_need_no_queries(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert rates.rate_resolver("EUR", "EUR", FRI, MON)(MON) == 1
        assert rates.rate_resolver("JPY", "JPY", FRI, MON)(MON) == 1


def test_rate_resolver_uses_one_query_for_a_foreign_pair(jpy_usd_rates, django_assert_num_queries):
    with django_assert_num_queries(1):
        resolve = rates.rate_resolver("JPY", "USD", FRI, MON)
        for day in (FRI, SAT, SUN, MON):
            resolve(day)
