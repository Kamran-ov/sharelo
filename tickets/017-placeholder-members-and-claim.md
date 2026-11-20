---
id: 017
title: Placeholder members, claim by link, guest to account
status: in-review
risk: risky
depends_on: [015]
pr: 25
---

## Goal
A group creator can add people by name only ("Janet", "Cami") and split bills with them before
they ever open the app. Anyone who later opens the share link can claim one of those names (no
account needed), and any guest can create an account at any time and keep the same member and
history. Losing a browser session no longer means losing the group.

## Scope
- Backend
  - `Member.claimed` state: a member is *unclaimed* when it has no profile and no guest session
    holds it. Track guest claims with `Member.guest_claimed_at` (nullable datetime).
  - `add_placeholder_member(group, display_name, by_member)` service; any member of the group
    (profile or guest) may add one. Unique (group, display_name) still holds.
  - `claim_member(token, member_id, session, profile=None)`: only an unclaimed member of that
    group can be claimed; with a profile the member gets `profile` set (and the normal GroupLink
    rule from 006 applies); without, the member id goes into the session's guest list and
    `guest_claimed_at` is set. Claiming an already-claimed member raises `LedgerError`
    `member_already_claimed`.
  - `release_guest(member)` used on guest logout: clears `guest_claimed_at` so the name becomes
    claimable again from the link.
  - Register / login / Google sign-in: if the session holds guest member ids, attach each of
    those members to the new or existing profile (refuse with `profile_already_in_group` if
    the profile already has a member in that group; keep the guest membership in that case).
  - API: `POST groups/{id}/members/ {display_name}`, `GET join/{token}/` now returns
    `unclaimed_members: [{id, display_name}]`, `POST join/{token}/claim {member_id}`.
- Frontend
  - Group Settings: "Add person" field (name only) and a member list showing who is
    "joined", "guest" or "not joined yet".
  - Join page: "Are you one of these?" list of unclaimed names (tap to claim) above the
    "I'm new" name field. Signed-in users claim with their profile.
  - Guest banner in the group shell: "You're a guest. Create an account to keep access on any
    device." → register/login sheet that keeps the claimed member.
  - Guest logout confirm: "You will lose access on this device. Save the group link or create
    an account first." with Copy link.

## Out of scope
- Removing or merging members, invitations by email, per-member permissions.

## Acceptance
- Creator adds Janet and Cami; an expense split equally among 3 works before either joins;
  balances show both.
- Fresh browser opens the link, sees Janet and Cami, taps Janet → lands in the group as Janet
  with the existing expense visible; a second fresh browser no longer sees Janet in the list
  (KEY test pair: claiming an already-claimed member → 400 `member_already_claimed`, nothing
  changes; claiming an unclaimed one succeeds).
- Guest Janet registers → her member now has her profile, the same id, all past splits; the
  guest session list is empty; `/api/me` shows the group under the profile.
- Guest Janet logs out → Janet appears again as claimable on the join page.
- A profile that already has a member in the group cannot also take over a guest member there
  (`profile_already_in_group`), and the guest membership is kept.
- e2e with phone-size screenshots for: add person, join-and-claim, guest banner, guest to
  account, logout warning.

## Notes
- Decision (Kamran): option C — the link is the key; claiming a name needs no account; an
  account is offered, never forced.
- Plan reference: "Groups and people". Guests still never appear in anyone's Home analytics.
