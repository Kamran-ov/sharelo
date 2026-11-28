---
id: 025
title: Go-live hardening — sign-up switch, real client IP, safe rollback, alerts, ops docs
status: ready
risk: risky
depends_on: [024]
pr:
---

## Goal
The public deployment from 024 is safe to use every day: strangers cannot sign up unless
Kamran opens registration, rate limits work behind Cloudflare, a bad release rolls back
cleanly including the database, Kamran hears about failures by email and Telegram, and every
routine admin task has a documented command.

## Scope
1. Sign-up control
   - Setting `REGISTRATION_OPEN` (env, default `false`). When false, `POST /api/auth/register`
     and new-account Google sign-in return 403 `registration_closed`, EXCEPT when the session
     holds a valid group invite (the user opened a share link) — invited people can always
     create an account (ties into 017's guest-to-account flow).
   - Login page hides "Create account" when closed and no invite is in the session.
   - `/api/me` reports `registration_open`.
2. Real client IP behind Cloudflare
   - A single helper `client_ip(request)` uses `CF-Connecting-IP` only when the request came
     through the tunnel (setting `TRUST_CF_HEADER`, true in server deploy), else `REMOTE_ADDR`.
     DRF throttles and any logging use it.
3. Safe rollback with migrations
   - `autodeploy.sh` records whether the release applied new migrations
     (`showmigrations` before/after). On failed health check: if migrations were applied,
     restore the pre-deploy backup (from 024) before restarting the previous commit; log both.
4. Alerts (email and Telegram, free)
   - Healthchecks.io-style pings: `HC_BACKUP_URL`, `HC_DEPLOY_URL`, `HC_DAILY_URL` in `.env`;
     `backup.sh`, `autodeploy.sh` (only when a deploy ran) and `run_daily` ping `/start`,
     success, or `/fail` with a short reason. Empty URL = no ping. Network failure of a ping
     never fails the job.
   - `docs/ops.md`: how to create the free healthchecks.io checks and connect email and
     Telegram, plus a free external uptime check of `https://$SHARELO_HOST/api/me`.
5. Disk and logs
   - Docker logging options in the server compose: `json-file`, `max-size: 10m`, `max-file: 3`
     for every service. Backups older than 14 days pruned (already in 024; assert it).
6. Time zone
   - `TZ=Europe/Rome` for backend and cron; Django `TIME_ZONE` from env; the daily job runs at
     06:00 Rome time; test that "today" for recurring rules uses the configured zone.
7. Ops commands documented in `docs/ops.md` (each a single `docker compose ... exec` line):
   create the first account / superuser, reset a user's password, open/close registration,
   run the Splitwise import on the server (API key passed as a one-off env var, never written
   to `.env`), run a backup now, restore, view deploy log, see running version.
8. Google sign-in on the server: `docs/ops.md` section for adding `https://$SHARELO_HOST` as an
   authorised origin and setting `GOOGLE_CLIENT_ID`; app works with it unset.

## Out of scope
- Email sending (release step), Cloudflare Access, 2FA, multi-server.

## Acceptance
- Registration closed: register → 403 `registration_closed`; same request after opening a
  share link in that session → 201 (KEY pair). Open: register → 201. Google new user follows
  the same rules; existing Google user can always log in.
- Throttle: 11 login attempts from IP A behind the tunnel (different `CF-Connecting-IP`,
  same `REMOTE_ADDR`) → only A is throttled, IP B still logs in (KEY test: with `REMOTE_ADDR`
  used it fails). With `TRUST_CF_HEADER` false the header is ignored (spoofing twin).
- Rollback (stubbed git/curl/db): failed health check after a migrating release → restore
  called before restart; after a non-migrating release → restore not called.
- Pings: success and fail URLs hit with the right suffix (stub server); unreachable ping URL →
  job still exits 0 when the job itself succeeded.
- Compose test: every service in the server compose has the logging limits.
- TZ test as above.
- `docs/ops.md` contains every command in item 7; each command is executed in CI against the
  test stack where possible (create user, reset password, toggle registration, backup).

## Notes
- Decisions (Kamran, 2026-11-28): registration switch plus invite-based sign-up ("both");
  alerts by email and Telegram.
