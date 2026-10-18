---
id: 001
title: Core models — groups, members, expenses, payers, splits, settlements
status: done
risk: risky
depends_on: [000]
pr: 5
---

## Goal
The database shape of the whole app exists as Django models with migrations, and the
invariants that keep money consistent are enforced and tested. No API, no UI.

## Scope
Django app `backend/ledger/` with these models (all money as `IntegerField` cents; never Decimal/float):

- `Group`: name, currency (ISO code, 3 chars), `share_token` (random, unique, URL-safe),
  created_at.
- `Member`: group (FK), display_name, `profile` (nullable FK to `accounts.Profile`; that model
  is a stub in this ticket: id + email, nothing else), unique (group, display_name).
- `Category`: name, `parent` (nullable self-FK, max depth 2), `is_default` bool.
  Seed data migration with Splitwise's two-level structure (see Notes).
- `Expense`: group, description, `amount_cents`, `currency`, `original_amount_cents`,
  `original_currency`, `rate_used` (Decimal(18,8), nullable, 1 when same currency), `date`,
  category (FK), `split_type` (choices: equal, personal, full_for_other, percentage, exact,
  shares), `source` (choices: manual, splitwise, revolut, wise, recurring), `external_id`
  (nullable), `import_batch` (nullable FK), `recurring_rule` (nullable FK, model stubbed),
  notes, created_at, updated_at, `deleted_at` (soft delete).
  Unique constraint on (source, external_id) where external_id is not null.
- `ExpensePayer`: expense, member, `paid_cents`. Unique (expense, member).
- `ExpenseSplit`: expense, member, `owed_cents`. Unique (expense, member).
- `Settlement`: group, from_member, to_member, `amount_cents`, currency, date, notes,
  `twin` (nullable self-FK, for "Move to Home" pairs later), source, external_id,
  import_batch, created_at.
- `ImportBatch`: group, source, started_at, finished_at, `label` (file name or "api"),
  rows_seen, rows_created, rows_skipped.

Service layer `ledger/services/expenses.py` (NOT model methods, NOT views):
- `create_expense(group, *, description, amount_cents, currency, date, category, payers: dict[member_id, cents], splits: dict[member_id, cents], split_type, ...) -> Expense`
- `update_expense(expense, **same)` and `delete_expense(expense)` (soft delete).
- Validation raises `LedgerError` (one exception class, with a machine-readable `code`).

## Out of scope
- Split presets and rounding helpers (ticket 002) — this ticket takes explicit cents only.
- Balances and debt simplification (003).
- Currency conversion logic and rate fetching (004) — `rate_used` is stored, not computed.
- Profiles, auth, group linking (006). Recurring rules (007).

## Acceptance
- Payers must sum exactly to `amount_cents`; splits must sum exactly to `amount_cents`;
  every payer/split member must belong to the expense's group; currency must be a valid
  3-letter code; `amount_cents` must be > 0. Each violation raises `LedgerError` with a
  distinct code, and the legitimate case succeeds (one positive test per rule).
- Creating an expense is atomic: if a split row fails validation, no expense row and no
  payer rows remain.
- `delete_expense` soft-deletes; the default manager hides deleted expenses; `all_objects`
  shows them.
- A second expense with the same (source, external_id) raises; a second one with
  external_id = NULL does not.
- Category depth > 2 is rejected at the model level.
- Seed migration produces the category tree; a test asserts the parent names and at least
  one child per parent.

## Notes
- Plan reference: see `docs/PLAN.md` sections "Data model" and "Key decisions".
- Splitwise category structure to seed (parent → children):
  - Entertainment → Games, Movies, Music, Sports, Other
  - Food and drink → Dining out, Groceries, Liquor, Other
  - Home → Electronics, Furniture, Household supplies, Maintenance, Mortgage, Pets, Rent,
    Services, Other
  - Life → Childcare, Clothing, Education, Gifts, Insurance, Medical expenses, Taxes, Other
  - Transportation → Bicycle, Bus/train, Car, Gas/fuel, Hotel, Parking, Plane, Taxi, Other
  - Utilities → Cleaning, Electricity, Heat/gas, Trash, TV/Phone/Internet, Water, Other
  - Uncategorized → General
- Soft delete rather than hard delete because balances are computed from history and the
  Splitwise import must be re-runnable.
