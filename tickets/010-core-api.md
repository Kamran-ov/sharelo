---
id: 010
title: Core REST API — groups, join, categories, expenses, balances, settlements, recurring
status: ready
risk: risky
depends_on: [007, 009]
pr:
---

## Goal
Everything the web app needs, as thin DRF views over the existing services. Only members of
a group (profile or guest session) can see or change it. The API is described by an OpenAPI
schema the frontend generates its types from.

## Scope
All under `/api/`, JSON, session auth from 009. Views call services; no business logic in views.
Every `LedgerError` → 400 `{code, detail}`.
- `GET/POST groups/` — list my groups (profile's and guest memberships), create
  `{name, currency, as_main}`; if the profile has no main group yet, `as_main` defaults true.
  `GET groups/{id}/` with members, currency, my member id, `is_main`, `link_active`.
  `POST groups/{id}/link {active}` → `set_link_active`.
- `GET join/{token}/` (public: group name, currency, member names) and
  `POST join/{token}/ {display_name}` → `join_group_by_token`; anonymous callers get a guest
  membership stored in the session; signed-in callers join with their profile.
- `GET categories/` — the two-level tree. `GET/PUT groups/{id}/category-defaults/`.
- `GET groups/{id}/expenses/?from&to&category&member&page` — newest first, 50 per page, each
  with payers and splits. `POST groups/{id}/expenses/` body
  `{description, amount_cents, date, category, payer_member, preset, params,
  original_currency?, original_amount_cents?, rate_used?}` → `create_expense_from_preset`;
  omitted `preset` → `default_split_for`. `PATCH/DELETE groups/{id}/expenses/{eid}/`.
  Advanced body: `{payers: {member: cents}, splits: {member: cents}, split_type}` →
  `create_expense`.
- `GET groups/{id}/balances/` → `{nets, transfers, members: [member_summary...]}`.
  `GET/POST groups/{id}/settlements/` → `record_settlement`.
  `POST groups/{id}/move-to-home {to_profile, amount_cents, date}` → `move_debt_to_home`;
  only when the group is not the caller's main group and both share one.
- `GET/POST groups/{id}/recurring/`, `PATCH/DELETE groups/{id}/recurring/{rid}/`,
  `POST .../pause`, `.../resume`, `.../skip`.
- `drf-spectacular`: `GET /api/schema/` (OpenAPI 3) and `/api/docs/`. `make schema` writes
  `frontend/src/api/schema.json`; CI fails if the committed schema is stale.
- Permissions: every group URL goes through `require_member` (404 for outsiders).
  Guests cannot create groups, change links, or call move-to-home.

## Out of scope
- Pages (011+), analytics endpoints (analytics step), bank/Splitwise import endpoints.
- Rate limiting beyond 009's auth throttles.

## Acceptance
- Outsider (signed in, not a member) gets 404 on every `groups/{id}/...` URL; a guest in the
  session gets 200 on the same URLs (one parametrised test over all routes — KEY TEST: it must
  fail if any single route forgets `require_member`).
- Create group as first group → it is the profile's main group; second group → `link_active`
  true; `as_main: true` on the second → no link, main group changes.
- Join by token anonymous → `/api/me.guest_memberships` contains the member; the same guest
  joining again returns the same member.
- Create expense with `preset: "half"` (50/50) returns splits of 2500/2500 for 5000; omitted
  preset uses the category default; foreign currency body stores `rate_used` and converted
  `amount_cents`; invalid sums → 400 with the service's code.
- Expense list paginates and filters; a deleted expense disappears from the list.
- Balances endpoint matches `net_balances`/`simplify_debts` on the same fixture; posting a
  settlement for the full transfer brings nets to zero in the next GET.
- Move-to-home from a main group → 400 code `not_a_sub_group`; from a trip → two settlements.
- Recurring: create, pause, skip, resume round-trip; `next_date` values match the service.
- Schema generates with zero warnings; `make schema` output equals the committed file.

## Notes
- Preset names for the API: `half` (50/50 of the two members), `personal`, `full_for_other`,
  `percentage` (params `{percent_payer}`), `equal`, `exact`, `shares`. Map to 002's functions.
- Plan reference: "Features → Adding an expense", "Balances and settle up".
