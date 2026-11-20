---
id: 019
title: Splitwise history import (API, command, re-runnable)
status: done
risk: risky
depends_on: [017]
pr: 28
---

## Goal
Five years of our Splitwise history come in once, exactly: every expense with its real paid and
owed shares, every payment as a settlement, categories mapped one to one. Running it again
creates nothing new.

## Scope
- `imports/splitwise/client.py`: the only place that talks to `https://secure.splitwise.com/api/v3.0`
  (`get_current_user`, `get_groups`, `get_expenses?group_id=&limit=&offset=` with paging,
  `get_categories`). Auth with a personal API key from env `SPLITWISE_API_KEY` (Bearer).
  Tests stub this module; no test touches the network.
- `imports/splitwise/mapper.py`, pure: Splitwise expense JSON → our create-expense arguments.
  `paid_share`/`owed_share` strings → integer cents with exact parsing (no float); per-expense
  sums must equal `cost`; a one-cent mismatch from Splitwise rounding goes to the lowest
  member id and is logged. `payment: true` → Settlement. `deleted_at` set → skipped and counted.
  Category by Splitwise category name → our seeded category (same tree, from 001); unknown →
  Uncategorized/General and counted.
- `import_splitwise --group <splitwise_group_id> --into <our_group_id> --map "<sw_user_id>=<member_id>" ... [--dry-run]`
  management command. Every row uses `source="splitwise"`, `external_id=<splitwise id>`, one
  `ImportBatch` per run with seen/created/skipped counts. Unmapped Splitwise users → the command
  refuses before writing anything and prints the user list with ids and names.
- `--dry-run` prints the counts and the first 10 mapped rows, writes nothing.
- README section "Import from Splitwise" (where to get the API key, the commands).

## Out of scope
- An import page in the app (the command is enough for a one-off), receipts/comments,
  Splitwise friends outside groups.

## Acceptance
- Fixture of recorded Splitwise JSON (hand-written, anonymised) with: equal split, unequal split,
  one person paid for other, multi-payer, payment, deleted expense, foreign currency, unknown
  category. Import creates exactly the expected rows; balances after import equal the balances
  implied by the fixture's `net_balance` values.
- Running the import twice: second run creates 0 and skips all (KEY test: with the
  `(source, external_id)` lookup removed it would duplicate).
- Unmapped user → no row written, exit code non-zero, users listed.
- `--dry-run` writes nothing (row counts identical before/after).
- No `float(` in the import package (grep test).

## Notes
- Kamran runs it on the laptop with his real key after merge; the REPORT must say which parts
  were only tested against fixtures.
