# API (accounts)

All routes are under `/api/`, session-cookie authenticated. Errors are always `{code, detail}`.

| Route | Body | Result |
|---|---|---|
| `GET /api/me` | — | `{authenticated, profile: {id, display_name, email, main_group_id} \| null, guest_memberships: [member_id], google_enabled}`; sets the `csrftoken` cookie |
| `POST /api/auth/register` | `{email, password, display_name}` | logs in, returns the `/api/me` body |
| `POST /api/auth/login` | `{email, password}` | same |
| `POST /api/auth/google` | `{id_token}` | same; 503 `google_disabled` when `GOOGLE_CLIENT_ID` is unset |
| `POST /api/auth/logout` | — | clears the session (guest memberships too) |

## Error codes

| Code | Status |
|---|---|
| `email_taken`, `invalid_email`, `invalid_display_name`, `weak_password`, `google_conflict`, `invalid_request` | 400 |
| `invalid_credentials`, `google_invalid`, `not_authenticated` | 401 |
| `csrf_failed`, `forbidden` | 403 |
| `not_found` | 404 (also what a non-member gets for a group: existence is not revealed) |
| `throttled` | 429 |
| `google_disabled` | 503 |

## CSRF

Every POST needs the token: read the `csrftoken` cookie (set by `GET /api/me`) and send it as
`X-CSRFToken`. DRF exempts its views from the CSRF middleware, so the anonymous auth views
re-apply `csrf_protect` (`accounts/api/csrf.py`); new anonymous POST views must derive from
`CsrfProtectedAPIView`.

## Throttle

Login, register and Google share one bucket: 10 per minute per `REMOTE_ADDR`, signed in or not.
`X-Forwarded-For` is ignored (`NUM_PROXIES = 0`); trusting a proxy header and a shared cache are
release-step work. The counter lives in the per-process cache, so with several workers the real
limit is 10 per worker.

## Local development

The Vite dev server proxies `/api` to `localhost:8000` with `changeOrigin: false`, so the browser's
`Origin` equals the `Host` Django sees. That `Host` (`localhost:5173`) must pass `ALLOWED_HOSTS`;
the default does, and an env-driven value must keep `localhost`. With `changeOrigin: true`, set
`CSRF_TRUSTED_ORIGINS=http://localhost:5173`.

## Guests

`request.session["guest_member_ids"]` holds the member ids a guest holds. Use
`accounts.services.access.member_for` / `require_member` (404 for non-members) in every group endpoint.
