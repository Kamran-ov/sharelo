---
id: 018
title: Share a group summary to WhatsApp (text and image)
status: in-review
risk: normal
depends_on: [017]
pr:
---

## Goal
For people who never open the app: one tap on Balances shares a readable summary (who owes whom,
totals, last expenses) to WhatsApp or any app, as text and as an image.

## Scope
- `GET groups/{id}/summary/` → `{group, currency, total_spent_cents, per_member: [...],
  transfers: [...], recent_expenses: [last 10]}` built from existing services.
- Balances page "Share" button:
  - Text: a plain message, e.g. "Rome trip — total 1,240.00 EUR\nJanet pays Kamran 82.50\n…",
    shared with the Web Share API; fallback copies to clipboard with a toast.
  - Image: the same content rendered as a card (canvas or SVG → PNG) and shared as a file where
    the browser supports file sharing, else downloaded.
- Amount formatting reuses the existing `formatCents`; no money arithmetic in TS.

## Out of scope
- Public read-only web page for the group (possible later ticket), PDF export.

## Acceptance
- vitest: the text builder for a 3-member fixture equals an exact expected string (KEY test:
  breaking the transfer direction must fail it).
- Backend: summary numbers equal `net_balances`/`simplify_debts` on the same fixture; outsider
  gets 404.
- e2e: Share with Web Share stubbed captures the text; without Web Share the clipboard holds it.
- Screenshot of the generated image card.
