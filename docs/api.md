# API (accounts)

All routes are under `/api/`, session-cookie authenticated. Errors are always `{code, detail}`.

| Route | Body | Result |
|---|---|---|
| `GET /api/me` | — | `{authenticated, profile: {id, display_name, email, main_group_id} \| null, guest_memberships: [member_id], guest_refused: [{member_id, group_id, code}], google_enabled}`; sets the `csrftoken` cookie; `guest_refused` is `[]` except on a sign-in response |
| `POST /api/auth/register` | `{email, password, display_name}` | logs in, returns the `/api/me` body; the session's guest members are attached to the profile (same member id and history; see Guests) |
| `POST /api/auth/login` | `{email, password}` | same |
| `POST /api/auth/google` | `{id_token}` | same; 503 `google_disabled` when `GOOGLE_CLIENT_ID` is unset |
| `POST /api/auth/logout` | — | releases every guest member the session holds (their names become claimable from the link again), then clears the session |

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

Claim state of a member (017), derived from two columns: **joined** = has a profile; **guest** = no profile,
`guest_claimed_at` set; **unclaimed** = neither (only "Add person" creates these). `guest_claimed_at` is set
whenever anyone takes a member, profiles included, so a deleted profile (`SET_NULL`) leaves a guest, never a
claimable name.

On register / login / Google sign-in, `ledger.services.groups.adopt_guest_members` gives each guest member the
session holds to the profile. Where the profile already has a member in that group the guest is kept as it is
(still in the session) and reported in `guest_refused` with code `profile_already_in_group`; the sign-in itself
succeeds. A profile without a main group gets no `GroupLink` (006 rule) and the group does not become main.

# API (ledger)

Interactive docs at `/api/docs/`; the OpenAPI schema is `GET /api/schema/` and is committed as
`frontend/src/api/schema.json` (`make schema` rewrites it, `test_committed_schema_equals_generated`
fails when it is stale). Errors are `{code, detail}`; ledger codes are 400, `not_found` is 404.

Every `groups/{id}/...` view derives from `GroupScopedView` (`ledger/api/access.py`): a missing group
and a non-member both get the same 404 body, a guest session of that group is a member. All writes
need the CSRF token (see above), guests included.

| Path | Methods | Notes |
|---|---|---|
| `groups/` | GET, POST | GET rows: `id, name, currency, is_main, link_active` (`null` for the main group and guest sessions); POST `{name, currency, as_main?}`; first group is the main group; `as_main: true` when a main group exists → 400 `main_group_exists` |
| `groups/{id}/` | GET | members (with `profile_id`, `is_guest`, `status`: `joined` \| `guest` \| `unclaimed`), `my_member_id`, `is_main`, `link_active`, `share_token` |
| `groups/{id}/members/` | POST | `{display_name}` → 201 member row (`status: unclaimed`); any member, guests included; `name_taken`, `invalid_display_name` |
| `groups/{id}/link` | POST | `{active}`; profiles only (guest → 401) |
| `join/{token}/` | GET, POST | GET is public and sets the CSRF cookie, returns `group_name, currency, member_names, unclaimed_members: [{id, display_name}]`; POST `{display_name}` ("I'm new"); a guest who joins again gets the same member |
| `join/{token}/claim` | POST | `{member_id}` → `{group_id, member_id}`; takes an unclaimed member: with a profile the member gets it (and the 006 link rule), otherwise the session holds it as a guest. 400 `member_already_claimed`, `profile_already_in_group`, `already_in_group` (the session already holds a member of this group); 404 unknown token or member of another group |
| `categories/` | GET | two-level tree |
| `groups/{id}/category-defaults/` | GET, PUT | PUT replaces the whole set: `{"<category id>": {preset, params}}`; `half` is stored and returned as `equal` |
| `groups/{id}/expenses/` | GET, POST | list: `from`, `to`, `category` (id or parent id), `member`, `page`; 50 per page, newest first; a page past the end is 404; the page carries `month_totals` (`"YYYY-MM"` → cents, `amount_cents` summed over the whole filtered set for the months on the page, `personal` rows included, computed by `services.expenses.month_totals`); every expense row carries `recurring_rule` (the rule id for an expense a recurring rule created, else `null`) |
| `groups/{id}/rate/` | GET | `?currency=USD&date=YYYY-MM-DD` → `{currency, date, rate}` (group units per 1 foreign unit, string); 400 `no_rate` when there is none within 7 days; 400 `invalid_request` for the group's own currency; preview only, the POST stays the authority |
| `groups/{id}/expenses/{eid}/` | PATCH, DELETE | DELETE is soft and idempotent (204) |
| `groups/{id}/balances/` | GET | `nets`, `transfers` (`from_member` pays `to_member`; each carries `to_profile`, the creditor's profile id or null for a guest, and `can_move_to_home`, a display hint that is true only for the debtor's own session when the group is not their main group, both members have profiles, both profiles share that main group and the currencies match; `move-to-home` stays the authority), per-member `paid/owed_share/net` |
| `groups/{id}/summary/` | GET | the shareable summary (018): `group {id, name}`, `currency`, `total_spent_cents` (every live expense, `personal` included; equals the sum of `owed_share`), `per_member [{member_id, display_name, paid, owed_share, net}]`, `transfers [{from_member, to_member, amount_cents}]` (same as `balances`, without the Move-to-Home hints), `recent_expenses` (last 10 live, `-date, -id`, each `{id, date, description, amount_cents, paid_by: [member_id]}`); built only from `services/summary.py:group_summary`, constant queries; guests 200, outsiders 404 |
| `groups/{id}/settlements/` | GET, POST | POST `{from_member, to_member, amount_cents, date, notes?}`; rows carry `twin_group_name` (group of the twin row, null without a twin) and `is_home_side` (true for the Home row of a Move to Home pair); the badge reads "<trip>: moved to Home" with the trip = `twin_group_name` on the Home side, else the group's own name |
| `groups/{id}/settlements/{sid}/` | DELETE | soft delete (204); a row with a `twin` → 400 `twin_settlement`; another group's id → 404 |
| `groups/{id}/move-to-home` | POST | `{to_profile, amount_cents, date}`; the main group → 400 `not_a_sub_group` |
| `groups/{id}/recurring/` | GET, POST | rule fields use the model's `split_type` + `split_params` (service form) |
| `groups/{id}/recurring/{rid}/` | PATCH, DELETE | |
| `groups/{id}/recurring/{rid}/pause`, `resume`, `skip` | POST | `skip` on a paused rule is refused: 400 `rule_paused` (resume it first) |
| `groups/{id}/recurring/status/` | GET | `{last_run_at}`: when `run_daily` last ran (ISO datetime), `null` before the first run; same for every group |

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

