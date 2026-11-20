"""Stage an uploaded bank file as pending rows. The only writer of PendingBankRow."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from django.db import transaction
from django.utils import timezone

from importers.banks import revolut, wise
from importers.banks.common import REVOLUT, WISE, BankRow, detect, read_csv
from importers.models import PendingBankRow
from ledger.errors import LedgerError
from ledger.models import Group, ImportBatch, Member

MAX_BYTES = 2 * 1024 * 1024
PARSERS = {REVOLUT: revolut.parse, WISE: wise.parse}


class UploadedFile(Protocol):
    name: str
    size: int

    def read(self) -> bytes: ...


@dataclass
class Parsed:
    source: str
    rows: list[BankRow]
    ignored: int


@dataclass
class StageResult:
    batch: ImportBatch
    ignored: int


@dataclass
class DryRun:
    source: str
    rows_seen: int
    ignored: int
    would_create: int
    would_skip: int
    cents_by_currency: dict[str, int] = field(default_factory=dict)
    rows_by_currency: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)


def parse_file(file: UploadedFile) -> Parsed:
    """Read, detect, parse. Every refusal happens here, before anything is written."""
    if file.size > MAX_BYTES:
        raise LedgerError("file_too_large", f"{file.size} bytes; the limit is {MAX_BYTES}")
    header, lines = read_csv(file.read())
    source = detect(header)
    rows = PARSERS[source](lines)
    return Parsed(source, rows, ignored=len(lines) - len(rows))


def _check_member(group: Group, member: Member) -> None:
    if member.group_id != group.id:
        raise LedgerError("member_not_in_group", "the uploader must belong to the group")


def dry_run(group: Group, member: Member, file: UploadedFile) -> DryRun:
    _check_member(group, member)
    parsed = parse_file(file)
    ids = {r.external_id for r in parsed.rows}
    existing = set(
        PendingBankRow.objects.filter(
            group=group, source=parsed.source, external_id__in=ids
        ).values_list("external_id", flat=True)
    )
    # Same definition as the real path: an id repeated within the file is created once, and
    # every other occurrence counts as skipped.
    would_create = len(ids - existing)
    cents: Counter[str] = Counter()
    count: Counter[str] = Counter()
    for r in parsed.rows:
        cents[r.currency] += r.amount_cents
        count[r.currency] += 1
    return DryRun(
        source=parsed.source,
        rows_seen=len(parsed.rows),
        ignored=parsed.ignored,
        would_create=would_create,
        would_skip=len(parsed.rows) - would_create,
        cents_by_currency=dict(cents),
        rows_by_currency=dict(count),
        kind_counts=dict(Counter(r.kind or "-" for r in parsed.rows)),
    )


def stage_bank_file(group: Group, member: Member, file: UploadedFile) -> StageResult:
    _check_member(group, member)
    parsed = parse_file(file)
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            group=group, source=parsed.source, label=(file.name or "")[:200]
        )
        # No lookup first: the unique constraint is the only duplicate guard, so a concurrent
        # upload of the same file and in-file repeats are both absorbed by ON CONFLICT.
        PendingBankRow.objects.bulk_create(
            [
                PendingBankRow(
                    group=group,
                    uploaded_by=member,
                    source=parsed.source,
                    import_batch=batch,
                    date=r.date,
                    amount_cents=r.amount_cents,
                    currency=r.currency,
                    description=r.description,
                    merchant=r.merchant,
                    external_id=r.external_id,
                    raw=r.raw,
                )
                for r in parsed.rows
            ],
            ignore_conflicts=True,
        )
        created = batch.bank_rows.count()
        batch.rows_seen = len(parsed.rows)
        batch.rows_created = created
        batch.rows_skipped = batch.rows_seen - created
        batch.finished_at = timezone.now()
        batch.save()
    return StageResult(batch, parsed.ignored)
