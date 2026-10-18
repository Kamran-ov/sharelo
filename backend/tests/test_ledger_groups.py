import datetime
import inspect

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from accounts.models import Profile
from ledger.errors import LedgerError
from ledger.models import Category, GroupLink, Member, Settlement
from ledger.services import groups
from ledger.services.balances import net_balances
from ledger.services.expenses import create_expense_from_preset
from ledger.services.groups import (
    create_group,
    join_group_by_token,
    move_debt_to_home,
    set_link_active,
)

pytestmark = pytest.mark.django_db

DAY = datetime.date(2026, 10, 1)


def make_profile(name: str) -> Profile:
    user = get_user_model().objects.create_user(username=name.lower())
    return Profile.objects.create(user=user, display_name=name)


def pay(group, payer: Member, amount: int, member_ids=None, currency="EUR"):
    return create_expense_from_preset(
        group,
        preset="equal",
        payer_id=payer.id,
        member_ids=member_ids,
        description="x",
        amount_cents=amount,
        currency=currency,
        date=DAY,
        category=Category.objects.get(name="Groceries"),
    )


def member_of(group, profile) -> Member:
    return Member.objects.get(group=group, profile=profile)


@pytest.fixture
def ann():
    return make_profile("Ann")


@pytest.fixture
def bea():
    return make_profile("Bea")


@pytest.fixture
def home(ann, bea):
    """Ann creates Home as her main group, Bea adopts it as hers through the services."""
    group = create_group(ann, "Home", "EUR", as_main=True)
    join_group_by_token(group.share_token, "Bea", bea, as_main=True)
    return group


@pytest.fixture
def trip(ann, bea, home):
    group = create_group(ann, "Rome", "EUR")
    join_group_by_token(group.share_token, "Bea", bea)
    return group


@pytest.fixture
def bea_paid_trip(trip, bea):
    """Bea pays 6000 split equally: Ann owes Bea 3000."""
    pay(trip, member_of(trip, bea), 6000)
    return trip


def nets_by_profile(group, *profiles):
    nets = net_balances(group)
    return {p.display_name: nets[member_of(group, p).id] for p in profiles}


# --- Move to Home ---------------------------------------------------------------------------


def test_move_to_home_shifts_debt_between_groups(bea_paid_trip, home, ann, bea):
    trip = bea_paid_trip
    in_trip, in_home = move_debt_to_home(trip, ann, bea, 3000, DAY)

    assert nets_by_profile(trip, ann, bea) == {"Ann": 0, "Bea": 0}
    assert nets_by_profile(home, ann, bea) == {"Ann": -3000, "Bea": 3000}
    assert Settlement.objects.count() == 2
    assert in_trip.twin_id == in_home.pk and in_home.twin_id == in_trip.pk


def test_move_to_home_is_all_or_nothing(bea_paid_trip, home, ann, bea, monkeypatch):
    real_create = Settlement.objects.create
    calls = []

    def fail_second(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("second insert failed")
        return real_create(**kwargs)

    monkeypatch.setattr(Settlement.objects, "create", fail_second)
    with pytest.raises(RuntimeError):
        move_debt_to_home(bea_paid_trip, ann, bea, 3000, DAY)
    monkeypatch.undo()

    assert Settlement.objects.count() == 0
    assert nets_by_profile(bea_paid_trip, ann, bea) == {"Ann": -3000, "Bea": 3000}
    move_debt_to_home(bea_paid_trip, ann, bea, 3000, DAY)
    assert Settlement.objects.count() == 2


def test_move_more_than_owed_refused(bea_paid_trip, ann, bea):
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, ann, bea, 3001, DAY)
    assert exc.value.code == "exceeds_debt"
    assert Settlement.objects.count() == 0


def test_move_in_parts_leaves_remainder_and_stops_at_zero(bea_paid_trip, ann, bea):
    move_debt_to_home(bea_paid_trip, ann, bea, 1000, DAY)
    assert nets_by_profile(bea_paid_trip, ann, bea) == {"Ann": -2000, "Bea": 2000}
    move_debt_to_home(bea_paid_trip, ann, bea, 2000, DAY)
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, ann, bea, 1, DAY)
    assert exc.value.code == "exceeds_debt"


def test_move_against_the_debt_direction_refused(bea_paid_trip, ann, bea):
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, bea, ann, 1000, DAY)
    assert exc.value.code == "exceeds_debt"


