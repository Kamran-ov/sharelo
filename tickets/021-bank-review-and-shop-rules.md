---
id: 021
title: Bank import review list and shop rules
status: ready
risk: normal
depends_on: [020]
pr:
---

## Goal
After uploading a month, each row needs one tap: Shared, Personal or Skip, with the category and
split already guessed from shop rules. Choices teach the rules, so next month is faster.

## Scope
- `ShopRule` model: group, `match_text` (case-insensitive contains on merchant or description),
  category, preset, params, created_by, last_used_at. Most specific (longest) match wins.
- Service `suggest(row)` → (category, preset) from rules, else the group's last choice for the
  same merchant, else Uncategorized + category default.
- Service `resolve_row(row, decision, category, preset, payer)` → creates the expense through
  `create_expense_from_preset` with `source` = the bank, `external_id` = the row's, and marks the
  row; "Personal" = preset `personal`; "Skip" creates nothing. Optional "remember" creates or
  updates a ShopRule.
- Pages: Expenses page gets "Import bank file" → upload → review list: date, merchant, amount,
  suggested category chip, three big buttons (Shared / Personal / Skip), "remember for this shop"
  toggle. Settings gets a "Shop rules" list (edit, delete).
- Undo per row within the session.

## Out of scope
- Automatic resolution without a tap, multi-member payer detection.

## Acceptance
- With rule "Esselunga → Groceries, 50/50", an Esselunga row is pre-filled and one tap creates a
  50/50 Groceries expense (KEY test: without the rule it suggests Uncategorized).
- Personal creates a `personal` expense; Skip creates nothing; a resolved row cannot be resolved
  twice.
- "Remember" creates a rule that pre-fills the next upload.
- e2e with screenshots: upload fixture, review three rows with three different decisions, list
  shows the two created expenses.
