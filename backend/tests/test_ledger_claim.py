"""017: placeholder members, claims, guest adoption; service level and Home analytics guard."""

import datetime
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from accounts.models import Profile
from ledger.errors import LedgerError
from ledger.models import Category, GroupLink, Member
from ledger.services import groups
from ledger.services.balances import net_balances
from ledger.services.expenses import create_expense_from_preset
from ledger.services.home import (
    home_spending_by_category,
    home_spending_by_member,
    home_spending_by_month,
)

D = datetime.date
WIDE = (D(2026, 1, 1), D(2026, 12, 31))
DAY = D(2026, 10, 2)


def make_profile(name: str) -> Profile:
    user = get_user_model().objects.create_user(username=name.lower())
    return Profile.objects.create(user=user, display_name=name)


def spend(group, payer, amount, member_ids):
    return create_expense_from_preset(
        group,
        preset="equal",
        payer_id=payer.id,
        member_ids=member_ids,
        description="x",
        amount_cents=amount,
        currency=group.currency,
        date=DAY,
        category=Category.objects.get(name="Groceries"),
    )


@pytest.fixture
def flat(db):
    alice = make_profile("Alice")
    group = groups.create_group(alice, "Flat", "EUR", as_main=True)
    me = Member.objects.get(group=group, profile=alice)
    return alice, group, me


@pytest.mark.django_db
def test_placeholder_is_unclaimed_and_creator_joined(flat):
    _, group, me = flat
    janet = groups.add_placeholder_member(group, "  Janet ", me)
    assert (janet.display_name, janet.claim_state) == ("Janet", "unclaimed")
    assert me.claim_state == "joined"


@pytest.mark.django_db
def test_add_placeholder_with_taken_name_is_refused(flat):
    _, group, me = flat
    groups.add_placeholder_member(group, "Janet", me)
    with pytest.raises(LedgerError) as exc:
        groups.add_placeholder_member(group, "Janet", me)
    assert exc.value.code == "name_taken"


@pytest.mark.django_db
def test_add_placeholder_blank_name_is_refused(flat):
    _, group, me = flat
    with pytest.raises(LedgerError) as exc:
        groups.add_placeholder_member(group, "   ", me)
    assert exc.value.code == "invalid_display_name"
    assert Member.objects.filter(group=group).count() == 1


@pytest.mark.django_db
def test_add_placeholder_by_member_of_other_group_is_refused(flat):
    alice, group, _ = flat
    other = groups.create_group(alice, "Other", "EUR")
    stranger = Member.objects.get(group=other, profile=alice)
    with pytest.raises(LedgerError) as exc:
        groups.add_placeholder_member(group, "Janet", stranger)
    assert exc.value.code == "not_a_member"


@pytest.mark.django_db
def test_guest_join_marks_member_guest_claimed(flat):
    _, group, _ = flat
    gus = groups.join_group_by_token(group.share_token, "Gus")
    assert gus.guest_claimed_at is not None and gus.claim_state == "guest"


@pytest.mark.django_db
def test_equal_expense_with_two_placeholders_balances_all_three(flat):
    _, group, me = flat
    janet = groups.add_placeholder_member(group, "Janet", me)
    cami = groups.add_placeholder_member(group, "Cami", me)
    expense = spend(group, me, 1000, [me.id, janet.id, cami.id])
    owed = dict(expense.splits.values_list("member_id", "owed_cents"))
    assert owed == {me.id: 334, janet.id: 333, cami.id: 333}
    nets = net_balances(group)
    assert nets == {me.id: 666, janet.id: -333, cami.id: -333}
    assert sum(nets.values()) == 0


@pytest.mark.django_db
def test_guest_claim_sets_claimed_at_and_second_claim_is_refused(flat):
    _, group, me = flat
    janet = groups.add_placeholder_member(group, "Janet", me)
    claimed = groups.claim_member(group.share_token, janet.id, [])
    assert claimed.claim_state == "guest"
    before = Member.objects.values().get(pk=janet.id)
    with pytest.raises(LedgerError) as exc:
        groups.claim_member(group.share_token, janet.id, [])
    assert exc.value.code == "member_already_claimed"
    assert Member.objects.values().get(pk=janet.id) == before


