---
id: 012
title: Web — add an expense in two taps, expense list, edit and delete
status: ready
risk: normal
depends_on: [011]
pr:
---

## Goal
The screen we will use ten times a week. Amount, description, Save — with the category's
default split, who-paid defaulting to me, and today's date — is a complete expense. Everything
else is one tap away, and the rare cases sit under Advanced.

## Scope
- `/g/:id/expenses`: list grouped by month with a month total, newest first, paged (50) with
  "load more". Row: description, sub-category, date, amount in group currency (original
  amount + currency in small text when different), "you paid" / "<name> paid", and your share
  ("you owe 12.50" / "you lent 12.50" / "personal"). Tap → edit sheet. Floating "+" button.
- Add sheet (full-height bottom sheet):
  1. Amount: numeric keypad input (`inputmode="decimal"`), typed in the group currency,
     converted to cents in the client; never a float sent to the API.
  2. Description with suggestions from the group's last 20 descriptions (tap to fill, which
     also fills that expense's category).
  3. Category: shows the last used category as a chip; tapping it opens the two-level picker
     (parents as tabs, children as a grid, most-used first).
  4. Date: today, tap to change.
  5. "Who paid": segmented control Me | <other> for 2-member groups; a dropdown for more.
  6. "Who it's for": segmented 50/50 | Only me | All <other> | Custom %; Custom shows one
     slider (payer's percent, 5 % steps, number shown) — maps to presets `half`, `personal`,
     `full_for_other`, `percentage`. Pre-selected from the category default.
  7. "Advanced" collapsed: exact amounts per member, shares, equal among a chosen subset,
     foreign currency (amount + currency picker; shows the converted amount from
     `/api/...` preview or disables Save until a rate exists, with a manual-rate field when
     the API says `no_rate`).
  Save → POST, optimistic insert into the list, sheet closes, toast "Saved" with Undo (undo =
  DELETE within 5 s).
- Edit sheet: same form, prefilled; Delete with confirm.
- Category default: Settings tab gets a "Default split per category" list (PUT
  `category-defaults`).

## Out of scope
- Multi-payer entry (API supports it; UI later if ever needed). Receipt photos. Search.

## Acceptance
- vitest: amount parsing "12,50" / "12.50" / "12" → 1250 / 1250 / 1200; "12.345" rejected;
  preset mapping from the two segmented controls to API body is exhaustive (4 × 2 cases).
- e2e (with screenshots): logged in as A, open "+", type 42.10 and "Pizza", Save — exactly
  3 fields touched, no other taps; list shows "Pizza 42.10, you paid, you lent 21.05"; the
  Balances API shows B owes A 2105. (KEY TEST: with the category default removed from the
  fixture the test must still pass via the "equal" fallback; with the preset mapping broken it
  must fail.)
- e2e: Only me → list shows "personal", balances unchanged; All <other> → B owes the full
  amount; Custom 70 % → splits 70/30 shown in the edit sheet.
- e2e: edit changes amount and the month total updates; delete removes the row; Undo after
  Save removes the row and the balance change.
- e2e: foreign currency USD with a seeded rate shows the converted EUR amount in the row;
  without a rate Save is disabled until a manual rate is typed.
- No horizontal scroll at 390 px on the list and in the sheet with the keyboard open.
- REPORT lists screenshots and what e2e did not cover.

## Notes
- Plan reference: "Features → Adding an expense (two taps)".
- "You owe / you lent" is `owed_cents - paid_cents` for the current member; sign decides the
  wording; zero → "settled".
