"""Groups, membership and the link between a profile's main group and its other groups.

A profile with a main group gets an active `GroupLink` to every other group it creates or joins;
`_auto_link` is the single place that rule lives. Guests (no profile) never get a link or a main
group. `as_main` adopts a group as the profile's main group instead of linking it, which is how
two partners end up sharing one Home.

Claim state (017): a member with a profile is joined; without one it is a guest when
`guest_claimed_at` is set and unclaimed otherwise. Only `add_placeholder_member` creates unclaimed
members, and every claim is one guarded UPDATE so two people can never take the same name.

`move_debt_to_home` writes the twin settlement pair in one transaction, with the trip group row
locked so two concurrent calls cannot both spend the same debt.
"""

import datetime
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Profile
from ledger.errors import LedgerError
from ledger.models import Group, GroupLink, Member, Settlement
from ledger.services.balances import net_balances, simplify_debts


def _adopt_main(profile: Profile, group: Group) -> None:
    if profile.main_group_id is not None:
        raise LedgerError("main_group_exists", f"profile {profile.pk} already has a main group")
    profile.main_group = group
    profile.save(update_fields=["main_group"])


def _auto_link(profile: Profile, group: Group) -> None:
    if profile.main_group_id is None or profile.main_group_id == group.pk:
        return
    # get_or_create: an existing, possibly deactivated, link must stay as the user left it.
    GroupLink.objects.get_or_create(
        profile=profile, sub_group=group, defaults={"main_group_id": profile.main_group_id}
    )


@transaction.atomic
def create_group(profile: Profile, name: str, currency: str, as_main: bool = False) -> Group:
    if as_main and profile.main_group_id is not None:
        raise LedgerError("main_group_exists", f"profile {profile.pk} already has a main group")
    group = Group.objects.create(name=name, currency=currency)
    Member.objects.create(
        group=group,
        display_name=profile.display_name,
        profile=profile,
        guest_claimed_at=timezone.now(),
    )
    if as_main:
        _adopt_main(profile, group)
    else:
        _auto_link(profile, group)
    return group


@transaction.atomic
def join_group_by_token(
    token: str, display_name: str, profile: Profile | None = None, as_main: bool = False
) -> Member:
    group = Group.objects.filter(share_token=token).first()
    if group is None:
        raise LedgerError("unknown_group", "no group has this share token")
    if profile is None:
        if as_main:
            raise LedgerError("guest_cannot_have_main", "a guest has no profile")
        return _new_member(group, display_name, None)
    member = Member.objects.filter(group=group, profile=profile).first()
    if as_main and profile.main_group_id != group.pk:
        _adopt_main(profile, group)
    if member is not None:
        return member
    member = _new_member(group, display_name, profile)
    if not as_main:
        _auto_link(profile, group)
    return member


def _new_member(
    group: Group, display_name: str, profile: Profile | None, claimed: bool = True
) -> Member:
    if Member.objects.filter(group=group, display_name=display_name).exists():
        raise LedgerError("name_taken", f"{display_name!r} is already in group {group.pk}")
    return Member.objects.create(
        group=group,
        display_name=display_name,
        profile=profile,
        guest_claimed_at=timezone.now() if claimed else None,
    )


def _clean_name(display_name: str) -> str:
    name = (display_name or "").strip()
    if not 1 <= len(name) <= 100:
        raise LedgerError("invalid_display_name", "a name has 1 to 100 characters")
    return name


@transaction.atomic
def add_placeholder_member(group: Group, display_name: str, by_member: Member) -> Member:
    """A name only; anyone with the share link may later claim it."""
    if by_member.group_id != group.pk:
        raise LedgerError("not_a_member", f"member {by_member.pk} is not in group {group.pk}")
    return _new_member(group, _clean_name(display_name), None, claimed=False)


def _profile_in_group(profile: Profile, group: Group) -> bool:
    return Member.objects.filter(group=group, profile=profile).exists()


def _take(member_id: int, group: Group, profile: Profile | None) -> bool:
    """The one guarded write; False when someone else holds the member.

    The WHERE re-checks the claim under Postgres' row lock, so of two concurrent calls exactly one
    updates a row. The savepoint keeps a unique-constraint race from poisoning the caller's
    transaction; the caller decides what the IntegrityError means.
    """
    values: dict = {"guest_claimed_at": timezone.now()}
    if profile is not None:
        values["profile"] = profile
    with transaction.atomic():
        updated = Member.objects.filter(
            pk=member_id, group=group, profile__isnull=True, guest_claimed_at__isnull=True
        ).update(**values)
    return updated == 1


@transaction.atomic
def claim_member(
    token: str, member_id: int, guest_member_ids: list[int], profile: Profile | None = None
) -> Member:
    """Take an unclaimed member of the group behind `token`.

    The view reads `guest_member_ids` from the session and writes the claimed id back for a
    guest; the service never touches request objects.
    """
    group = Group.objects.filter(share_token=token).first()
    if group is None:
        raise LedgerError("not_found", "no group has this share token")
    if not Member.objects.filter(pk=member_id, group=group).exists():
        raise LedgerError("not_found", f"member {member_id} is not in group {group.pk}")
    if profile is not None:
        if _profile_in_group(profile, group):
            raise LedgerError("profile_already_in_group", f"profile {profile.pk} is in it")
    elif guest_member_ids and Member.objects.filter(group=group, id__in=guest_member_ids).exists():
        raise LedgerError("already_in_group", "this session already holds a member here")
    try:
        taken = _take(member_id, group, profile)
    except IntegrityError as exc:
        # Only uniq_member_group_profile can fire: the profile joined between check and write.
        raise LedgerError("profile_already_in_group", f"profile {profile.pk} is in it") from exc
    if not taken:
        raise LedgerError("member_already_claimed", f"member {member_id} is taken")
    if profile is not None:
        _auto_link(profile, group)
    return Member.objects.get(pk=member_id)


