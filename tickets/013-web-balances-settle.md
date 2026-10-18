---
id: 013
title: Web — balances, settle up, Move to Home
status: in-review
risk: normal
depends_on: [012]
pr: 19
---

## Goal
Open Balances and see in one glance who owes whom; settle a debt in two taps; in a trip, move a
leftover debt between the two of us into Home with one tap.

## Scope
- `/g/:id/balances`: top card for me ("you are owed 84.20" / "you owe 12.00" / "all settled");
  per-member rows with net; "Suggested payments" list from `transfers`
  ("B pays A 12.00") each with a Settle button; collapsed "History" list of settlements
  (date, from → to, amount, note, Move-to-Home badge with the twin group name).
- Settle sheet: from, to (prefilled from the transfer, editable), amount (prefilled with the
  full transfer, editable), date, note → POST settlements; balances refetch; toast with Undo
  (undo = delete the settlement; add `DELETE settlements/{sid}/` to the API in this ticket if
  missing, with the same member permission).
- Move to Home button on a transfer only when: this group is not my main group, both members
  have profiles, and both share the same main group (the API tells via a `can_move_to_home`
  flag on the transfer; add it to the balances endpoint in this ticket). Confirm sheet shows
  "Rome trip: 200.00 moved to Home" preview on both sides → POST move-to-home. Afterwards the
  trip transfer disappears and Home's balances show the mirrored entry.
- Settings tab: "Leave group" is out of scope; nothing added.

## Out of scope
- Partial Move to Home below the suggested amount via slider (the amount field is enough).
- Multi-currency settlements (one currency per group).

## Acceptance
- e2e (screenshots): fixture with A lent B 2105 → Balances shows "you are owed 21.05", one
  suggested payment "B pays A 21.05"; Settle with the prefilled amount → "all settled", history
  has one row (KEY TEST pair: settling 0.00 shows the API error inline and creates nothing).
- e2e: in the trip group, the transfer between A and B shows Move to Home; after confirming,
  the trip is settled and Home shows the mirrored settlement with the trip's name; the guest's
  transfer shows no Move to Home button.
- e2e: Undo after Settle restores the previous balances.
- vitest: wording helper for the top card covers positive, negative, zero.
- `can_move_to_home` backend test: false in a main group, false when one member is a guest,
  false when main groups differ, true otherwise.
- No horizontal scroll at 390 px. REPORT lists screenshots and uncovered paths.

## Notes
- Plan reference: "Balances and settle up", "Groups and people → Move to Home".
- Balances are computed on every GET; never cache them in the client beyond TanStack Query's
  refetch on mutation.
