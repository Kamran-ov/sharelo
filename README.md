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

## Import from Splitwise

A one-off import of a Splitwise group's history (`backend/importers/splitwise/`). Every expense
comes in with its real paid and owed shares, payments become settlements, and categories map one
to one. Re-running it creates nothing new.

**The first real run fixes every choice for good.** Re-runs skip rows by Splitwise id, and
nothing is ever hard-deleted, so the only undo is restoring a database dump. Take one first, and
import into a **new, empty** group:

```
pg_dump "$DATABASE_URL" > before-splitwise.sql
```

1. API key: on splitwise.com go to *Your account → Your apps*, register an app, and copy its
   **API key** (a personal key; no OAuth needed). Then `export SPLITWISE_API_KEY=...`. Only this
   command reads it; the app does not need it to boot.
2. Rates: if any expense is not in the group's currency, fetch the ECB history first:
   `python manage.py fetch_rates --since <date of the oldest Splitwise expense>`. Currencies the
   ECB never publishes (e.g. ARS) are listed as `no_rate`, and the import refuses to run.
3. Find the ids: the Splitwise group id is in the group's URL (`/groups/<id>`). Run once
   without `--map` and the command lists every Splitwise user to map, with our group's members.
4. Dry run (writes nothing), then read the printout: counts, errors, unknown categories, cent
   adjustments, and dates shifted by Europe/Rome:

```
cd backend
python manage.py import_splitwise --group 555 --into 7 --map 101=21 --map 102=22 --dry-run
python manage.py import_splitwise --group 555 --into 7 --map 101=21 --map 102=22
```

The real run prints a balance check. The group-currency line must have no ✗. Lines marked
`= after cent adjustment` are Splitwise rounding gaps (e.g. 1000.00 / 3) that we closed with our
one-cent rule. Foreign currencies are shown but not compared, because we convert at ECB rates.
A refusal of any kind (unmapped users, rows that cannot be imported, rows already in another of
our groups) writes nothing and exits non-zero.

Tested against recorded, anonymised fixtures and stubs only. The real API shapes (`balance[]`,
the `date` format, paging, users who left the group) and Bearer auth against the real host are
first exercised by your first `--dry-run`.

## Run it for real on your laptop

One origin, gunicorn, and the daily job on a clock; needs Docker (`compose.prod.yml`).

```
cp .env.example .env
# edit .env: set SECRET_KEY (generator line inside)
docker compose -f compose.prod.yml up -d --build
docker compose -f compose.prod.yml logs backend    # migrations ran, gunicorn listening
# open http://localhost:8000
```

Phone test through a Cloudflare tunnel: `cloudflared tunnel --url http://localhost:8000`, then switch modes.

| Mode | `.env` | Open |
|---|---|---|
| local | `HTTPS=0`, `ALLOWED_HOSTS=localhost,127.0.0.1` | `http://localhost:8000` |
| tunnel | `HTTPS=1`, `ALLOWED_HOSTS=<host>.trycloudflare.com`, `CSRF_TRUSTED_ORIGINS=https://<host>.trycloudflare.com` | the https URL the tunnel prints |

Switch by editing `.env`, then `docker compose -f compose.prod.yml up -d` (recreates `backend` with the new
environment). With `HTTPS=1` the app redirects plain http to https, so `localhost:8000` stops working until you
switch back. The `cron` service runs `python manage.py run_daily` at 06:00 UTC (08:00 Rome).

Without Docker: `make build-frontend` builds the SPA into `backend/frontend_dist` and collects static files;
Django then serves it at the site root.