## Bank imports (ticket 020)

`POST groups/{id}/bank-imports/` — multipart, field `file`: a Revolut personal-account CSV or a Wise
statement CSV (the bank is recognised by its header; any column order). Only money-out rows are
kept (Revolut: `State = COMPLETED`, `Amount ≤ 0`, amount = `Fee − Amount`; Wise: negative
`Amount`). New rows are stored as pending for the review list (021); rows already staged in this
group are skipped by id ([ADR 002](adr/002-bank-row-ids.md)). → 201
`{batch: {id, source, label, rows_seen, rows_created, rows_skipped, started_at, finished_at},
ignored, rows: [{id, date, amount_cents, currency, description, merchant, external_id, status}]}`.
`rows_seen` counts money-out rows only; `ignored` counts the other data rows (top-ups, declined,
reverted, money in). Foreign-currency rows keep their currency; conversion happens in 021.

`GET groups/{id}/bank-imports/{batch}/` → the same without `ignored`. A statement is personal:
a batch with rows is readable by its uploader only (404 for other members). A batch without rows
(everything was a duplicate) shows its counts to any member. Splitwise batches are not bank
imports (404).

Codes: 400 `unknown_bank_format` (detail: `revolut missing: …; wise missing: …`), 400
`bad_bank_row` (every unreadable line listed; nothing is staged), 400 `file_too_large` (> 2 MiB),
400 `invalid_request` (no `file`), 415 for a non-multipart body.

## Bank review list and shop rules (ticket 021)

Rows are the uploader's (as above): another member's row is 404. Shop rules are group data: every
member reads and edits them.

`GET groups/{id}/bank-rows/` → `{rows, category_splits}`. `rows`: my `pending` rows of every
batch, ordered by date, each with `suggestion: {category, category_name, decision, preset,
params, basis, rule}`. `decision` (`shared`/`personal`) is the highlighted button; `preset` and
`params` are the split the **Shared** button uses (never `personal`). Suggestion order: the
longest shop rule whose text is in the merchant or description (case-insensitive) → `basis
rule`; else the group's latest decided row for the same shop (preset and params from that row,
category from its expense) → `history`; else Uncategorized › General with its default →
`default`. A rule or history split the members no longer fit falls back to the category split.
`category_splits`: `{<leaf category id>: {preset, params}}` — the Shared split for a category
(its default; `equal` when that is `personal` or no longer valid). When the user changes a row's
category the page shows and sends `category_splits[new]`; choosing the suggested category again
restores the suggestion's own split. The server applies the same rule when `preset` is omitted.

