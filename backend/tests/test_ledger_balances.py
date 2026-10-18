import inspect

import pytest

from ledger.errors import LedgerError
from ledger.models import ExpenseSplit, Group
from ledger.services import balances
from ledger.services.balances import (
    member_summary,
    net_balances,
    record_settlement,
    simplify_debts,
)
from ledger.services.expenses import (
    create_expense,
    create_expense_from_preset,
    delete_expense,
    update_expense,
)


def add(group, category, day, payer, amount, preset="equal", **kw):
    return create_expense_from_preset(
        group,
        preset=preset,
        payer_id=payer.id,
        description="x",
        amount_cents=amount,
        currency="EUR",
        date=day,
        category=category,
        **kw,
    )


@pytest.fixture
def mixed(group, members, category, day):
    ann, ben, cy = members
    add(group, category, day, ann, 1000)  # 334/333/333, Ann paid
    add(
        group,
        category,
        day,
        ben,
        900,
        "shares",
        params={"shares": {ann.id: 2, ben.id: 1}},
        member_ids=[ann.id, ben.id],
    )  # 600/300
    add(group, category, day, cy, 500, "personal")
    create_expense(  # two payers
        group,
        description="y",
        amount_cents=600,
        currency="EUR",
        date=day,
        category=category,
        payers={ann.id: 400, cy.id: 200},
        splits={ann.id: 100, ben.id: 200, cy.id: 300},
        split_type="exact",
    )
    record_settlement(group, ben, ann, 200, day)
    return members


# Ann: paid 1000+400=1400, owed 334+600+100=1034, received 200 -> +166
# Ben: paid 900, owed 333+300+200=833, sent 200 -> +267
# Cy: paid 500+200=700, owed 333+500+300=1133 -> -433


def test_nets_match_hand_computed_values(group, mixed):
    ann, ben, cy = mixed
    assert net_balances(group) == {ann.id: 166, ben.id: 267, cy.id: -433}


def test_nets_sum_to_zero(group, mixed):
    assert sum(net_balances(group).values()) == 0


def test_even_split_makes_other_owe_half(group, members, category, day):
    ann, ben, _ = members
    add(group, category, day, ann, 5000, member_ids=[ann.id, ben.id])
    nets = net_balances(group)
    assert nets == {ann.id: 2500, ben.id: -2500, members[2].id: 0}


def test_personal_expense_changes_no_net_but_shows_in_owed_share(group, members, category, day):
    ann, ben, _ = members
    add(group, category, day, ann, 700, "personal")
    assert set(net_balances(group).values()) == {0}
    assert member_summary(group, ann) == {"paid": 700, "owed_share": 700, "net": 0}
    add(group, category, day, ann, 700, member_ids=[ann.id, ben.id])  # twin: equal does move nets
    assert net_balances(group)[ben.id] == -350


def test_full_settlement_zeroes_nets_partial_reduces_exactly(group, members, category, day):
    ann, ben, _ = members
    add(group, category, day, ann, 5000, member_ids=[ann.id, ben.id])
    record_settlement(group, ben, ann, 1000, day)
    assert net_balances(group)[ben.id] == -1500
    record_settlement(group, ben, ann, 1500, day)
    nets = net_balances(group)
    assert nets[ann.id] == nets[ben.id] == 0


def test_simplify_three_members_in_at_most_two_transfers():
    nets = {1: 666, 2: -333, 3: -333}
    transfers = simplify_debts(nets)
    assert transfers == [(2, 1, 333), (3, 1, 333)]


def test_simplify_four_members_in_at_most_three_transfers():
    transfers = simplify_debts({1: 100, 2: -33, 3: -33, 4: -34})
    assert transfers == [(4, 1, 34), (2, 1, 33), (3, 1, 33)]
    assert len(transfers) <= 3


def test_applying_transfers_yields_zero():
    fixtures = [
        {1: 10, 2: -10},
        {1: 7, 2: 5, 3: -12},
        {1: 50, 2: -20, 3: -20, 4: -10},
        {1: 30, 2: 30, 3: -25, 4: -35},
        {1: 1, 2: 2, 3: 3, 4: -4, 5: -2},
        {1: 40, 2: -15, 3: 25, 4: -30, 5: 0, 6: -20},
    ]
    for nets in fixtures:
        applied = dict(nets)
        transfers = simplify_debts(nets)
        for frm, to, cents in transfers:
            assert cents > 0
            applied[frm] += cents
            applied[to] -= cents
        assert set(applied.values()) == {0}
        assert len(transfers) <= len([v for v in nets.values() if v]) - 1


