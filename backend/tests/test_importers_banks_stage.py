import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction

from importers.banks import staging
from importers.models import PendingBankRow
from ledger.errors import LedgerError
from ledger.models import Group, ImportBatch, Member

FIXTURES = Path(__file__).parent / "fixtures" / "banks"

pytestmark = pytest.mark.django_db


def upload(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, (FIXTURES / name).read_bytes(), content_type="text/csv")


def stage(group, member, name):
    return staging.stage_bank_file(group, member, upload(name))


def test_same_file_twice_second_batch_creates_nothing_and_skips_every_row(group, members):
    ann = members[0]
    first = stage(group, ann, "revolut_2026_09.csv").batch
    assert (first.rows_seen, first.rows_created, first.rows_skipped) == (7, 7, 0)

    second = stage(group, ann, "revolut_2026_09.csv").batch
    assert (second.rows_seen, second.rows_created, second.rows_skipped) == (7, 0, 7)
    assert PendingBankRow.objects.count() == 7
    assert not PendingBankRow.objects.filter(import_batch=second).exists()


def test_overlapping_months_skip_overlap_and_create_new_rows(group, members):
    ann = members[0]
    stage(group, ann, "revolut_2026_09.csv")
    oct_ = stage(group, ann, "revolut_2026_10.csv").batch
    assert (oct_.rows_seen, oct_.rows_created, oct_.rows_skipped) == (7, 4, 3)
    assert PendingBankRow.objects.count() == 11
    assert sorted(oct_.bank_rows.values_list("description", flat=True)) == [
        "Coop",
        "Netflix",
        "Pizzeria Da Gino",
        "To John Doe",
    ]

    stage(group, ann, "wise_2026_09.csv")
    wise_oct = stage(group, ann, "wise_2026_10.csv").batch
    assert (wise_oct.rows_seen, wise_oct.rows_created, wise_oct.rows_skipped) == (4, 2, 2)


def test_same_file_in_another_group_is_staged_there(group, members):
    other = Group.objects.create(name="Trip", currency="EUR")
    zed = Member.objects.create(group=other, display_name="Zed")
    stage(group, members[0], "wise_2026_09.csv")
    there = stage(other, zed, "wise_2026_09.csv").batch
    assert there.rows_created == 4
    assert PendingBankRow.objects.filter(group=other).count() == 4


def test_batch_counts_seen_created_skipped_and_finishes(group, members):
    result = stage(group, members[1], "wise_2026_09.csv")
    b = ImportBatch.objects.get(pk=result.batch.pk)
    assert b.source == "wise"
    assert b.label == "wise_2026_09.csv"
    assert b.group == group
    assert b.finished_at is not None
    assert b.rows_seen == b.rows_created + b.rows_skipped == 4
    assert result.ignored == 1
    row = b.bank_rows.get(external_id="wise:CARD-1001")
    assert (row.amount_cents, row.currency, row.merchant, row.status) == (
        1820,
        "EUR",
        "Lidl",
        "pending",
    )
    assert row.uploaded_by == members[1]
    assert row.raw["Running Balance"] == "481.80"


def test_dry_run_writes_nothing_and_reports_what_staging_would(group, members):
    ann = members[0]
    dry = staging.dry_run(group, ann, upload("revolut_2026_09.csv"))
    assert not ImportBatch.objects.exists()
    assert not PendingBankRow.objects.exists()
    assert dry.source == "revolut"
    assert (dry.rows_seen, dry.ignored, dry.would_create, dry.would_skip) == (7, 3, 7, 0)
    # 2340 + 1280 + 120 + 120 + 199 + 10000 EUR; 875 USD
    assert dry.cents_by_currency == {"EUR": 14059, "USD": 875}
    assert dry.kind_counts == {"CARD_PAYMENT": 5, "FEE": 1, "EXCHANGE": 1}

    real = stage(group, ann, "revolut_2026_09.csv")
    b = real.batch
    assert (dry.rows_seen, dry.would_create, dry.would_skip, dry.ignored) == (
        b.rows_seen,
        b.rows_created,
        b.rows_skipped,
        real.ignored,
    )
    staged = {}
    for currency, cents in b.bank_rows.values_list("currency", "amount_cents"):
        staged[currency] = staged.get(currency, 0) + cents
    assert staged == dry.cents_by_currency

    # after a stage: the overlap file's dry run predicts the real stage's skip count
    dry_oct = staging.dry_run(group, ann, upload("revolut_2026_10.csv"))
    oct_ = stage(group, ann, "revolut_2026_10.csv").batch
    assert (dry_oct.would_create, dry_oct.would_skip) == (oct_.rows_created, oct_.rows_skipped)
    assert (dry_oct.would_create, dry_oct.would_skip) == (4, 3)

    # an id repeated inside one file: both paths create it once and skip the repeat
    dry_rep = staging.dry_run(group, ann, upload("revolut_repeated_line.csv"))
    rep = stage(group, ann, "revolut_repeated_line.csv").batch
    assert (dry_rep.rows_seen, dry_rep.would_create, dry_rep.would_skip) == (3, 2, 1)
    assert (rep.rows_seen, rep.rows_created, rep.rows_skipped) == (3, 2, 1)


