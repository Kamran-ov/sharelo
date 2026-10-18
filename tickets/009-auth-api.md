---
id: 009
title: Sign-in API — email and password, Google, guest sessions
status: in-review
risk: risky
depends_on: [006]
pr:
---

## Goal
A browser can create an account with email and password or with a Google ID token, stay
signed in with a session cookie, and sign out. A guest can hold group memberships in the
session without an account. No pages yet; DRF endpoints only.

## Scope
- DRF with `SessionAuthentication` + CSRF. `CORS`/`CSRF_TRUSTED_ORIGINS` read from env so the
  Vite dev origin works locally; in production the frontend is served from the same origin.
- `accounts/api/`:
  - `POST /api/auth/register {email, password, display_name}` → creates `User` (username =
    email, lower-cased; unique case-insensitively) + `Profile`, logs in, returns `/api/me`
    shape. Django's default password validators apply. No email is sent (release step).
  - `POST /api/auth/login {email, password}`, `POST /api/auth/logout`.
  - `POST /api/auth/google {id_token}` → `accounts/services/google.py:verify_id_token(token)
    -> {email, sub, name}` using `google-auth`'s `id_token.verify_oauth2_token` with
    `GOOGLE_CLIENT_ID` from env; the function is the only place the library is called so
    tests stub it. Matches an existing user by email, else creates User + Profile. Stores
    `google_sub` on Profile. If `GOOGLE_CLIENT_ID` is unset the endpoint returns 503 with
    code `google_disabled` and `/api/me` reports `google_enabled: false`.
  - `GET /api/me` → `{authenticated, profile: {id, display_name, email, main_group_id},
    guest_memberships: [member_id...], google_enabled}`. Works for anonymous users too.
- Guest sessions: `request.session["guest_member_ids"]` list. Helper
  `accounts/services/access.py:member_for(request, group) -> Member | None` returns the
  caller's member in a group whether via profile or guest session, and `require_member`
  raises a 404 (not 403: don't reveal group existence). Used by every group endpoint in 010.
- Throttle login/register/google: 10 per minute per IP (DRF throttling).
- `LedgerError` and auth errors map to `{code, detail}` JSON with 400/401/404.

## Out of scope
- Password reset, email verification, email sending (release step).
- Group/expense endpoints (010), pages (011).
- Linking a Google login to an existing password account by anything other than same email.

## Acceptance
- Register → `/api/me` authenticated with the display name; a second register with the same
  email in different case returns 400 code `email_taken`.
- Login with wrong password → 401; correct → 200 and the session cookie works on `/api/me`.
- Logout clears the session; `/api/me` returns `authenticated: false`.
- Google: stubbed verifier returning a new email creates User + Profile with `google_sub`;
  returning an existing user's email logs that user in without creating anything (KEY TEST:
  user count unchanged); a verifier that raises → 401 code `google_invalid`; unset client id →
  503 `google_disabled`.
- Guest membership stored in the session is visible in `/api/me.guest_memberships`;
  `member_for` returns it; a different session gets `None`.
- `require_member` for a non-member returns 404, for a member returns the member.
- 11th login attempt within a minute from one IP → 429.
- Unsafe requests without CSRF token → 403 (one test proves CSRF is on).

## Notes
- Plan reference: "Key decisions → Access".
- Frontend will use Google Identity Services (the "Sign in with Google" button), which hands
  back an ID token; that is why the backend verifies a token rather than running OAuth
  redirects.
- `google-auth` is the only new dependency.