def release_guest(member: Member) -> None:
    """Guest logout: the name becomes claimable again. A member with a profile is never freed."""
    Member.objects.filter(pk=member.pk, profile__isnull=True).update(guest_claimed_at=None)


@dataclass
class AdoptResult:
    attached: list[int] = field(default_factory=list)
    kept: list[int] = field(default_factory=list)
    refused: list[tuple[int, int, str]] = field(default_factory=list)  # (member, group, code)


@transaction.atomic
def adopt_guest_members(profile: Profile, member_ids: list[int]) -> AdoptResult:
    """Sign-in: the session's guest members become the profile's, same id and history.

    A group where the profile already has a member keeps the guest as it is (`kept`). Ids whose
    member is gone or already has a profile are dropped. No main group → no link (006).
    """
    result = AdoptResult()
    guests = Member.objects.filter(id__in=member_ids or [], profile__isnull=True).select_related(
        "group"
    )
    for member in sorted(guests, key=lambda m: m.id):
        if _profile_in_group(profile, member.group):
            result.kept.append(member.id)
            result.refused.append((member.id, member.group_id, "profile_already_in_group"))
            continue
        try:
            with transaction.atomic():
                updated = Member.objects.filter(pk=member.pk, profile__isnull=True).update(
                    profile=profile
                )
        except IntegrityError:
            result.kept.append(member.id)
            result.refused.append((member.id, member.group_id, "profile_already_in_group"))
            continue
        if updated == 1:
            result.attached.append(member.id)
            _auto_link(profile, member.group)
    return result


def set_link_active(profile: Profile, group: Group, active: bool) -> GroupLink:
    link = GroupLink.objects.filter(profile=profile, sub_group=group).first()
    if link is None:
        raise LedgerError("no_link", f"profile {profile.pk} has no link to group {group.pk}")
    link.active = active
    link.save(update_fields=["active"])
    return link


def _member_in(group: Group, profile: Profile) -> Member:
    member = Member.objects.filter(group=group, profile=profile).first()
    if member is None:
        raise LedgerError("not_a_member", f"profile {profile.pk} is not in group {group.pk}")
    return member


def can_move_to_home(
    group: Group, home: Group | None, viewer: Member, from_member: Member, to_member: Member
) -> bool:
    """Display hint for the Move to Home button; `move_debt_to_home` stays the authority.

    `home` is the viewer's main group (None when they have none). Only the debtor's own session
    may move the debt: `move_debt_to_home` takes the caller as `from_profile`. Members arrive with
    `profile` already loaded so a page of transfers costs no extra queries.
    """
    if home is None or viewer.profile is None or to_member.profile is None:
        return False
    return (
        from_member.pk == viewer.pk
        and group.pk != home.pk
        and to_member.profile.main_group_id == home.pk
        and group.currency == home.currency
    )


@transaction.atomic
def move_debt_to_home(
    trip_group: Group,
    from_profile: Profile,
    to_profile: Profile,
    amount_cents: int,
    date: datetime.date,
) -> tuple[Settlement, Settlement]:
    if amount_cents <= 0:
        raise LedgerError("amount_not_positive", f"amount_cents={amount_cents}")
    if from_profile.pk == to_profile.pk:
        raise LedgerError("same_profile", "a debt needs two different people")
    if from_profile.main_group_id is None or to_profile.main_group_id is None:
        raise LedgerError("no_main_group", "both profiles need a main group")
    if from_profile.main_group_id != to_profile.main_group_id:
        raise LedgerError("main_group_mismatch", "the profiles do not share a main group")
    if trip_group.pk == from_profile.main_group_id:
        raise LedgerError("trip_is_main_group", "the group is already the main group")

    # Lock before reading nets: a second concurrent call must see this one's settlement.
    trip = Group.objects.select_for_update().get(pk=trip_group.pk)
    home = Group.objects.get(pk=from_profile.main_group_id)
    if trip.currency != home.currency:
        raise LedgerError("currency_mismatch", f"{trip.currency} trip, {home.currency} main group")

    trip_from, trip_to = _member_in(trip, from_profile), _member_in(trip, to_profile)
    home_from, home_to = _member_in(home, from_profile), _member_in(home, to_profile)

    owed = sum(
        cents
        for debtor, creditor, cents in simplify_debts(net_balances(trip))
        if (debtor, creditor) == (trip_from.pk, trip_to.pk)
    )
    if amount_cents > owed:
        raise LedgerError("exceeds_debt", f"{amount_cents} requested, {owed} owed")

    # The trip payment settles the debt there; the mirror runs the other way so the same
    # amount is now owed at Home.
    in_trip = Settlement.objects.create(
        group=trip,
        from_member=trip_from,
        to_member=trip_to,
        amount_cents=amount_cents,
        currency=trip.currency,
        date=date,
        notes=f"Moved to {home.name}",
    )
    in_home = Settlement.objects.create(
        group=home,
        from_member=home_to,
        to_member=home_from,
        amount_cents=amount_cents,
        currency=home.currency,
        date=date,
        notes=f"{trip.name}: moved to Home",
    )
    in_trip.twin, in_home.twin = in_home, in_trip
    in_trip.save(update_fields=["twin"])
    in_home.save(update_fields=["twin"])
    return in_trip, in_home
