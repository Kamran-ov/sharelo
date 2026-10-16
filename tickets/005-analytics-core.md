---
id: 005
title: Analytics core — spending per person and per category
status: ready
risk: normal
depends_on: [003]
pr:
---

## Goal
Pure query functions the dashboard will call later. "Spending" means a member's OWED share,
so a personal expense counts fully for its owner and a 50/50 dinner counts half per person.

## Scope
`ledger/services/analytics.py`, each taking `(group, date_from, date_to, member=None)`:
- `spending_by_member()` → `{member_id: cents}`
- `spending_by_category(level=1|2)` → `{category_id: cents}` (level 1 rolls children into parent)
- `spending_by_month()` → `{"YYYY-MM": cents}`
- `spending_by_member_and_category()` → nested dict.
All exclude soft-deleted expenses and exclude settlements (settlements are not spending).
Use ORM aggregation, not Python loops over rows.

## Out of scope
- Linked sub-groups rolled into Home (needs ticket 006; a follow-up ticket adds it).
- Charts, API endpoints, home-currency conversion.

## Acceptance
- A personal €30 expense by A: A = 3000, B = 0.
- A 50/50 €50 expense paid by A: A = 2500, B = 2500, regardless of who paid.
- Level-1 category totals equal the sum of their level-2 children.
- Date range boundaries are inclusive on both ends.
- Deleted expenses are excluded; a settlement does not appear anywhere.
- Each function runs in a constant number of queries (assert with `django_assert_num_queries`).

## Notes
- Keep the function signatures stable: the dashboard step builds on them.