def test_simplify_is_deterministic_on_ties():
    nets = {5: -10, 2: -10, 9: 10, 1: 10}
    first = simplify_debts(nets)
    assert first == [(2, 1, 10), (5, 9, 10)]
    assert simplify_debts(dict(reversed(list(nets.items())))) == first
    assert simplify_debts({}) == []


def test_edit_and_delete_change_nets(group, members, category, day):
    ann, ben, _ = members
    expense = add(group, category, day, ann, 1000, member_ids=[ann.id, ben.id])
    assert net_balances(group)[ben.id] == -500
    update_expense(
        expense,
        description="x",
        amount_cents=2000,
        currency="EUR",
        date=day,
        category=category,
        payers={ann.id: 2000},
        splits={ann.id: 1000, ben.id: 1000},
        split_type="equal",
    )
    assert net_balances(group)[ben.id] == -1000
    delete_expense(expense)
    assert set(net_balances(group).values()) == {0}


def test_other_group_activity_excluded(group, members, category, day):
    ann, ben, _ = members
    other = Group.objects.create(name="Other", currency="EUR")
    zed = other.members.create(display_name="Zed")
    yan = other.members.create(display_name="Yan")
    add(other, category, day, zed, 900, member_ids=[zed.id, yan.id])
    record_settlement(other, yan, zed, 100, day)
    assert set(net_balances(group).values()) == {0}
    assert set(net_balances(group)) == {m.id for m in members}


def test_record_settlement_rejects_invalid_input(group, members, day):
    ann, ben, _ = members
    other = Group.objects.create(name="Other", currency="EUR")
    stranger = other.members.create(display_name="Zed")
    for amount in (0, -5):
        with pytest.raises(LedgerError) as exc:
            record_settlement(group, ben, ann, amount, day)
        assert exc.value.code == "amount_not_positive"
    with pytest.raises(LedgerError) as exc:
        record_settlement(group, ann, ann, 100, day)
    assert exc.value.code == "same_member"
    with pytest.raises(LedgerError) as exc:
        record_settlement(group, stranger, ann, 100, day)
    assert exc.value.code == "member_not_in_group"
    settlement = record_settlement(group, ben, ann, 100, day, notes="cash")
    assert (settlement.amount_cents, settlement.currency, settlement.twin) == (100, "EUR", None)
    assert net_balances(group)[ben.id] == 100


def test_overpaying_settlement_is_allowed_and_balanced(group, members, category, day):
    ann, ben, _ = members
    add(group, category, day, ann, 1000, member_ids=[ann.id, ben.id])
    record_settlement(group, ben, ann, 800, day)
    nets = net_balances(group)
    assert nets[ben.id] == 300 and nets[ann.id] == -300


def test_member_summary_values(group, members, category, day):
    ann, ben, cy = members
    add(group, category, day, ann, 1000, member_ids=[ann.id, ben.id])
    assert member_summary(group, ann) == {"paid": 1000, "owed_share": 500, "net": 500}
    assert member_summary(group, ben) == {"paid": 0, "owed_share": 500, "net": -500}
    other = Group.objects.create(name="Other", currency="EUR")
    stranger = other.members.create(display_name="Zed")
    with pytest.raises(LedgerError) as exc:
        member_summary(group, stranger)
    assert exc.value.code == "member_not_in_group"


def test_unbalanced_nets_are_refused_not_returned(group, members, category, day):
    with pytest.raises(LedgerError) as exc:
        simplify_debts({1: 100, 2: -50})
    assert exc.value.code == "balance_drift"
    ann, ben, _ = members
    expense = add(group, category, day, ann, 1000, member_ids=[ann.id, ben.id])
    ExpenseSplit.objects.filter(expense=expense, member=ben).update(owed_cents=400)
    with pytest.raises(LedgerError) as exc:
        net_balances(group)
    assert exc.value.code == "balance_drift"


def test_balances_module_has_no_float_or_decimal():
    source = inspect.getsource(balances)
    for banned in ("float(", "Decimal(", "round(", " / "):
        assert banned not in source, banned
