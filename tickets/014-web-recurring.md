---
id: 014
title: Web — recurring rules page
status: in-review
risk: normal
depends_on: [012]
pr:
---

## Goal
See every standing bill, change an amount when the price changes, pause one, skip one
occurrence. Expenses created by a rule are recognisable in the list.

## Scope
- `/g/:id/recurring`: list of rules — description, amount, "monthly on the 1st" /
  "yearly on 14 Mar", next date, payer, split summary, Paused badge. "+" opens the rule sheet.
- Rule sheet: reuses the add-expense form pieces (amount, description, category, who paid,
  who for) plus Frequency (Monthly | Yearly), day of month / date, start date, optional end
  date. Shows the computed next three dates (from a client helper mirroring `next_occurrence`,
  including the day-31 clamp) before Save.
- Row actions: Edit, Pause/Resume, Skip next (confirm shows the date being skipped), Delete
  (confirm; past expenses stay).
- Expense list rows created by a rule show a small "repeat" icon; tapping it opens the rule.
- Settings tab: a line "Recurring expenses are created by the daily job; last run: <date>"
  read from a new `GET groups/{id}/recurring/status/` (last `run_daily` time stored in a
  tiny `JobRun` model written by the command — add to backend in this ticket).

## Out of scope
- Running the job from the UI. Weekly frequency. Notifications.

## Acceptance
- vitest: client `nextOccurrences(rule, from, 3)` equals the backend for the day-31 case and
  the Feb-29 yearly case (fixtures copied from 007's tests).
- e2e (screenshots): create "Rent 950 monthly on 1" paid by A 50/50 → listed with next date
  = next 1st; preview showed three correct dates. Pause → badge; Resume → badge gone. Skip
  next → next date advanced by one month (KEY TEST pair: skipping a paused rule shows the API
  error inline).
- e2e: after the fixture runs `run_daily` (via `e2e_reset` option `--with-recurring-run`), the
  expense list shows the created expense with the repeat icon and the rule's next date moved.
- e2e: edit amount to 1000 → the existing expense still shows 950.
- No horizontal scroll at 390 px. REPORT lists screenshots and uncovered paths.

## Notes
- Plan reference: "Features → Recurring expenses".
