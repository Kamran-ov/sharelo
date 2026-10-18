---
id: 004
title: Exchange rates and conversion to group currency
status: done
risk: normal
depends_on: [001]
pr: 8
---

## Goal
A foreign-currency expense keeps its original amount and is converted to the group's currency
at that day's rate. Rates are stored once per currency per day against EUR.

## Scope
- `ExchangeRate` model: date, currency, `rate_to_eur` (Decimal(18,8)); unique (date, currency).
- `ledger/services/rates.py`:
  - `fetch_ecb_rates(date=None)` — downloads the ECB daily reference rates
    (https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip for history, or the daily XML)
    and upserts them. Network call isolated behind one function so tests can stub it.
  - `rate(date, from_currency, to_currency) -> Decimal` — via EUR. Same currency → 1.
    Uses the latest rate on or before `date` (weekends/holidays). Raises `LedgerError`
    code `no_rate` if none exists within 7 days before `date`.
  - `convert(amount_cents, date, from_currency, to_currency) -> int` — round half-even.
- Management command `fetch_rates [--since YYYY-MM-DD]`.
- Hook into `create_expense`: if `original_currency != group.currency`, compute `rate_used`
  and `amount_cents` from `original_amount_cents`; allow an explicit `rate_used` override for
  currencies the ECB does not publish.

## Out of scope
- Scheduling the fetch (comes with the recurring job in ticket 007).
- User "home currency" for analytics (analytics step, later).

## Acceptance
- With stubbed rates USD 1.10 and GBP 0.85 on 2026-03-02, $60 on 2026-03-02 in a EUR group →
  5455 cents (60/1.10 = 54.545… → 5455); £10 → 1176 cents.
- Cross rate USD→GBP goes through EUR and equals (1/1.10)*0.85 within 1e-8.
- A Saturday date uses Friday's rate; a date with no rate in the previous 7 days raises `no_rate`.
- Explicit `rate_used` override is stored and used; a missing rate for an unknown currency
  without override raises.
- The ECB parser handles the real file format (one fixture file committed under `tests/fixtures/`).

## Notes
- The ECB publishes ~30 currencies. Anything else needs a manual rate on the expense; the UI
  will ask for it (later ticket).
