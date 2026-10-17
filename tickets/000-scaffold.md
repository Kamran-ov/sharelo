---
id: 000
title: Repository scaffold — Django + Postgres + test stack
status: done
risk: normal
depends_on: []
pr: 2
---

## Goal
A repo where `docker compose run --rm backend pytest` passes one trivial test against
PostgreSQL, both locally and inside a Claude Routines cloud session. Nothing app-specific yet.
This ticket is also the dry run of the whole loop: plan → draft PR → review → build → merge.

## Scope
- `backend/`: Django 5.x project `sharelo`, Django REST Framework, `psycopg`, `pytest-django`,
  `ruff`. Settings read `DATABASE_URL` from env; default to the compose Postgres.
- `frontend/`: Vite + TypeScript + React skeleton with `vitest` and one trivial passing test.
  No pages yet beyond "Hello".
- `docker-compose.yml`: services `db` (postgres:17), `backend`, `frontend`. `backend` waits for
  `db` with a healthcheck (compose `depends_on: condition: service_healthy`), NOT a shell loop.
  Compose is for Kamran's laptop. The cloud session that builds and reviews has NO Docker
  daemon, so the test targets must also work with a plain Postgres reachable at `DATABASE_URL`:
  provide `scripts/cloud-setup.sh` that installs and starts Postgres as a local process
  (apt or the environment's package manager), creates the test role/db, and exports
  `DATABASE_URL`. This script becomes the routine environment's setup script.
- `Makefile` with targets: `test-backend`, `test-frontend`, `test` (both), `lint`. Each target
  uses Docker only if `USE_DOCKER=1`, otherwise runs directly against `DATABASE_URL`. Every
  target must exit non-zero on failure and must terminate on its own.
- `.github/workflows/ci.yml`: runs `test` and `lint` on every PR with a Postgres service container.
- `README.md`: setup in 5 commands, how to run tests. `CLAUDE.md`: stack, commands, the rules in
  `.claude/settings.json`, the ticket workflow (link to `tickets/README.md`), and: "money is
  integer cents, never floats".
- `.gitignore`, `.env.example`.
- Branch `develop` exists and is the PR target. `main` is protected for Kamran only.

## Out of scope
- Any model, API or page of the app itself.
- Authentication (ticket 006).

## Acceptance
- `make test` passes in the routine's cloud session against a real Postgres started by
  `scripts/cloud-setup.sh` (paste the command output in the PR description), and
  `USE_DOCKER=1 make test` is documented for the laptop.
- CI is green on the PR.
- No command in any script, Makefile or workflow can run forever (no `while`, `until`, `for`
  loops over `seq`, no `sleep` loops, no foreground dev servers).
- `ruff check` passes.

## Notes
- If Postgres cannot run inside the cloud session, do NOT silently switch to SQLite: open a
  `needs-operator` issue describing what failed and mark this ticket `blocked`. The whole
  build order depends on tests running against real Postgres.
- Keep `settings.py` ready for a `TEST` database override via env.
