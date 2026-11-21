import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from importers.banks import review, shop_rules, staging
from importers.models import ShopRule
from ledger.errors import LedgerError
from ledger.models import Category, CategoryDefault, ExchangeRate, Expense, Group, Member
from ledger.services.balances import net_balances
from ledger.services.expenses import update_expense

FIXTURES = Path(__file__).parent / "fixtures" / "banks"

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair(db):
    group = Group.objects.create(name="Home", currency="EUR")
    alice = Member.objects.create(group=group, display_name="Alice")
    bea = Member.objects.create(group=group, display_name="Bea")
    return group, alice, bea


@pytest.fixture
def cats(db):
    return {
        "groceries": Category.objects.get(name="Groceries"),
        "dining": Category.objects.get(name="Dining out"),
        "general": Category.objects.get(name="General", parent__name="Uncategorized"),
    }


def stage(group, member, name):
    data = (FIXTURES / name).read_bytes()
    batch = staging.stage_bank_file(group, member, SimpleUploadedFile(name, data)).batch
    return {r.description: r for r in batch.bank_rows.all()}


def rule(group, member, text, category, preset="equal", params=None):
    return shop_rules.save_rule(
        group, member, match_text=text, category=category, preset=preset, params=params
    )


def splits_of(expense):
    return {s.member_id: s.owed_cents for s in expense.splits.all()}


# ---- KEY and the default branch ----


def test_rule_prefills_row_and_one_tap_creates_groceries_half(pair, cats):
    group, alice, bea = pair
    rule(group, alice, "Esselunga", cats["groceries"])
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]

    hint = review.suggest(row)
    assert (hint.category, hint.decision, hint.preset, hint.basis) == (
        cats["groceries"],
        "shared",
        "equal",
        "rule",
    )

    done = review.resolve_row(row, alice, "shared")
    expense = done.expense
    assert expense.category == cats["groceries"]
    assert expense.split_type == "equal"
    assert expense.amount_cents == 4520
    assert {p.member_id: p.paid_cents for p in expense.payers.all()} == {alice.id: 4520}
    assert splits_of(expense) == {alice.id: 2260, bea.id: 2260}
    assert (expense.source, expense.external_id) == ("revolut", row.external_id)
    row.refresh_from_db()
    assert row.status == "shared"
    assert row.expense_id == expense.id


def test_row_without_rule_or_history_suggests_uncategorized_and_category_default(pair, cats):
    group, alice, bea = pair
    CategoryDefault.objects.create(
        group=group,
        category=cats["general"],
        split_type="percentage",
        split_params={"basis_points": {str(alice.id): 7000, str(bea.id): 3000}},
    )
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    hint = review.suggest(row)
    assert (hint.category, hint.decision, hint.preset, hint.basis) == (
        cats["general"],
        "shared",
        "percentage",
        "default",
    )
    expense = review.resolve_row(row, alice, "shared").expense
    assert expense.category == cats["general"]
    assert splits_of(expense) == {alice.id: 3164, bea.id: 1356}


# ---- rules ----


def test_longest_matching_rule_wins(pair, cats):
    group, alice, _ = pair
    rule(group, alice, "Esselunga", cats["general"])
    rule(group, alice, "Esselunga Milano", cats["groceries"])
    row = stage(group, alice, "revolut_review_next.csv")["ESSELUNGA MILANO"]
    assert review.suggest(row).category == cats["groceries"]


def test_rule_matches_merchant_or_description_case_insensitively(pair, cats):
    group, alice, _ = pair
    rule(group, alice, "esselunga", cats["groceries"])
    row = stage(group, alice, "revolut_review_next.csv")["ESSELUNGA MILANO"]
    assert review.suggest(row).basis == "rule"

    wise_group = Group.objects.create(name="W", currency="EUR")
    wanda = Member.objects.create(group=wise_group, display_name="Wanda")
    rule(wise_group, wanda, "LIDL", cats["groceries"])  # Wise merchant column
    rule(wise_group, wanda, "issued by", cats["dining"])  # only in the description
    rows = stage(wise_group, wanda, "wise_2026_09.csv")
    lidl = next(r for r in rows.values() if r.merchant == "Lidl")
    # Both match; "issued by" is longer than "LIDL", so it wins: description counts too.
    assert review.suggest(lidl).category == cats["dining"]


def test_rule_of_another_group_does_not_match(pair, cats):
    group, alice, _ = pair
    other = Group.objects.create(name="Trip", currency="EUR")
    zed = Member.objects.create(group=other, display_name="Zed")
    rule(other, zed, "Esselunga", cats["groceries"])
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    assert review.suggest(row).basis == "default"


