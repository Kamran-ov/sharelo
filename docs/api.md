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

# API (ledger)

Interactive docs at `/api/docs/`; the OpenAPI schema is `GET /api/schema/` and is committed as
`frontend/src/api/schema.json` (`make schema` rewrites it, `test_committed_schema_equals_generated`
fails when it is stale). Errors are `{code, detail}`; ledger codes are 400, `not_found` is 404.

Every `groups/{id}/...` view derives from `GroupScopedView` (`ledger/api/access.py`): a missing group
and a non-member both get the same 404 body, a guest session of that group is a member. All writes
need the CSRF token (see above), guests included.

| Path | Methods | Notes |
|---|---|---|
| `groups/` | GET, POST | POST `{name, currency, as_main?}`; first group is the main group; `as_main: true` when a main group exists → 400 `main_group_exists` |
| `groups/{id}/` | GET | members (with `profile_id`, `is_guest`), `my_member_id`, `is_main`, `link_active`, `share_token` |
| `groups/{id}/link` | POST | `{active}`; profiles only (guest → 401) |
| `join/{token}/` | GET, POST | GET is public and sets the CSRF cookie; POST `{display_name}`; a guest who joins again gets the same member |
| `categories/` | GET | two-level tree |
| `groups/{id}/category-defaults/` | GET, PUT | PUT replaces the whole set: `{"<category id>": {preset, params}}`; `half` is stored and returned as `equal` |
| `groups/{id}/expenses/` | GET, POST | list: `from`, `to`, `category` (id or parent id), `member`, `page`; 50 per page, newest first; a page past the end is 404 |
| `groups/{id}/expenses/{eid}/` | PATCH, DELETE | DELETE is soft and idempotent (204) |
| `groups/{id}/balances/` | GET | `nets`, `transfers` (`from_member` pays `to_member`), per-member `paid/owed_share/net` |
| `groups/{id}/settlements/` | GET, POST | POST `{from_member, to_member, amount_cents, date, notes?}` |
| `groups/{id}/move-to-home` | POST | `{to_profile, amount_cents, date}`; the main group → 400 `not_a_sub_group` |
| `groups/{id}/recurring/` | GET, POST | rule fields use the model's `split_type` + `split_params` (service form) |
| `groups/{id}/recurring/{rid}/` | PATCH, DELETE | |
| `groups/{id}/recurring/{rid}/pause`, `resume`, `skip` | POST | |

## Creating an expense

Body `{description, amount_cents, date, category, payer_member, preset?, params?, notes?}`. Amounts are
JSON integers (cents); `50.0`, `"50"` and `true` are 400. The group's currency is the expense currency.
A foreign expense sends `original_currency` + `original_amount_cents` (and no `amount_cents`): the
amount is converted at that date's rate and `rate_used` (a string, group units per 1 original unit)
is stored. Advanced: `{payers: {member: cents}, splits: {member: cents}, split_type, amount_cents}`;
combining it with `preset` is 400 `invalid_request`.

| `preset` | `params` | Stored `split_type` |
|---|---|---|
| `half` | — (exactly two members, else `invalid_params`) | `equal` |
| omitted | the category default of the group, else `equal` | as the default |
| `equal`, `personal` | — | same |
| `full_for_other` | `other_id` (optional with two members) | same |
| `percentage` | `percent_payer` (integer 0–100, two members) or `basis_points {member: bp}` | same |
| `exact` | `cents {member: cents}` | same |
| `shares` | `shares {member: n}` | same |

## Changing an expense (PATCH)

An expense keeps its `split_type` but not the preset params, so splits are never guessed.
- Description, category, notes, and `date` on a same-currency expense keep payers and splits.
- A changed `amount_cents` or `payer_member` with `preset` (+`params`) or `payers`+`splits` in the body
  uses the body. Without them it recomputes only when the stored split reproduces from `equal`,
  `personal` or two-member `full_for_other`; otherwise 400 `invalid_request`.
- A `date` change on a foreign expense converts the original amount again at the new date's rate;
  for `percentage`, `exact`, `shares` and advanced expenses that changes the amount, so it is the same
  400 `invalid_request` unless the body carries the splits.

New codes: `not_a_sub_group`, `unknown_profile`, `invalid_params` (bad preset params).
