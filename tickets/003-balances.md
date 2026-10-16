---
id: 003
title: Balances, settlements and debt simplification
status: ready
risk: risky
depends_on: [002]
pr:
---

## Goal
Given a group's expenses and settlements, the app can say what each member's net position is
and the fewest transfers that settle everyone. Always computed, never stored.

## Scope
`ledger/services/balances.py`:
- `net_balances(group) -> dict[member_id, cents]` in the group currency. Positive = is owed,
  negative = owes. For each non-deleted expense: member net += paid − owed. For each settlement:
  from_member net += amount, to_member net −= amount. Sum of all nets is always 0.
- `simplify_debts(net_balances) -> list[(from_member_id, to_member_id, cents)]` — greedy:
  repeatedly match the largest debtor with the largest creditor. Deterministic order.
- `record_settlement(group, from_member, to_member, amount_cents, date, notes="")` with the
  same validations as expenses (members in group, amount > 0).
- `member_summary(group, member) -> {"paid", "owed_share", "net"}` for the UI.

## Out of scope
- Cross-group "Move to Home" settlements (ticket 006 adds the twin link; this ticket only
  stores `twin` as nullable).
- Currency conversion (004): all expenses in a group are already in the group currency by
  ticket 001's invariant (`currency == group.currency`) — add that invariant check here if 001
  did not.

## Acceptance
- Two members, one 50/50 expense paid by A: B owes A exactly half; sum of nets is 0.
- A "personal" expense changes no net balance but shows in `member_summary.owed_share`.
- A settlement of the full owed amount brings both nets to 0; a partial one reduces by exactly
  that amount.
- Three members with mixed expenses settle in at most 2 transfers; four members in at most 3;
  the transfers, applied to the nets, yield all zeros.
- Editing an expense's amount or deleting it changes the nets accordingly (no stale cache).
- Every computation is in integer cents; a test greps the module for `float(` and `Decimal(`
  and fails if either appears outside the rate field.

## Notes
- Greedy is fine; optimal minimal-transfer is NP-hard and Splitwise uses greedy too.