def test_invalid_rule_split_falls_back_to_category_split(pair, cats):
    group, alice, bea = pair
    r = rule(
        group,
        alice,
        "Esselunga",
        cats["groceries"],
        "percentage",
        {"basis_points": {alice.id: 5000, bea.id: 5000}},
    )
    Member.objects.create(group=group, display_name="Cy")
    # Bypass validation: params now name a member set that no longer covers the group exactly.
    ShopRule.objects.filter(pk=r.pk).update(params={"basis_points": {str(alice.id): 9000}})
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    hint = review.suggest(row)
    assert hint.category == cats["groceries"]
    assert (hint.preset, hint.params) == ("equal", {})
    assert review.resolve_row(row, alice, "shared").expense.split_type == "equal"


def test_shared_split_for_category_uses_default_and_never_personal(pair, cats):
    group, alice, bea = pair
    assert review.shared_split_for(group, cats["dining"]) == ("equal", {})
    CategoryDefault.objects.create(group=group, category=cats["general"], split_type="personal")
    assert review.shared_split_for(group, cats["general"]) == ("equal", {})
    bp = {"basis_points": {str(alice.id): 7000, str(bea.id): 3000}}
    CategoryDefault.objects.create(
        group=group, category=cats["dining"], split_type="percentage", split_params=bp
    )
    assert review.shared_split_for(group, cats["dining"]) == ("percentage", bp)


def test_shop_rule_with_bad_params_is_refused(pair, cats):
    group, alice, _ = pair
    with pytest.raises(LedgerError) as exc:
        rule(group, alice, "Esselunga", cats["groceries"], "percentage", {"basis_points": {}})
    assert exc.value.code == "empty_members"
    assert not ShopRule.objects.exists()


def test_parent_category_is_refused(pair, cats):
    group, alice, _ = pair
    with pytest.raises(LedgerError) as exc:
        rule(group, alice, "Esselunga", cats["groceries"].parent)
    assert exc.value.code == "invalid_category"
    assert rule(group, alice, "Esselunga", cats["groceries"]).pk


def test_shop_rule_saved_and_soft_deleted(pair, cats):
    group, alice, _ = pair
    r = rule(group, alice, "Esselunga", cats["groceries"])
    shop_rules.delete_rule(r)
    assert not ShopRule.objects.filter(pk=r.pk).exists()
    assert ShopRule.all_objects.filter(pk=r.pk, deleted_at__isnull=False).exists()
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    assert review.suggest(row).basis == "default"
    again = rule(group, alice, "Esselunga", cats["dining"])
    assert again.pk != r.pk


def test_rule_use_sets_last_used_at(pair, cats):
    group, alice, _ = pair
    r = rule(group, alice, "Esselunga", cats["groceries"])
    assert r.last_used_at is None
    review.resolve_row(stage(group, alice, "revolut_review.csv")["Esselunga"], alice, "shared")
    r.refresh_from_db()
    assert r.last_used_at is not None


# ---- history ----


def test_last_choice_for_same_merchant_is_suggested_when_no_rule(pair, cats):
    group, alice, _ = pair
    rows = stage(group, alice, "revolut_review.csv")
    review.resolve_row(rows["Farmacia Centrale"], alice, "personal", category=cats["dining"])
    # Same shop on a later statement line (another balance, so another row id).
    data = (FIXTURES / "revolut_review.csv").read_bytes().replace(b"942.80", b"900.00")
    batch = staging.stage_bank_file(group, alice, SimpleUploadedFile("again.csv", data)).batch
    again = batch.bank_rows.get(description="Farmacia Centrale")
    hint = review.suggest(again)
    assert (hint.category, hint.decision, hint.basis) == (cats["dining"], "personal", "history")
    assert hint.preset == "equal"  # the Shared button's split is never personal


def test_undone_or_skipped_rows_are_not_history(pair, cats):
    group, alice, _ = pair
    rows = stage(group, alice, "revolut_review.csv")
    review.resolve_row(rows["Esselunga"], alice, "shared", category=cats["groceries"])
    review.undo_row(rows["Esselunga"], alice)
    review.resolve_row(rows["Transfer to Bea"], alice, "skip")
    data = (
        (FIXTURES / "revolut_review.csv")
        .read_bytes()
        .replace(b"954.80", b"1.00")
        .replace(b"842.80", b"2.00")
    )
    batch = staging.stage_bank_file(group, alice, SimpleUploadedFile("again.csv", data)).batch
    for desc in ("Esselunga", "Transfer to Bea"):
        assert review.suggest(batch.bank_rows.get(description=desc)).basis == "default"


