---
id: 015
title: Installable PWA, single-origin serving, laptop "production" compose
status: in-review
risk: normal
depends_on: [013, 014]
pr: 21
---

## Goal
The app installs to a phone's home screen and runs from one origin, so Kamran can test
`develop` on his phone through a Cloudflare tunnel from his laptop. This closes plan step 3.

## Scope
- `vite-plugin-pwa`: manifest (name Sharelo, short name, theme colour, 192/512 icons and a
  maskable one — simple generated SVG → PNG, no brand artwork), service worker with
  precached app shell and network-first for `/api/`; an offline page saying the app needs a
  connection (no offline writes). "Install" hint banner shown once on iOS/Android when not
  installed.
- Single origin: Django serves the built frontend — `whitenoise` for `frontend/dist` assets
  and a catch-all view returning `index.html` for non-`/api/` paths. `make build-frontend`
  runs before collectstatic.
- `compose.prod.yml` for the laptop: `db`, `backend` (gunicorn, `DEBUG=0`, secure cookie
  settings when `HTTPS=1`), `cron` service running `supercronic` with one line calling
  `run_daily` at 06:00; frontend built into the backend image (multi-stage Dockerfile).
  `.env.example` lists `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
  `GOOGLE_CLIENT_ID`. README: "Run it for real on your laptop" in 5 commands + the Cloudflare
  tunnel line (`cloudflared tunnel --url http://localhost:8000`).
- Production checklist: `python manage.py check --deploy` passes with the prod env; security
  headers set.

## Out of scope
- Real hosting, domain, email, licence, directory listings (release step).
- Push notifications, background sync.

## Acceptance
- e2e (screenshots): manifest is served with the right name and ≥ 2 icons; the service worker
  registers (`navigator.serviceWorker.ready` resolves); after one load, going offline and
  reloading shows the offline page instead of a browser error (Playwright `context.setOffline`).
- e2e: with the backend serving the built frontend (no vite preview), `/g/1/expenses` deep
  link returns `index.html` and the app renders the route; `/api/me` is not caught by the
  catch-all (KEY TEST: with the catch-all exclusion removed, `/api/me` would return HTML and
  the test must fail).
- `docker compose -f compose.prod.yml config` is valid; backend test asserts
  `check --deploy` emits no warnings under the prod env (run with
  `DJANGO_SETTINGS_MODULE` + env, not a live server).
- The `cron` service's command is the only long-running process added, and it lives in
  compose, not in any Makefile target or script.
- REPORT lists screenshots and states that the real phone install was not covered (Kamran
  does that).

## Notes
- Plan reference: "Key decisions → Mobile, Hosting"; build order step 3.
- After this merges, Kamran merges `develop` → `main` for the first time and tests on his
  phone.