@pytest.mark.django_db
def test_claiming_a_profile_member_is_refused(flat):
    _, group, me = flat
    with pytest.raises(LedgerError) as exc:
        groups.claim_member(group.share_token, me.id, [])
    assert exc.value.code == "member_already_claimed"


@pytest.mark.django_db
def test_signed_in_claim_sets_profile_and_auto_links(flat):
    _, group, me = flat
    trip_owner = make_profile("Tom")
    trip = groups.create_group(trip_owner, "Trip", "EUR", as_main=True)
    janet = groups.add_placeholder_member(trip, "Janet", Member.objects.get(group=trip))
    alice = me.profile
    claimed = groups.claim_member(trip.share_token, janet.id, [], alice)
    assert claimed.profile_id == alice.id and claimed.claim_state == "joined"
    link = GroupLink.objects.get(profile=alice, sub_group=trip)
    assert (link.main_group_id, link.active) == (group.id, True)


@pytest.mark.django_db
def test_signed_in_claim_refused_when_profile_already_in_group(flat):
    alice, group, me = flat
    janet = groups.add_placeholder_member(group, "Janet", me)
    with pytest.raises(LedgerError) as exc:
        groups.claim_member(group.share_token, janet.id, [], alice)
    assert exc.value.code == "profile_already_in_group"
    assert Member.objects.get(pk=janet.id).claim_state == "unclaimed"


@pytest.mark.django_db
def test_guest_session_cannot_claim_a_second_member_in_same_group(flat):
    _, group, me = flat
    janet = groups.add_placeholder_member(group, "Janet", me)
    cami = groups.add_placeholder_member(group, "Cami", me)
    groups.claim_member(group.share_token, janet.id, [])
    with pytest.raises(LedgerError) as exc:
        groups.claim_member(group.share_token, cami.id, [janet.id])
    assert exc.value.code == "already_in_group"
    assert Member.objects.get(pk=cami.id).claim_state == "unclaimed"


@pytest.mark.django_db
def test_guest_session_can_claim_in_another_group(flat):
    alice, group, me = flat
    other = groups.create_group(alice, "Other", "EUR")
    janet = groups.add_placeholder_member(group, "Janet", me)
    jo = groups.add_placeholder_member(other, "Jo", Member.objects.get(group=other))
    groups.claim_member(group.share_token, janet.id, [])
    assert groups.claim_member(other.share_token, jo.id, [janet.id]).claim_state == "guest"


@pytest.mark.django_db
def test_release_guest_frees_only_profileless_members(flat):
    _, group, me = flat
    gus = groups.join_group_by_token(group.share_token, "Gus")
    groups.release_guest(gus)
    groups.release_guest(me)
    assert Member.objects.get(pk=gus.id).claim_state == "unclaimed"
    assert Member.objects.get(pk=me.id).guest_claimed_at is not None


@pytest.mark.django_db
def test_deleted_profile_leaves_a_guest_not_a_claimable_name(flat):
    # Member.profile is SET_NULL: the history of a deleted person must not be up for grabs.
    alice, group, me = flat
    alice.user.delete()
    left = Member.objects.get(pk=me.id)
    assert left.profile_id is None and left.claim_state == "guest"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_profile_claim_race_into_unique_constraint_is_refused_cleanly(flat, monkeypatch):
    alice, group, me = flat
    trip = groups.create_group(make_profile("Tom"), "Trip", "EUR")
    janet = groups.add_placeholder_member(trip, "Janet", Member.objects.get(group=trip))
    Member.objects.create(group=trip, display_name="Alice", profile=alice)
    # The pre-check lost the race: the profile's member appeared between check and write.
    monkeypatch.setattr(groups, "_profile_in_group", lambda profile, group: False)
    with pytest.raises(LedgerError) as exc:
        groups.claim_member(trip.share_token, janet.id, [], alice)
    assert exc.value.code == "profile_already_in_group"
    assert Member.objects.get(pk=janet.id).claim_state == "unclaimed"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_adopt_race_on_one_member_still_attaches_the_next(flat, monkeypatch):
    alice, group, _ = flat
    tom = make_profile("Tom")
    t1 = groups.create_group(tom, "T1", "EUR")
    t2 = groups.create_group(tom, "T2", "EUR")
    g1 = groups.join_group_by_token(t1.share_token, "Jan")
    g2 = groups.join_group_by_token(t2.share_token, "Jan")
    Member.objects.create(group=t1, display_name="Alice", profile=alice)
    monkeypatch.setattr(groups, "_profile_in_group", lambda profile, group: False)
    result = groups.adopt_guest_members(alice, [g1.id, g2.id])
    assert result.attached == [g2.id]
    assert result.kept == [g1.id]
    assert result.refused == [(g1.id, t1.id, "profile_already_in_group")]
    assert Member.objects.get(pk=g1.id).profile_id is None
    assert Member.objects.get(pk=g2.id).profile_id == alice.id


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_claims_leave_exactly_one_winner(flat):
    _, group, me = flat
    janet = groups.add_placeholder_member(group, "Janet", me)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def claim():
        try:
            barrier.wait(timeout=10)
            groups.claim_member(group.share_token, janet.id, [])
            outcomes.append("ok")
        except LedgerError as exc:
            outcomes.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["member_already_claimed", "ok"]


