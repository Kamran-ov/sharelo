---
id: 006
title: Profiles, main group, linked sub-groups, Move to Home
status: ready
risk: risky
depends_on: [003]
pr:
---

## Goal
The app knows "it's the same me in every group". A profile has one main group; other groups it
joins are linked sub-groups by default. Guests without a profile join a group by link with
just a name. Leftover debt between two profiles in a trip can be moved into their main group.

## Scope
- `accounts.Profile` (replace the stub from 001): Django `User` one-to-one, display_name,
  `main_group` (nullable FK to Group), created_at. Sign-in methods themselves (Google, email
  and password) are a later web ticket; this ticket only needs `User` + `Profile`.
- `GroupLink`: profile, sub_group, main_group, `active` bool, created_at. Unique (profile, sub_group).
- Services in `ledger/services/groups.py`:
  - `create_group(profile, name, currency, as_main=False)` — creates group + a Member for the
    profile; if the profile already has a main group and `as_main` is False, auto-creates an
    active GroupLink.
  - `join_group_by_token(token, display_name, profile=None)` — creates a Member; with a profile,
    auto-links (same rule). Returns the member. Idempotent for the same profile.
  - `set_link_active(profile, group, active)`.
  - `move_debt_to_home(trip_group, from_profile, to_profile, amount_cents, date)` — creates a
    Settlement in the trip (from→to) and a mirror Settlement in the shared main group (to→from),
    each pointing at the other via `twin`, in one transaction. Both profiles must share the same
    main group; amount must not exceed what from owes to in the trip's simplified debts.
- Member ↔ Profile identity: a profile can appear in a group only once.

## Out of scope
- Auth endpoints, Google OAuth, password reset, session handling.
- Analytics rollup of linked groups into Home (next ticket after this).

## Acceptance
- A profile with a main group that creates or joins a second group gets an active link; a
  profile without a main group gets none; a guest (no profile) gets none.
- Deactivating a link and re-activating it never creates a duplicate.
- `move_debt_to_home` creates exactly two settlements, each `twin` of the other, trip nets
  reduce by the amount, main-group nets change by the same amount in the opposite direction;
  the whole thing rolls back if the second insert fails.
- Moving more than is owed raises `LedgerError`; profiles with different main groups raise.
- The same profile joining the same group twice returns the existing member.

## Notes
- Plan reference: "Key decisions" and "Features → Groups and people" in `docs/PLAN.md`.
- A guest Member has `profile = NULL`; their shares never appear in anyone's Home analytics
  (enforced in the rollup ticket, not here).