def test_only_a_direct_transfer_is_movable_with_three_people(home, ann, bea):
    cy = make_profile("Cy")
    join_group_by_token(home.share_token, "Cy", cy, as_main=True)
    trip = create_group(ann, "Alps", "EUR")
    join_group_by_token(trip.share_token, "Bea", bea)
    join_group_by_token(trip.share_token, "Cy", cy)
    ids = lambda *ps: [member_of(trip, p).id for p in ps]  # noqa: E731
    pay(trip, member_of(trip, cy), 4000, ids(ann, cy))  # Ann owes Cy 2000
    pay(trip, member_of(trip, cy), 2000, ids(bea, cy))  # Bea owes Cy 1000

    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(trip, ann, bea, 1, DAY)
    assert exc.value.code == "exceeds_debt"
    move_debt_to_home(trip, ann, cy, 2000, DAY)
    assert nets_by_profile(trip, ann, cy)["Ann"] == 0


def test_different_main_groups_refused(trip, ann, bea):
    other = make_profile("Dee")
    own_home = create_group(other, "Dee home", "EUR", as_main=True)
    join_group_by_token(trip.share_token, "Dee", other)
    pay(trip, member_of(trip, other), 6000)
    assert other.main_group_id == own_home.pk
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(trip, ann, other, 1000, DAY)
    assert exc.value.code == "main_group_mismatch"


def test_no_main_group_refused(ann, bea):
    trip = create_group(ann, "Rome", "EUR")
    join_group_by_token(trip.share_token, "Bea", bea)
    pay(trip, member_of(trip, bea), 6000)
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(trip, ann, bea, 1000, DAY)
    assert exc.value.code == "no_main_group"


def test_same_profile_refused(bea_paid_trip, ann):
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, ann, ann, 1000, DAY)
    assert exc.value.code == "same_profile"


def test_not_a_member_of_main_group_refused(bea_paid_trip, home, ann, bea):
    Member.objects.filter(group=home, profile=bea).delete()
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, ann, bea, 1000, DAY)
    assert exc.value.code == "not_a_member"


def test_trip_that_is_the_main_group_refused(home, ann, bea):
    pay(home, member_of(home, bea), 6000)
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(home, ann, bea, 1000, DAY)
    assert exc.value.code == "trip_is_main_group"


@pytest.mark.parametrize("amount", [0, -5])
def test_non_positive_amount_refused(bea_paid_trip, ann, bea, amount):
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(bea_paid_trip, ann, bea, amount, DAY)
    assert exc.value.code == "amount_not_positive"


def test_currency_mismatch_refused(home, ann, bea):
    usd_trip = create_group(ann, "NYC", "USD")
    join_group_by_token(usd_trip.share_token, "Bea", bea)
    pay(usd_trip, member_of(usd_trip, bea), 6000, currency="USD")
    with pytest.raises(LedgerError) as exc:
        move_debt_to_home(usd_trip, ann, bea, 1000, DAY)
    assert exc.value.code == "currency_mismatch"


# --- Linking --------------------------------------------------------------------------------


def test_group_with_main_creates_active_link(home, ann):
    trip = create_group(ann, "Rome", "EUR")
    link = GroupLink.objects.get()
    assert (link.profile_id, link.sub_group_id, link.main_group_id) == (ann.pk, trip.pk, home.pk)
    assert link.active


def test_first_group_without_main_creates_no_link(ann):
    create_group(ann, "Rome", "EUR")
    ann.refresh_from_db()
    assert GroupLink.objects.count() == 0
    assert ann.main_group_id is None


def test_as_main_sets_main_and_no_link(ann):
    group = create_group(ann, "Home", "EUR", as_main=True)
    ann.refresh_from_db()
    assert ann.main_group_id == group.pk
    assert GroupLink.objects.count() == 0


def test_as_main_twice_refused(home, ann):
    with pytest.raises(LedgerError) as exc:
        create_group(ann, "Second home", "EUR", as_main=True)
    assert exc.value.code == "main_group_exists"


def test_joining_with_main_creates_active_link(home, ann, bea):
    trip = create_group(ann, "Rome", "EUR")
    GroupLink.objects.all().delete()
    join_group_by_token(trip.share_token, "Bea", bea)
    link = GroupLink.objects.get()
    assert (link.profile_id, link.sub_group_id, link.main_group_id) == (bea.pk, trip.pk, home.pk)
    assert link.active


