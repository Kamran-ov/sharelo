# Browser tests (Playwright)

`make e2e` builds the frontend and runs `playwright test` in `frontend/`. Playwright's `webServer` entries start
Django (`E2E=1 manage.py runserver 8001 --noreload`, after `e2e_prepare`) and `vite preview` (4173) and stop them
afterwards; never start either by hand.

- **Database:** `sharelo_e2e`, separate from the dev database. `e2e_prepare` creates it if missing (needs CREATEDB,
  else it prints `createdb sharelo_e2e`) and migrates it. `e2e_reset` refuses unless `E2E=1` and the database name
  ends in `_e2e`; the settings refuse to boot in E2E mode on any other name or on a foreign `ALLOWED_HOSTS`.
- **Reset:** before every test, `e2e_reset` truncates all tables except `django_migrations`, `django_content_type`,
  `auth_permission`, `ledger_category` and `ledger_exchangerate`, then seeds the fixture below.
- **Fixture:** `a@example.com` / `password1234` ("Alice") and `b@example.com` ("Bea") share main group "Home"
  (EUR). "Rome trip" (EUR) belongs to Bea only, share token `e2e-rome-token`.
- **Fixture rows added in 012:** Home has one `CategoryDefault` for Uncategorized › General with preset `equal` (General is the category the add sheet preselects in a group with no expenses). `ledger_exchangerate` is not truncated, so the reset upserts USD 1.10 per EUR for today with `update_or_create` on `(date, currency)` and deletes every GBP row (GBP has no rate, which the no-rate test needs). A 100.00 USD expense stores `rate_used` `0.90909091` and `amount_cents` 9091.
- **E2E mode:** `DEBUG` off, `ALLOWED_HOSTS` localhost only, plain-http cookies, no SSL redirect, auth throttle lifted.
- **Browser:** Chromium at 390x844. The cloud image has it under `PLAYWRIGHT_BROWSERS_PATH` (`@playwright/test` is
  pinned to the matching 1.56.1); CI runs `npx playwright install --with-deps chromium` first.
- **Screenshots:** each test writes `docs/screenshots/<ticket>/<test name>.png`, committed.
- **Google sign-in** is not covered (needs real Google).
