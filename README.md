# sharelo

See `docs/PLAN.md` and `tickets/README.md`.

## Setup (plain Postgres, e.g. a cloud session without Docker)

```
scripts/cloud-setup.sh   # run it, do not source it; starts PostgreSQL, creates role/db
make install
make test
make lint
```

The Makefile defaults `DATABASE_URL` to `postgres://sharelo:sharelo@localhost:5432/sharelo` and
`SECRET_KEY` to a test value, so nothing needs exporting. Running `pytest` directly (not via
`make`) needs `DATABASE_URL` and `SECRET_KEY` set: `settings.py` defaults to the compose host
`db:5432` and refuses to boot without a `SECRET_KEY`.

## Laptop with Docker

```
USE_DOCKER=1 make test
USE_DOCKER=1 make lint
docker compose up -d db backend frontend   # dev servers; always with -d
```

PostgreSQL is 17 in compose and CI, and the distro's 16 in cloud sessions; both are supported.

## Daily job

```
cd backend && python manage.py run_daily            # today = local date (timezone.localdate())
cd backend && python manage.py run_daily --today 2026-10-18
```

Step 1 refreshes ECB rates (a network failure is logged and does not stop step 2). Step 2 creates
every recurring expense that is due, catching up missed days; running it twice creates nothing
new. It prints rates upserted, expenses created and rules failed, and exits non-zero only when a
rule failed. Example cron line (scheduling it on a server is the release step):

```
15 6 * * * cd /srv/sharelo/backend && python manage.py run_daily >> /var/log/sharelo-daily.log 2>&1
```