def test_bad_row_stages_nothing_and_creates_no_batch(group, members):
    bad = SimpleUploadedFile(
        "bad.csv",
        b"TransferWise ID,Date,Amount,Currency,Description,Merchant\n"
        b"CARD-1,01-09-2026,-1.00,EUR,ok,Shop\n"
        b"CARD-2,01-09-2026,-1.005,EUR,bad,Shop\n",
    )
    with pytest.raises(LedgerError) as exc:
        staging.stage_bank_file(group, members[0], bad)
    assert exc.value.code == "bad_bank_row"
    assert not ImportBatch.objects.exists()
    assert not PendingBankRow.objects.exists()


def test_member_of_another_group_is_refused(group, members):
    other = Group.objects.create(name="Trip", currency="EUR")
    zed = Member.objects.create(group=other, display_name="Zed")
    with pytest.raises(LedgerError) as exc:
        stage(group, zed, "wise_2026_09.csv")
    assert exc.value.code == "member_not_in_group"
    assert not PendingBankRow.objects.exists()


def test_oversized_file_is_refused_before_reading(group, members):
    class Huge:
        name = "huge.csv"
        size = staging.MAX_BYTES + 1

        def read(self):
            raise AssertionError("read before the size check")

    with pytest.raises(LedgerError) as exc:
        staging.stage_bank_file(group, members[0], Huge())
    assert exc.value.code == "file_too_large"


def test_amount_check_constraint_refuses_zero(group, members):
    batch = ImportBatch.objects.create(group=group, source="wise")
    fields = dict(
        group=group,
        uploaded_by=members[0],
        source="wise",
        import_batch=batch,
        date="2026-09-01",
        currency="EUR",
        description="x",
        raw={},
    )
    PendingBankRow.objects.create(amount_cents=1, external_id="wise:ok", **fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        PendingBankRow.objects.create(amount_cents=0, external_id="wise:zero", **fields)


def test_stage_bank_file_command_dry_run_prints_totals_and_exits_0(group, members):
    out = io.StringIO()
    call_command(
        "stage_bank_file",
        str(FIXTURES / "revolut_2026_09.csv"),
        "--group",
        str(group.pk),
        "--member",
        str(members[0].pk),
        "--dry-run",
        stdout=out,
    )
    text = out.getvalue()
    assert "DRY RUN revolut  seen 7  ignored 3  would create 7  would skip 0" in text
    assert "EUR  total 140.59  rows 6" in text
    assert "USD  total 8.75  rows 1" in text
    assert "EXCHANGE 1" in text
    assert "Nothing written." in text
    assert not ImportBatch.objects.exists()

    out = io.StringIO()
    call_command(
        "stage_bank_file",
        str(FIXTURES / "revolut_2026_09.csv"),
        "--group",
        str(group.pk),
        "--member",
        str(members[0].pk),
        stdout=out,
    )
    assert "seen 7  created 7  skipped 0  ignored 3" in out.getvalue()
    assert PendingBankRow.objects.count() == 7


def test_stage_bank_file_command_unknown_format_exits_1(group, members):
    with pytest.raises(CommandError) as exc:
        call_command(
            "stage_bank_file",
            str(FIXTURES / "unknown.csv"),
            "--group",
            str(group.pk),
            "--member",
            str(members[0].pk),
            "--dry-run",
        )
    assert "unknown_bank_format" in str(exc.value)
    assert "Completed Date" in str(exc.value)
