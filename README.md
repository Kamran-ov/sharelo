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