def test_history_suggestion_after_expense_split_edited_is_consistent(pair, cats):
    group, alice, bea = pair
    rows = stage(group, alice, "revolut_review.csv")
    expense = review.resolve_row(
        rows["Esselunga"], alice, "shared", category=cats["groceries"], preset="equal"
    ).expense
    update_expense(
        expense,
        description=expense.description,
        amount_cents=4520,
        currency="EUR",
        date=expense.date,
        category=cats["groceries"],
        payers={alice.id: 4520},
        splits={alice.id: 2712, bea.id: 1808},
        split_type="percentage",
    )
    data = (FIXTURES / "revolut_review.csv").read_bytes().replace(b"954.80", b"5.00")
    batch = staging.stage_bank_file(group, alice, SimpleUploadedFile("again.csv", data)).batch
    row = batch.bank_rows.get(description="Esselunga")
    hint = review.suggest(row)
    assert hint.basis == "history"
    assert (hint.preset, hint.params) == ("equal", {})
    done = review.resolve_row(
        row, alice, "shared", category=hint.category, preset=hint.preset, params=hint.params
    )
    assert done.expense.split_type == "equal"
    assert splits_of(done.expense) == {alice.id: 2260, bea.id: 2260}


# ---- decisions ----


def test_personal_creates_personal_expense_with_no_balance_effect(pair, cats):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Farmacia Centrale"]
    expense = review.resolve_row(row, alice, "personal").expense
    assert expense.split_type == "personal"
    assert splits_of(expense) == {alice.id: 1200}
    assert set(net_balances(group).values()) == {0}
    row.refresh_from_db()
    assert row.status == "personal"


