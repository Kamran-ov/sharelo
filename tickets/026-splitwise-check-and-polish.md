---
id: 026
title: Splitwise import check report, React Router warnings, small polish
status: ready
risk: normal
depends_on: [019]
pr:
---

## Goal
After the real 5-year Splitwise import, one command proves the data matches Splitwise: same
balances per person, same totals per year and per category. Plus small clean-ups seen in test
output.

## Scope
- Management command `check_splitwise --group <sw_group_id> --into <our_group_id> --map ...`:
  reads the Splitwise group via the existing client and compares with our data:
  per-member net balance (Splitwise `balance` vs our `net_balances`), number of expenses and
  payments imported vs seen (excluding deleted), total cost per year, total per category.
  Prints a table with OK / DIFF per line and exits non-zero on any DIFF. Read-only.
- Same check also available with `--json` for the REPORT.
- Frontend: opt in to the React Router v7 future flags (`v7_startTransition`,
  `v7_relativeSplatPath`) so the test warnings disappear; no behaviour change.
- `docs/ops.md` (from 025, or create the section if 025 is not merged yet): "Import from
  Splitwise" — dry run, import, check, what to do with a DIFF.

## Out of scope
- Fixing data differences automatically; importing more than one group per run.

## Acceptance
- Fixture where everything matches → all OK, exit 0. Fixture with one expense missing → DIFF
  on count, year total and that member's balance, exit 1 (KEY pair).
- Command performs no writes (row counts identical before/after).
- vitest output contains no React Router future-flag warning (test captures console.warn).

## Notes
- Kamran runs the real import + check on the server after 024/025; the REPORT says only
  fixtures were used.
