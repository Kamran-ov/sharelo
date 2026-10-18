---
id: 011
title: Web app shell — sign-in, groups, join by link, Playwright e2e
status: done
risk: normal
depends_on: [010]
pr: 17
---

## Goal
The first screens on a phone: sign in or register, see and create groups, open a shared link
and join as a guest with a name. This ticket also sets up the browser test stack every later
UI ticket uses, and the REPORT for UI tickets gains screenshots.

## Scope
- Frontend stack decisions (stay with them in later tickets): React + React Router,
  TanStack Query for server state, Tailwind CSS v4, types generated from
  `src/api/schema.json` with `openapi-typescript`, one `api.ts` fetch wrapper that sends the
  CSRF token and maps `{code, detail}` errors. Mobile-first: 390 px wide is the design
  target, desktop just centres it (max 480 px). Tap targets ≥ 44 px. No component library.
- Pages: `/login` (email + password, "create account" toggle, "Sign in with Google" button
  via Google Identity Services, hidden when `/api/me.google_enabled` is false),
  `/groups` (list with currency and "main" badge; create sheet: name, currency picker with
  EUR first, "make this my main group" checkbox), `/join/:token` (group name, members,
  name field; signed-in users join with one tap; guests type a name), `/g/:id` shell with a
  bottom nav: Expenses, Balances, Recurring, Settings (the three tabs other than Settings are
  placeholders saying "coming in ticket 012/013/014"; Settings shows the share link with a
  copy button and the link-to-Home toggle).
- Routing guard: anonymous users without guest memberships are sent to `/login`; a guest with
  memberships sees only their groups.
- Playwright: `frontend/e2e/`, `playwright.config.ts` whose `webServer` entries start the
  Django server (`E2E=1 python manage.py runserver 8001`) and the built frontend
  (`vite preview`) — Playwright starts and stops them itself; nobody runs a server by hand.
  Backend management command `e2e_reset` (only works when `E2E=1`) wipes and seeds a known
  fixture: user `a@example.com`/`password1234` with Home + partner B, one trip group with a
  known share token. `make e2e` = build + `playwright test`; CI job `e2e` with the Postgres
  service. Phone viewport (390×844). Each e2e test saves a screenshot to
  `docs/screenshots/<ticket-id>/<test-name>.png`; the PNGs are committed and listed in the
  REPORT.
- PWA manifest and service worker are ticket 015, not here.

## Out of scope
- Expense, balance and recurring screens (012–014). Google button in e2e (needs real Google;
  covered by a vitest unit test that the button renders only when enabled).

## Acceptance
- vitest: `api.ts` attaches the CSRF header and maps a 400 `{code}` into a typed error; the
  Google button renders iff `google_enabled`.
- e2e (each with screenshot): register a new account and land on `/groups`; log in as the
  fixture user and see Home with the "main" badge; create a trip group and see it listed
  with "linked to Home"; open `/join/<token>` in a fresh browser context, enter "Guest Gina",
  land in the group shell and see her name under Settings; wrong password shows the API's
  message inline, no redirect (KEY TEST pair: refusal + the success case above).
- Routing guard: visiting `/groups` anonymous redirects to `/login`.
- Lighthouse not required; but no horizontal scroll at 390 px (e2e asserts
  `document.documentElement.scrollWidth <= 390`).
- REPORT lists every screenshot path and what it shows, and states what the e2e did not cover.

## Notes
- Plan reference: "Key decisions → Access, Mobile" and "Groups and people".
- Server start commands belong only inside `playwright.config.ts` `webServer`; the builder's
  shell rules forbid running them directly.
- Reviewer may open the committed PNGs (images only) to judge the screens.
