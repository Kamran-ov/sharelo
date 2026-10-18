---
id: 008
title: Home analytics rollup — linked sub-groups into the main group
status: in-review
risk: risky
depends_on: [005, 006]
pr:
---

## Goal
A profile's Home analytics include its spending in every linked trip, converted to Home's
currency at each expense's date, either as one line per trip or spread into categories.
Guests and unlinked groups never leak in. Pure query functions; no API, no charts.

## Scope
`ledger/services/home.py`, each taking `(main_group, date_from, date_to, trips="lines"|"spread")`:
- `home_spending_by_member()` → `{member_id: cents}` for the main group's members. A member
  with a profile P contributes: its owed shares in the main group + the owed shares of P's
  member in every sub-group where P has an ACTIVE `GroupLink` to this main group. Each
  sub-group expense is converted from the sub-group currency to the main currency with
  `rates.convert(..., expense.date, ...)`. Members without a profile contribute main-group
  shares only.
- `home_spending_by_category(level=1|2)` → `{key: cents}`. With `trips="lines"` every linked
  sub-group becomes one pseudo-row keyed `("trip", group_id)` with the group name; with
  `trips="spread"` its expenses land in their real categories.
- `home_spending_by_month()` → `{"YYYY-MM": cents}`.
- `home_trip_breakdown(main_group, trip_group)` → per-member, per-category totals of that one
  trip in the main currency (drill-down from one trip line).
- Rule for "linking is per person": if only one partner's link is active, only that partner's
  trip shares roll in. If a trip member has a profile whose main group is a different group,
  their shares never appear here.
- Aggregate in the ORM by `(expense.date, currency)` first, then convert each aggregate
  (not each row). Query count per function is bounded by the number of linked sub-groups,
  asserted with `django_assert_max_num_queries`.
- Move-to-Home settlements are settlements, not spending: they must not appear.

## Out of scope
- Charts, API endpoints (analytics API comes with the analytics step of the plan).
- Rates missing for a date: `convert` raises `LedgerError(no_rate)`; propagate it, don't hide it.

## Acceptance
- Fixture: Home (EUR) with A and B (profiles), trip Rome (EUR) with A, B and guest G; trip
  Tokyo (JPY) with A only, B's link to Tokyo inactive (B is not in Tokyo).
  Rome dinner 9000 split equal 3 ways; Tokyo 100000 JPY personal for A; Home groceries 5000
  50/50; one rate row JPY on the Tokyo date.
  - `home_spending_by_member`: A = 2500 + 3000 + convert(100000 JPY), B = 2500 + 3000,
    G absent.
  - `trips="lines"`: Rome row = 6000 (A+B only, the guest's 3000 excluded), Tokyo row =
    convert(100000 JPY); groceries in Food and drink = 5000.
  - `trips="spread"`: Dining out = 6000, Groceries = 5000, Tokyo's category gets the converted
    amount; the two modes sum to the same total.
- Deactivating A's Rome link removes exactly A's 3000 (KEY TEST: with the `active` filter
  removed, the inactive link would still contribute; the test must fail then).
- A trip member whose main group is a different Home contributes nothing here.
- A Move-to-Home settlement pair changes no spending figure.
- Conversion uses the rate of the expense date, not today's: two JPY expenses on different
  dates with different rates give different EUR amounts.
- Date boundaries inclusive; deleted expenses excluded.

## Notes
- Plan reference: "Features → Analytics" and "Groups and people".
- Keep signatures parallel to `services/analytics.py` so the dashboard step can switch between
  "this group" and "Home" with one flag.