`POST groups/{id}/bank-rows/{row}/resolve` `{decision: shared|personal|skip, category?, preset?,
params?, remember?}` → 200 `{row, expense, rule}`. Shared/Personal create the expense with
`create_expense_from_preset` (payer = the uploader, `source` = the bank, `external_id` = the
row's, foreign rows converted at the row's date); Skip creates nothing. `remember` creates or
updates the shop rule for the row's merchant (else description). Presets accept the sheet's
`half` and `percent_payer`. 400 codes: `row_already_resolved`, `shared_needs_split` (Shared with
`personal`), `remember_needs_category` (remember with skip), `no_rate`, `duplicate_external_id`
(the same bank row is already an expense in another group), `invalid_params`.

`POST groups/{id}/bank-rows/{row}/undo` → 200 row, back to `pending`; its expense is soft-deleted
(balances revert). Deciding again revives that same expense (a deleted expense keeps its
`(source, external_id)`). 400 `row_not_resolved` on a pending row. A remembered rule stays.

`GET groups/{id}/shop-rules/` → live rules `{id, match_text, category, category_name, preset,
params, created_by, last_used_at}`; `POST` → 201; `PATCH groups/{id}/shop-rules/{rule}/`;
`DELETE` → 204 (soft). 400 `duplicate_rule` (same text, case-insensitive), `invalid_category`
(a main type), `invalid_params`/`empty_members` (a split the group cannot take).

## Analytics (ticket 022)

Data only, for the dashboard step; built in `ledger/services/analytics_report.py` from
`services/analytics.py` and `services/home.py`, so every figure equals the service's to the cent.
Spending is the owed share (FACTS), in cents.

| Path | Params | Access |
|---|---|---|
| `groups/{id}/analytics/` | `from`, `to`, `by=member\|category\|month\|member_category`, `level=1\|2` | any member, guests included (the group's own spending, guests' shares counted); outsider 404 |
| `home/analytics/` | `from`, `to`, `by=member\|category\|month`, `trips=lines\|spread`, `level=1\|2` | the caller's main group plus active linked sub-groups, profiles only: guest session or anonymous → 401 `not_authenticated`, a profile without a main group → 404 |
| `home/analytics/trip/{group_id}/` | `from`, `to`, `level=1\|2` | same 401/404; a group not linked into the caller's Home (or missing) → 404 |

Response: `{currency, from, to, rows: [{key, label, cents}]}`; `member_category` and the trip
breakdown nest: `rows: [{key, label, cents, rows: [{key, label, cents}]}]`, the outer `cents`
being the sum of its inner rows. Every key is a string:

| Row | key | label | order |
|---|---|---|---|
| member | member id | display name | member id; `by=member` lists every member, 0 included |
| category | category id | level 1 the name, level 2 `Parent › Child` | cents desc, then key |
| trip line (Home `by=category&trips=lines`) | `trip:<group_id>` | trip name | with the categories |
| month | `YYYY-MM` | same | ascending, months with spending only |

Defaults: `from`/`to` are the current calendar month (server date), `by=category`, `level=1`,
`trips=lines`. `trips` changes only `by=category` (member and month totals are the same in both
modes; the totals are equal in both modes, the rows differ). Home trip guests and Home guests
never appear in Home analytics. The trip breakdown is in Home's currency, keyed by the trip's own
member ids. 400 codes: `invalid_date` (`from`/`to` not an ISO date), `invalid_range` (`from` after
`to`), `range_too_long` (`to` on or after `from` + 5 years), `invalid_by`, `invalid_level`,
`invalid_trips`, `no_rate` (a Home figure needs a missing rate).

Home `by=member_category` is not offered yet (400 `invalid_by`): `home.py` has no such function.
The dashboard ticket may need it; it would be added from the same converted cells.

# Frontend

`vite dev` (port 5173) and `vite preview` (port 4173) both proxy `/api` to Django with `changeOrigin: false`.
The e2e backend listens on 8001 and must be reached as `localhost`, never `127.0.0.1`, or Origin and Host differ
and CSRF fails. `E2E=1` is the browser-test mode (see `docs/e2e.md`); it is refused unless the database name ends
in `_e2e`.

## Unknown paths

Django serves the built SPA for every path that no route claims, except `api`, `admin` and `static`
(with or without a trailing slash). An unknown `/api/...` path is therefore a plain 404, never the
app shell.
