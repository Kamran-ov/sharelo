# sharelo — agent operating manual

Project facts only. Process lives in the `spec-driven-development` skill; if this file ever
contradicts it, follow the skill for process and this file for facts, and say so once.

## 1. CONTEXT MAP

Read only what the task needs. If you are opening a fourth unrelated area, stop and re-read
the ticket.

| Task touches | Read |
|---|---|
| Anything | `docs/PLAN.md` (what we're building and why), the ticket in `tickets/` |
| Money, splits, balances | `backend/ledger/services/` and its tests; never views |
| Groups, members, profiles, linking | `backend/accounts/`, `backend/ledger/services/groups.py` |
| Currency | `backend/ledger/services/rates.py` |
| Frontend | `frontend/src/` — pages talk to DRF endpoints only, no business logic in TS |
| Imports (later) | `backend/importers/<source>/` one package per source |

Layout: `backend/` (Django project `sharelo`, apps `ledger`, `accounts`, later `importers`),
`frontend/` (Vite + TypeScript + React, PWA), `docs/` (plan, specs, review log, ADRs),
`tickets/`, `scripts/`.

## 2. FACTS — do not guess these

- **Money is integer cents in every model, service and test.** Never `float`, never `Decimal`
  for amounts. The only Decimal in the codebase is `Expense.rate_used` (18,8). Trap: a
  `/ 100` or `round()` on money anywhere else is a defect, not a convenience.
- **Rounding rule:** floor every share, hand leftover cents one each to members in ascending
  `member_id` order. Lives in `ledger/services/splits.py` and nowhere else. 10.00/3 → 334/333/333.
- **Balances are computed, never stored.** net = paid − owed over non-deleted expenses, ±
  settlements. The sum of all nets in a group is always 0. If a cache ever appears, it is wrong.
- **One currency per group.** `Expense.currency == group.currency` always; the foreign amount
  lives in `original_amount_cents` + `original_currency`, converted at `rate_used`. Rates are
  stored per (date, currency) against EUR; any pair goes through EUR; weekend → previous rate;
  >7 days without a rate → `LedgerError(no_rate)`.
- **split_type enum (exact strings):** `equal`, `personal`, `full_for_other`, `percentage`,
  `exact`, `shares`. `personal` = payer owes 100% to themselves: zero effect on balances, full
  effect on that person's analytics. Analytics "spending" = OWED share, never paid.
- **source enum:** `manual`, `splitwise`, `revolut`, `wise`, `recurring`. `(source, external_id)`
  is unique where external_id is not null; this is the only duplicate guard for imports.
- **Soft delete only** (`deleted_at`). Default manager hides deleted rows; `all_objects` shows
  them. Imports must be re-runnable, so nothing is ever hard-deleted.
- **Categories are two levels** (parent → child), seeded from Splitwise's structure. Max depth 2
  is enforced at the model.
- **Identity:** a `Profile` (Django User 1:1) is one person across all groups. A `Member` is
  that person inside one group, or a guest with `profile = NULL`. A profile appears in a group
  at most once. Guest shares never roll into anyone's Home analytics.
- **Main group + links:** each profile has one `main_group`. Any other group it creates or joins
  gets a `GroupLink(active=True)` automatically. "Move to Home" = two `Settlement` rows (trip
  and main group) pointing at each other via `twin`, in one transaction.
- **Natural keys:** Group → `share_token`; Member → (group, display_name); Expense from an
  import → (source, external_id).
- **Timezone:** expenses carry a `date`, not a datetime; the group's day is the date given.
  Rates are keyed by that same date. <!-- FILL: confirm Europe/Rome as display TZ for the UI -->
- **Statuses of a ticket:** draft, ready, in-review, blocked, done. Terminal: done.

## 3. HARD RULES — each names the bug it prevents

1. **Postgres only; no SQLite fallback, not even in tests.** Prevents green tests that hide
   constraint and transaction behaviour that only Postgres enforces.
2. **Every multi-row write (expense + payers + splits; the settlement twin pair) is one
   transaction** via the service layer. Prevents half-written expenses that make balances
   wrong with no error.
3. **Payers sum to total, splits sum to total, every member belongs to the group — enforced in
   the service, tested with one failing and one passing case each.** Prevents the silent
   balance drift Splitwise users never notice until settle-up.
4. Never edit a committed migration; add a new one. Prevents divergent schemas between
   laptop and server.
5. Never commit secrets; an empty required env var means "missing" and the app refuses to
   boot. Prevents a wrong-but-booting production.
6. A test that was green and goes red is your regression; fix the code, not the test. Deleting
   or re-aiming a test must name the property that loses its guard.
7. Never commit to `main` or `develop` directly. Branch `claude/<id>-<slug>`, one PR, squash.
8. Business logic in `services/`, never in views, serializers or models' save(). Prevents
   untestable logic and duplicated rules between API and importers.
9. Doc first: a plan in `docs/specs/<id>.md` precedes code; a decision someone will need later
   goes in `docs/adr/` or `docs/REVIEW-LOG.md`, never only in a PR body.
10. **No command that cannot finish on its own**: no `while`/`until`/`for` loops, `sleep`,
    `watch`, `tail -f`, no `&`/`nohup` backgrounding, no foreground dev servers. Wait on CI
    with one `timeout 1800 gh run watch <run-id> --exit-status`. Prevents the hung sessions
    this project's owner has already lost hours to; the settings file denies these too.

## 4. WORKFLOW

Spec-driven-development skill, as practised here:
plan (draft PR) → Reviewer ACCEPT/REVISE → build (ready PR with REPORT) → Reviewer
ACCEPT → merge preflight → squash merge to `develop`. Kamran merges `develop` → `main`.
Ticket key = the `tickets/NNN-*.md` id; it goes in the branch name, PR title and commits.

Definition of Done for a ticket: plan accepted; every test the plan named is in the PR and
green; key test shown red without the fix and restored; `make lint` green; REPORT in the PR
body; `docs/REVIEW-LOG.md` updated with the reviewer's entries; ticket `status: done`.

## 5. COMMANDS

| What | Command | Trap |
|---|---|---|
| Tests (cloud / plain Postgres) | `make test` | Needs `DATABASE_URL`; run `scripts/cloud-setup.sh` first in a fresh cloud session |
| Tests (laptop, Docker) | `USE_DOCKER=1 make test` | `docker compose up` without `-d` never returns; use `make`, which uses `run --rm` |
| Backend only / frontend only | `make test-backend` / `make test-frontend` | Both must exit non-zero on failure; CI relies on it |
| Lint | `make lint` | `ruff check` + `ruff format --check` for Python, `tsc --noEmit` for TS |
| Wait for CI | `timeout 1800 gh run watch <run-id> --exit-status` | Take the run id from `gh run list --branch <b>`; no output = no run exists, not "finished" |
| Merge preflight | `gh pr checks <n>`; `gh pr view <n> --json mergeStateStatus` | `UNKNOWN`/`UNSTABLE` = not answered yet; settle on `gh run view <run> --json jobs` |
| Rates | `python manage.py fetch_rates --since YYYY-MM-DD` | Network; stub in tests |

## 6. CURRENT STATE

Scaffold exists (ticket 000): Django 5 + DRF project `sharelo` in `backend/` (Postgres only, `DATABASE_URL`), Vite/React/TS skeleton in `frontend/`, `Makefile`, compose, CI. Ticket 001 added apps `accounts` (stub `Profile`) and `ledger` (all core models, constraints, seeded Splitwise categories, `services/expenses.py` create/update/delete with `LedgerError`). Ticket 002 added `services/splits.py` (pure split functions in integer basis points, `split_for_preset`, `default_split_for`), `CategoryDefault`, and `create_expense_from_preset`. Ticket 003 added `services/balances.py` (`net_balances`, `simplify_debts`, `record_settlement`, `member_summary`). Ticket 004 added `ExchangeRate`, `services/rates.py` (ECB parse/fetch, `rate`, `convert`, `resolve_foreign_amount`), `fetch_rates`, and `rate_mismatch` in `create_expense`. Ticket 005 added `services/analytics.py` (owed-share spending by member, category, month, member×category; one query each). Ticket 006 added the real `accounts.Profile` (User 1:1, `main_group`), `GroupLink`, a DB-level one-member-per-profile-per-group constraint, and `services/groups.py` (`create_group`/`join_group_by_token` with `as_main` and one `_auto_link` rule, `set_link_active`, `move_debt_to_home` as a twin settlement pair). Ticket 007 added the full `RecurringRule`, `services/recurring.py` (`create_rule`/`update_rule`/pause/resume/skip/delete, pure `next_occurrence`, `generate_due` idempotent via `external_id="rule:<id>:<date>"`) and the `run_daily` command (rates refresh, then due expenses). Roadmap in `docs/PLAN.md` "Build order". Tickets 000–007 cover
step 0 (scaffold) and step 1 (core engine). This section is updated by the Author at each
merge: one line, what now exists.

## 7. STANDING DECISIONS

**Question budget:** ask (via a `needs-operator` issue) only for forks that are irreversible or
change the plan's Key decisions. Take the reversible default, note it in the plan's Open
questions as "assumed", and continue.

- Own app, not a Spliit fork. Python/Django because the owner is a Python developer.
- No Docker daemon in cloud sessions: `scripts/cloud-setup.sh` starts Postgres as a process.
- Hosting, domain, email (Brevo), and sign-in providers (Google OAuth) are release-step work;
  do not scaffold them early. Email/password auth works without any email sending until then.
- Analytics chart design is decided by Kamran before the analytics UI ticket; do not design
  dashboards unasked.
- Pantry/meals module is phase 2 in a separate app; nothing in `ledger` should anticipate it.
- Splitwise category tree is seeded verbatim so the five-year import maps 1:1; rename later
  in the UI, not in the seed.
- ⚠️ Never add a stored balance, cached total, or denormalised "owes" column without reading
  FACTS "Balances are computed" first.

## 8. STYLE MICRO-RULES

- Type hints everywhere; `LedgerError(code=...)` is the only domain exception.
- Tests are named for the property, not the function: `test_splits_sum_to_total`, not
  `test_split_equal`.
- No comments restating code; comments state the reason or the trap.
- Frontend strings in English; no i18n until a ticket asks.

Skills this repo relies on: `spec-driven-development` (process), `proving-tests-bite` (key
test discipline), `working-agreements`, `silent-failure-patterns` (review lens),
`browser-e2e-with-mock-auth` (from the web-app step on).