@pytest.mark.django_db
def test_placeholder_shares_never_in_home_analytics(flat):
    _, home, me = flat
    janet = groups.add_placeholder_member(home, "Janet", me)
    spend(home, me, 1000, [me.id, janet.id])
    assert home_spending_by_member(home, *WIDE) == {me.id: 500}
    assert sum(home_spending_by_category(home, *WIDE).values()) == 500
    assert home_spending_by_month(home, *WIDE) == {"2026-10": 500}


@pytest.mark.django_db
def test_adopted_member_shares_appear_in_her_home_only(flat):
    alice, alice_home, alice_me = flat
    trip = groups.create_group(alice, "Trip", "EUR")
    alice_trip = Member.objects.get(group=trip, profile=alice)
    janet = groups.join_group_by_token(trip.share_token, "Janet")
    spend(trip, alice_trip, 1000, [alice_trip.id, janet.id])
    jo = make_profile("Jo")
    jo_home = groups.create_group(jo, "JoHome", "EUR", as_main=True)
    jo_home_me = Member.objects.get(group=jo_home, profile=jo)
    alice_before = (
        home_spending_by_member(alice_home, *WIDE),
        home_spending_by_category(alice_home, *WIDE),
        home_spending_by_month(alice_home, *WIDE),
    )
    assert home_spending_by_member(jo_home, *WIDE) == {jo_home_me.id: 0}

    result = groups.adopt_guest_members(jo, [janet.id])

    assert result.attached == [janet.id]
    assert GroupLink.objects.get(profile=jo, sub_group=trip).active is True
    assert home_spending_by_member(jo_home, *WIDE) == {jo_home_me.id: 500}
    assert (
        home_spending_by_member(alice_home, *WIDE),
        home_spending_by_category(alice_home, *WIDE),
        home_spending_by_month(alice_home, *WIDE),
    ) == alice_before


@pytest.mark.django_db
def test_adopt_keeps_guest_where_profile_already_in_group(flat):
    alice, group, _ = flat
    gus = groups.join_group_by_token(group.share_token, "Gus")
    result = groups.adopt_guest_members(alice, [gus.id])
    assert (result.attached, result.kept) == ([], [gus.id])
    assert result.refused == [(gus.id, group.id, "profile_already_in_group")]
    assert Member.objects.get(pk=gus.id).claim_state == "guest"


@pytest.mark.django_db
def test_adopt_drops_ids_that_already_have_a_profile(flat):
    alice, group, me = flat
    jo = make_profile("Jo")
    result = groups.adopt_guest_members(jo, [me.id, 999999])
    assert (result.attached, result.kept, result.refused) == ([], [], [])
    assert Member.objects.get(pk=me.id).profile_id == alice.id


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_migration_marks_existing_members_claimed():
    executor = MigrationExecutor(connection)
    executor.migrate([("ledger", "0008_jobrun")])
    apps = executor.loader.project_state([("ledger", "0008_jobrun")]).apps
    OldGroup = apps.get_model("ledger", "Group")
    OldMember = apps.get_model("ledger", "Member")
    group = OldGroup.objects.create(name="Old", currency="EUR", share_token="old-token")
    guest = OldMember.objects.create(group=group, display_name="Gus")

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    assert Member.objects.get(pk=guest.pk).claim_state == "guest"
    assert not Member.objects.filter(guest_claimed_at__isnull=True).exists()