def test_joining_without_main_creates_no_link(ann, bea):
    trip = create_group(ann, "Rome", "EUR")
    join_group_by_token(trip.share_token, "Bea", bea)
    assert GroupLink.objects.count() == 0


def test_joining_as_main_sets_main_and_no_link(ann, bea):
    group = create_group(ann, "Home", "EUR")
    join_group_by_token(group.share_token, "Bea", bea, as_main=True)
    bea.refresh_from_db()
    assert bea.main_group_id == group.pk
    assert GroupLink.objects.count() == 0


def test_joining_as_main_twice_refused(home, ann, bea):
    other = create_group(ann, "Rome", "EUR")
    with pytest.raises(LedgerError) as exc:
        join_group_by_token(other.share_token, "Bea", bea, as_main=True)
    assert exc.value.code == "main_group_exists"


def test_existing_member_joining_as_main_adopts_when_none_set(ann, bea):
    group = create_group(ann, "Home", "EUR")
    join_group_by_token(group.share_token, "Bea", bea)
    again = join_group_by_token(group.share_token, "Bea", bea, as_main=True)
    bea.refresh_from_db()
    assert bea.main_group_id == group.pk
    assert again.profile_id == bea.pk


def test_guest_joining_as_main_refused(home):
    with pytest.raises(LedgerError) as exc:
        join_group_by_token(home.share_token, "Guest", None, as_main=True)
    assert exc.value.code == "guest_cannot_have_main"


def test_guest_join_creates_no_link_and_no_profile(trip):
    guest = join_group_by_token(trip.share_token, "Gus")
    assert guest.profile_id is None
    assert GroupLink.objects.filter(sub_group=trip).count() == 2  # Ann and Bea only


def test_joining_own_main_group_creates_no_self_link(home, ann):
    join_group_by_token(home.share_token, "Ann", ann)
    assert not GroupLink.objects.filter(sub_group=home).exists()


def test_deactivate_and_reactivate_never_duplicates_link(trip, ann):
    assert set_link_active(ann, trip, False).active is False
    join_group_by_token(trip.share_token, "Ann", ann)
    assert set_link_active(ann, trip, True).active is True
    assert GroupLink.objects.filter(profile=ann, sub_group=trip).count() == 1


def test_set_link_active_without_link_refused(home, ann):
    with pytest.raises(LedgerError) as exc:
        set_link_active(ann, home, False)
    assert exc.value.code == "no_link"


# --- Identity -------------------------------------------------------------------------------


def test_same_profile_joining_twice_returns_same_member(trip, bea):
    first = member_of(trip, bea)
    again = join_group_by_token(trip.share_token, "Another name", bea)
    assert again.pk == first.pk
    assert Member.objects.filter(group=trip, profile=bea).count() == 1


def test_second_profile_gets_its_own_member(trip, ann, bea):
    assert member_of(trip, ann).pk != member_of(trip, bea).pk


def test_db_refuses_profile_twice_in_group(trip, bea):
    with pytest.raises(IntegrityError), transaction.atomic():
        Member.objects.create(group=trip, display_name="Bea again", profile=bea)
    assert Member.objects.filter(group=trip, profile=bea).count() == 1


def test_guests_with_null_profile_may_repeat_in_a_group(trip):
    join_group_by_token(trip.share_token, "Gus")
    join_group_by_token(trip.share_token, "Gwen")
    assert Member.objects.filter(group=trip, profile__isnull=True).count() == 2


def test_name_taken_refused(trip):
    with pytest.raises(LedgerError) as exc:
        join_group_by_token(trip.share_token, "Bea")
    assert exc.value.code == "name_taken"


def test_same_name_in_another_group_allowed(home, trip):
    guest = join_group_by_token(home.share_token, "Gus")
    other = join_group_by_token(trip.share_token, "Gus")
    assert guest.pk != other.pk


def test_unknown_token_refused(db):
    with pytest.raises(LedgerError) as exc:
        join_group_by_token("nope", "Gus")
    assert exc.value.code == "unknown_group"


def test_groups_module_has_no_float_or_decimal():
    source = inspect.getsource(groups)
    for banned in ("float(", "Decimal(", "round(", " / "):
        assert banned not in source, banned
