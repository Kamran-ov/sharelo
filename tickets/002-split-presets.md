---
id: 002
title: Split presets and rounding
status: in-review
risk: risky
depends_on: [001]
pr: 6
---

## Goal
Pure functions that turn a user's one-tap choice into exact per-member cents, so the UI can
save an expense with minimal input. Rounding never loses or creates a cent.

## Scope
`ledger/services/splits.py`, pure functions (no DB access), each returning `dict[member_id, cents]`:
- `split_equal(total_cents, member_ids)`
- `split_personal(total_cents, payer_id)` → 100% to the payer
- `split_full_for_other(total_cents, other_id)` → 100% to one other member
- `split_percentage(total_cents, {member_id: percent})` — percents sum to 100 (allow 2 decimals)
- `split_exact(total_cents, {member_id: cents})` — must sum to total
- `split_shares(total_cents, {member_id: shares})` — e.g. 2:1
- `split_for_preset(preset, total_cents, member_ids, payer_id, params)` — dispatcher used by
  the API later.

Rounding rule: compute floor shares, distribute leftover cents one each to members in a
deterministic order (sorted by member_id). Document this in the module docstring.

`CategoryDefault` model: group, category, split_type, `split_params` (JSON). Unique
(group, category). Service `default_split_for(group, category)` returns (split_type, params)
or `("equal", {})`.

Convenience `create_expense_from_preset(...)` in `services/expenses.py` that calls the
split function and then `create_expense` from ticket 001.

## Out of scope
- UI, API endpoints.
- Multi-payer presets (multi-payer stays explicit-cents via ticket 001).

## Acceptance
- Every split function's result sums exactly to `total_cents` for totals 1..1000 cents and
  2..5 members (property-style test with a fixed loop of cases, not hypothesis).
- 10.00 / 3 → 334, 333, 333 with the extra cent going to the lowest member_id.
- Percentages not summing to 100 (±0.005) raise `LedgerError`; exact not summing to total raises;
  zero or negative shares raise; empty member list raises.
- `split_personal` for the payer produces owed = total for payer and nothing for others, and
  `create_expense_from_preset(... "personal")` yields an expense whose payer and sole split are
  the same member.
- `default_split_for` returns the group's category default when set, else equal.

## Notes
- "personal" exists so that an expense paid by one person for themselves still appears in that
  person's analytics but has zero effect on balances. That property is tested in ticket 003.
