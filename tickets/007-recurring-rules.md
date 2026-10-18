---
id: 007
title: Recurring rules and the daily job
status: done
risk: risky
depends_on: [002, 004]
pr: 12
---

## Goal
Rent, Netflix and similar fixed bills create themselves. A rule holds amount, payer, split,
category and frequency; a daily command creates the expenses that are due, catches up missed
days, and is safe to run twice. The same command refreshes ECB rates.

## Scope
- `RecurringRule` model (replace the stub from 001): group, description, `amount_cents`,
  payer (Member FK), `split_type`, `split_params` (JSON, same shape as `CategoryDefault`),
  category, `frequency` (choices: monthly, yearly), `day_of_month` (1–31), `month` (1–12,
  yearly only), `start_date`, `next_date`, `end_date` (nullable), `paused` bool, created_at,
  updated_at, `deleted_at` (soft delete). Currency is always the group currency.
- `ledger/services/recurring.py`:
  - `create_rule(group, **fields)`, `update_rule(rule, **fields)` (changes apply to future
    occurrences only; already created expenses keep their amount), `delete_rule(rule)` (soft).
  - `next_occurrence(after: date, rule) -> date` — pure; monthly day 31 clamps to the last day
    of shorter months (Jan 31 → Feb 28/29 → Mar 31); yearly Feb 29 clamps to Feb 28 in
    non-leap years.
  - `pause_rule(rule)`, `resume_rule(rule, today)` — resume sets `next_date` to the first
    occurrence on or after `today`; paused months are NOT back-filled.
  - `skip_next(rule)` — advances `next_date` by one occurrence without creating an expense.
  - `generate_due(today) -> list[Expense]` — for every active, non-deleted rule with
    `next_date <= today` (and `end_date` not passed): create the expense with
    `create_expense_from_preset(...)`, `source="recurring"`,
    `external_id=f"rule:{rule.id}:{next_date.isoformat()}"`, `recurring_rule=rule`,
    `date=next_date`; then advance `next_date`. Repeat until `next_date > today` (catch-up).
    One transaction per occurrence, so a failure in one rule never blocks the others; failures
    are collected and returned/logged, not raised.
- Management command `run_daily [--today YYYY-MM-DD]`: step 1 `fetch_ecb_rates()` (a network
  failure is logged and does NOT stop step 2); step 2 `generate_due(today)`. Prints rates
  upserted, expenses created, rules failed. Exit code 0 unless a rule failed.
- README: one section "Daily job" with the command and an example cron line. Scheduling it on
  a server is the release step, not this ticket.

## Out of scope
- API endpoints and the recurring page (tickets 010, 014).
- Variable-amount bills (plan: those stay manual).
- Any scheduler process inside the repo (compose service, celery, APScheduler).

## Acceptance
- A monthly rule on day 31 starting Jan 31 produces Jan 31, Feb 28 (or 29), Mar 31, Apr 30.
- A yearly rule on Feb 29 produces Feb 28 in non-leap years and Feb 29 in leap years.
- `generate_due` run twice for the same `today` creates nothing the second time (KEY TEST:
  the duplicate is prevented by the `(source, external_id)` constraint; the test must show
  that removing the external_id would create a duplicate).
- A rule 3 months behind creates exactly 3 expenses dated to each missed occurrence, and
  `next_date` ends in the future.
- A paused rule creates nothing; after `resume_rule` on a later day, nothing is created for
  the paused months and the next expense is the first occurrence on or after that day.
- `skip_next` advances `next_date` by exactly one occurrence and creates no expense.
- `update_rule(amount_cents=...)` changes only expenses created afterwards.
- Deleting a rule keeps its past expenses; `Expense.recurring_rule` still points at it.
- A rule whose payer left the group (member deleted or moved) fails alone; other rules in the
  same run still create their expenses, and the command exits non-zero.
- `run_daily` with `fetch_ecb_rates` stubbed to raise still creates due expenses.
- Edge cases and production checks in the plan (risky ticket): expected counts after one run
  on a fixture of 5 rules.

## Notes
- Plan reference: "Features → Recurring expenses" and "Key decisions → Recurring amounts".
- `external_id` encodes rule id + occurrence date so idempotency needs no extra table.
- Every expense created here goes through the normal services, so balances and analytics need
  no special case.
