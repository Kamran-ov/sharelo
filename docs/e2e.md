# Browser tests (Playwright)

`make e2e` builds the frontend and runs `playwright test` in `frontend/`. Playwright's `webServer` entries start
Django (`E2E=1 manage.py runserver 8001 --noreload`, after `e2e_prepare`) and `vite preview` (4173) and stop them
afterwards; never start either by hand. Since 015 a third entry, Django on 8002 serving `frontend/dist` itself
(no `e2e_prepare`: the 8001 entry prepared the shared `sharelo_e2e` database), backs the `served` project.

- **Database:** `sharelo_e2e`, separate from the dev database. `e2e_prepare` creates it if missing (needs CREATEDB,
  else it prints `createdb sharelo_e2e`) and migrates it. `e2e_reset` refuses unless `E2E=1` and the database name
  ends in `_e2e`; the settings refuse to boot in E2E mode on any other name or on a foreign `ALLOWED_HOSTS`.
- **Reset:** before every test, `e2e_reset` truncates all tables except `django_migrations`, `django_content_type`,
  `auth_permission`, `ledger_category` and `ledger_exchangerate`, then seeds the fixture below.
- **Fixture:** `a@example.com` / `password1234` ("Alice") and `b@example.com` ("Bea") share main group "Home"
  (EUR). "Rome trip" (EUR) belongs to Bea only, share token `e2e-rome-token`.
- **Fixture rows added in 012:** Home has one `CategoryDefault` for Uncategorized › General with preset `equal` (General is the category the add sheet preselects in a group with no expenses). `ledger_exchangerate` is not truncated, so the reset upserts USD 1.10 per EUR for today with `update_or_create` on `(date, currency)` and deletes every GBP row (GBP has no rate, which the no-rate test needs). A 100.00 USD expense stores `rate_used` `0.90909091` and `amount_cents` 9091.
- **013 specs (`balances.spec.ts`):** no change to the fixture. Trip tests make Alice join Rome trip through `POST join/<token>/` while logged in as her, then log in as Bea (`loginAs`); debts are seeded with `owes()` (creditor pays, preset `full_for_other`). The guest ("Gus") joins through the invite page in a second browser context.
- **014 specs (`recurring.spec.ts`):** `e2e_reset --with-recurring-run` (helper `resetFixture("--with-recurring-run")`) additionally seeds one rule in Home: "Rent", 95000 cents, monthly on day 1, paid by Alice, equal split, start 2026-01-01, then calls `generate_due(2026-01-15)` and `record_job_run("run_daily", 2026-01-15T07:13Z)` with those fixed literals. That leaves one expense "Rent" 950.00 dated 2026-01-01 and the rule's next date 2026-02-01. The fixture calls the two services the `run_daily` command calls instead of the command itself, because the command fetches ECB rates over the network. Specs that create a rule through the UI use the 1st of next month (computed once in the spec) as start date, never today.
- **E2E mode:** `DEBUG` off, `ALLOWED_HOSTS` localhost only, plain-http cookies, no SSL redirect, auth throttle lifted.
- **Browser:** Chromium at 390x844. The cloud image has it under `PLAYWRIGHT_BROWSERS_PATH` (`@playwright/test` is
  pinned to the matching 1.56.1); CI runs `npx playwright install --with-deps chromium` first.
- **Screenshots:** each test writes `docs/screenshots/<ticket>/<test name>.png`, committed.
- **Google sign-in** is not covered (needs real Google).
- **015 specs (`pwa.spec.ts`, project `served`, baseURL 8002):** the `preview` project (all earlier specs, vite preview 4173) and `served` run in the same `make e2e`, one worker, so every `e2e_reset` is serial. `dist` is built once by `make e2e` and shared. The offline test cannot use `context.setOffline` (Chromium does not apply it to the service worker's own fetches, so the worker would still fetch the shell from the server); it runs through a forwarding proxy on 8003 that the test closes. Not covered: a real phone install, `beforeinstallprompt` on real Chrome (vitest drives that branch), HTTPS/HSTS behind a tunnel.