def test_skip_creates_nothing(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Transfer to Bea"]
    done = review.resolve_row(row, alice, "skip")
    assert done.expense is None
    assert not Expense.all_objects.exists()
    row.refresh_from_db()
    assert row.status == "skipped"


def test_resolved_row_cannot_be_resolved_twice(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    review.resolve_row(row, alice, "shared")
    for decision in ("shared", "personal", "skip"):
        with pytest.raises(LedgerError) as exc:
            review.resolve_row(row, alice, decision)
        assert exc.value.code == "row_already_resolved"
    assert Expense.all_objects.count() == 1


def test_shared_with_personal_preset_is_refused(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    with pytest.raises(LedgerError) as exc:
        review.resolve_row(row, alice, "shared", preset="personal")
    assert exc.value.code == "shared_needs_split"
    assert review.resolve_row(row, alice, "shared", preset="equal").expense


def test_remember_on_skip_is_refused(pair, cats):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Transfer to Bea"]
    with pytest.raises(LedgerError) as exc:
        review.resolve_row(row, alice, "skip", remember=True)
    assert exc.value.code == "remember_needs_category"
    row.refresh_from_db()
    assert row.status == "pending"
    assert review.resolve_row(row, alice, "personal", remember=True).rule.preset == "personal"


def test_remember_creates_rule_that_prefills_next_upload(pair, cats):
    group, alice, bea = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    done = review.resolve_row(
        row, alice, "shared", category=cats["groceries"], preset="equal", remember=True
    )
    assert (done.rule.match_text, done.rule.category, done.rule.preset) == (
        "Esselunga",
        cats["groceries"],
        "equal",
    )
    nxt = stage(group, alice, "revolut_review_next.csv")["ESSELUNGA MILANO"]
    hint = review.suggest(nxt)
    assert (hint.category, hint.preset, hint.basis) == (cats["groceries"], "equal", "rule")
    assert splits_of(review.resolve_row(nxt, alice, "shared").expense) == {
        alice.id: 1505,
        bea.id: 1505,
    }


def test_remember_updates_existing_rule_instead_of_duplicating(pair, cats):
    group, alice, _ = pair
    first = rule(group, alice, "ESSELUNGA", cats["general"])
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    done = review.resolve_row(row, alice, "shared", category=cats["groceries"], remember=True)
    assert done.rule.pk == first.pk
    assert ShopRule.objects.count() == 1
    first.refresh_from_db()
    assert first.category == cats["groceries"]


def test_undo_soft_deletes_expense_and_returns_row_to_pending(pair):
    group, alice, bea = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    expense = review.resolve_row(row, alice, "shared").expense
    assert net_balances(group)[bea.id] == -2260
    undone = review.undo_row(row, alice)
    assert undone.status == "pending"
    assert not Expense.objects.filter(pk=expense.pk).exists()
    assert Expense.all_objects.get(pk=expense.pk).deleted_at is not None
    assert set(net_balances(group).values()) == {0}


def test_undo_of_pending_row_is_refused(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    with pytest.raises(LedgerError) as exc:
        review.undo_row(row, alice)
    assert exc.value.code == "row_not_resolved"
    review.resolve_row(row, alice, "skip")
    assert review.undo_row(row, alice).status == "pending"


def test_redecide_after_undo_revives_same_expense_with_new_split(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    first = review.resolve_row(row, alice, "shared").expense
    review.undo_row(row, alice)
    again = review.resolve_row(row, alice, "personal").expense
    assert again.pk == first.pk
    again.refresh_from_db()
    assert again.deleted_at is None
    assert again.split_type == "personal"
    assert Expense.all_objects.filter(external_id=row.external_id).count() == 1


def _usd_rate():
    ExchangeRate.objects.create(
        date=datetime.date(2026, 9, 11), currency="USD", rate_to_eur=Decimal("1.10")
    )


def test_foreign_currency_row_converts_at_row_date(pair):
    group, alice, _ = pair
    _usd_rate()
    row = stage(group, alice, "revolut_2026_09.csv")["Starbucks NYC"]
    expense = review.resolve_row(row, alice, "shared").expense
    assert (expense.original_amount_cents, expense.original_currency) == (875, "USD")
    assert expense.currency == "EUR"
    assert expense.rate_used == Decimal("0.90909091")
    assert expense.amount_cents == 795


def test_foreign_row_without_rate_stays_pending(pair):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_2026_09.csv")["Starbucks NYC"]
    with pytest.raises(LedgerError) as exc:
        review.resolve_row(row, alice, "shared")
    assert exc.value.code == "no_rate"
    row.refresh_from_db()
    assert row.status == "pending"
    assert not Expense.all_objects.exists()


def test_foreign_row_revived_after_undo_reconverts(pair):
    group, alice, _ = pair
    _usd_rate()
    row = stage(group, alice, "revolut_2026_09.csv")["Starbucks NYC"]
    review.resolve_row(row, alice, "shared")
    review.undo_row(row, alice)
    expense = review.resolve_row(row, alice, "personal").expense
    expense.refresh_from_db()
    assert (expense.amount_cents, expense.original_amount_cents) == (795, 875)
    assert (expense.original_currency, expense.rate_used) == ("USD", Decimal("0.90909091"))
    assert {s.member_id: s.owed_cents for s in expense.splits.all()} == {alice.id: 795}


def test_row_already_shared_in_another_group_is_refused_and_stays_pending(pair):
    group, alice, _ = pair
    other = Group.objects.create(name="Trip", currency="EUR")
    zed = Member.objects.create(group=other, display_name="Zed")
    review.resolve_row(stage(other, zed, "revolut_review.csv")["Esselunga"], zed, "personal")
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    with pytest.raises(LedgerError) as exc:
        review.resolve_row(row, alice, "shared")
    assert exc.value.code == "duplicate_external_id"
    row.refresh_from_db()
    assert row.status == "pending"
    assert review.resolve_row(row, alice, "skip").row.status == "skipped"


def test_other_members_row_cannot_be_resolved(pair):
    group, alice, bea = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]
    with pytest.raises(LedgerError) as exc:
        review.resolve_row(row, bea, "shared")
    assert exc.value.code == "not_found"
    with pytest.raises(LedgerError):
        review.undo_row(row, bea)
    assert review.resolve_row(row, alice, "shared").expense


def test_resolve_writes_row_and_expense_atomically(pair, cats, monkeypatch):
    group, alice, _ = pair
    row = stage(group, alice, "revolut_review.csv")["Esselunga"]

    def boom(*a, **k):
        raise LedgerError("boom", "forced")

    monkeypatch.setattr(shop_rules, "save_rule", boom)
    with pytest.raises(LedgerError):
        review.resolve_row(row, alice, "shared", remember=True)
    row.refresh_from_db()
    assert row.status == "pending"
    assert row.expense_id is None
    assert not Expense.all_objects.exists()


def test_suggested_category_keeps_suggested_split_other_category_takes_its_own(pair, cats):
    # Same rule as the page's rowChoice: the server never re-derives a split the row did not show.
    group, alice, bea = pair
    rule(group, alice, "Esselunga", cats["groceries"])
    CategoryDefault.objects.create(
        group=group, category=cats["groceries"], split_type="full_for_other"
    )
    rows = stage(group, alice, "revolut_review.csv")
    same = review.resolve_row(rows["Esselunga"], alice, "shared", category=cats["groceries"])
    assert same.expense.split_type == "equal"
    CategoryDefault.objects.create(
        group=group,
        category=cats["dining"],
        split_type="percentage",
        split_params={"basis_points": {str(alice.id): 7000, str(bea.id): 3000}},
    )
    other = review.resolve_row(rows["Farmacia Centrale"], alice, "shared", category=cats["dining"])
    assert other.expense.split_type == "percentage"
    assert splits_of(other.expense) == {alice.id: 840, bea.id: 360}
