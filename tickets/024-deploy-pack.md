---
id: 024
title: Deploy pack — one Ubuntu server behind Cloudflare Tunnel, nightly backups, auto-deploy
status: ready
risk: risky
depends_on: [016]
pr:
---

## Goal
Sharelo runs on one small Ubuntu VPS (any provider, ARM or x86), reachable over HTTPS through a
Cloudflare Tunnel on a fixed hostname, with the daily job, a nightly database backup that leaves
the server, and automatic deploys when `main` changes. Kamran sets it up by following one
document. No second service for the database, and no inbound ports open except SSH.

## Scope
- `deploy/compose.server.yml`: reuses `compose.prod.yml` (db, backend, cron) and adds
  `cloudflared` (official image) running `tunnel run` with `TUNNEL_TOKEN` from `.env`. The
  tunnel's public hostname (configured in the Cloudflare dashboard) points to
  `http://backend:8000`. NO service publishes a host port (db, backend, cloudflared all
  internal). Images must build on both `linux/arm64` and `linux/amd64` (CI builds both with
  buildx; no push needed).
- `.env` keys: `SHARELO_HOST` (e.g. `sharelo.example.com`), `TUNNEL_TOKEN`, `HTTPS=1`;
  `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` derived from `SHARELO_HOST` in `.env.example` and
  the docs. Django trusts Cloudflare's `X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`) so the
  https redirect does not loop; covered by a test.
- `deploy/backup.sh`: `pg_dump` (custom format) → `/var/backups/sharelo/sharelo-YYYY-MM-DD.dump`,
  keeps the last 14 locally; if `BACKUP_REMOTE` is set, copies the file with `rclone` to that
  remote (Cloudflare R2, Google Drive, any rclone backend). Exit non-zero on any failure.
  Runs nightly from the existing `cron` service (supercronic), 03:30 server time.
- `deploy/restore.sh <file>`: restores a dump into a fresh database; documented and tested.
- `deploy/update.sh`: `git pull` on `DEPLOY_BRANCH` (default `main`),
  `docker compose ... up -d --build`, runs migrations, prints the running commit. Never deletes
  volumes. Must terminate on its own.
- Auto-deploy on release (pull-based, no GitHub secrets, no inbound access needed):
  `deploy/autodeploy.sh` runs from the `cron` service every 10 minutes. It runs `git fetch` on
  `DEPLOY_BRANCH`; if the remote commit differs from the running one it takes a backup
  (`backup.sh`), runs `update.sh`, then checks `https://$SHARELO_HOST/api/me` returns 200 within
  60 s (one `curl --retry` with a time limit, not a loop). On failure it checks out the previous
  commit, rebuilds, restarts, and writes the reason to `/var/log/sharelo/deploy.log`. A lock file
  prevents overlapping runs. `AUTODEPLOY=0` in `.env` turns it off. The deployed commit is shown
  in Settings ("Version abc1234, deployed <date>").
- `deploy/bootstrap.sh`: for a fresh Ubuntu 24.04 VM — installs Docker Engine + compose plugin
  from Docker's apt repo, enables unattended security upgrades, `ufw` allows only 22, clones the
  repo, copies `.env.example` to `.env` and stops with a message to fill it in. Idempotent.
- `docs/deploy.md`: step-by-step for Kamran in plain language: create the VM (Oracle Always Free
  Arm or any VPS; provider firewall needs only SSH), in Cloudflare Zero Trust create a tunnel,
  add public hostname `sharelo.<domain>` → `http://backend:8000`, copy the token into `.env`,
  run bootstrap, first start, create the first account, set up the backup remote (R2), check a
  backup exists, how auto-deploy works and how to see its log, how to restore, how to change the
  hostname later.

## Out of scope
- Kubernetes, managed databases, push-based CI deploy (GitHub → SSH), Cloudflare Access
  policies, monitoring dashboards, email (release step).

## Acceptance
- CI job builds backend and frontend images for `linux/arm64` and `linux/amd64`.
- `docker compose -f compose.prod.yml -f deploy/compose.server.yml config` is valid; a test
  asserts NO service publishes a host port and that `cloudflared` reads `TUNNEL_TOKEN` from env.
- Behind a proxy sending `X-Forwarded-Proto: https`, a request is not redirected (test), and
  without it under `HTTPS=1` it is (twin).
- KEY test: backup then restore round trip — seed data, run `backup.sh` against the test
  database, drop it, run `restore.sh`, assert expense count and one balance are identical (red
  proof: restoring an empty file must fail the test).
- `backup.sh` exits non-zero when `pg_dump` fails and when the rclone copy fails (stubbed).
- Auto-deploy tests (git and curl stubbed): no new commit → nothing happens; new commit → backup
  then update in that order; failed health check → previous commit restored and the reason
  logged (pair with the success case); second run while the lock is held exits immediately;
  `AUTODEPLOY=0` → nothing happens.
- `update.sh`, `autodeploy.sh`, `bootstrap.sh` pass `shellcheck`; none contains a loop that can
  run forever.
- `docs/deploy.md` covers every step above; REPORT states the real server run is Kamran's and
  was not verified by the builder.

## Notes
- Hosting decision (Kamran, 2026-11-28): one VPS running the existing compose stack, exposed
  through Cloudflare Tunnel on a subdomain of a domain already in his Cloudflare account; Oracle
  Always Free Arm preferred, a ~€6/month VPS as fallback. Data is small (5 years ≈ 200 KB).
- Release = merge `develop` → `main`; the server deploys it by itself.
