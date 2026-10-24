---
id: 016
title: Laptop Docker test run sees the whole repo; faster test hashing
status: in-review
risk: normal
depends_on: [015]
pr: 23
---

## Goal
`USE_DOCKER=1 make test` passes on Kamran's laptop exactly as it passes in CI and the cloud session. Today 9 backend tests fail only under Docker because the backend container sees `backend/` alone, so tests that read repo-root files (`compose.prod.yml`, `deploy/crontab`, `scripts/`, `frontend/src/api/schema.json`) get FileNotFoundError.

## Scope
- Make the repo root visible to the backend container for the test targets (for example mount `.` at `/repo` and set the working dir to `/repo/backend` in the compose service or in the Makefile's `USE_DOCKER=1` command). The tests' ROOT resolution must work unchanged in CI, cloud and Docker.
- `make test` with `USE_DOCKER=1` runs the frontend tests too, and vitest always runs in `run` mode (never watch), so the target always terminates.
- Test settings use a fast password hasher (`MD5PasswordHasher`) only under pytest, never in prod settings.

## Out of scope
- Any app behaviour change. Skipping or xfailing the 9 tests is NOT acceptable.

## Acceptance
- `USE_DOCKER=1 make test` on a clean checkout: backend 405 passed, 0 failed, then frontend vitest passes; paste both summary lines.
- The same 9 tests still pass in CI on the PR head.
- KEY test: `test_compose_prod_declares_expected_services` reds under Docker with the mount removed and passes with it (pair run shown).
- Backend suite time under Docker is reported before and after the hasher change.
- A test asserts prod settings do not use MD5PasswordHasher.

## Notes
- Root cause seen on the laptop: `PosixPath('/backend')` and `'/compose.prod.yml'` not found inside the container.
