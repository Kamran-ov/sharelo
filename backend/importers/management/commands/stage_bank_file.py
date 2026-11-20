from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from importers.banks import staging
from ledger.errors import LedgerError
from ledger.models import Group, Member


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    return f"{sign}{whole}.{rest:02d}"


class Command(BaseCommand):
    help = (
        "Stage a Revolut or Wise CSV export as pending bank rows. "
        "Use --dry-run first on any new export: it writes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--group", type=int, required=True, help="our group id")
        parser.add_argument("--member", type=int, required=True, help="uploader's member id")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        group = Group.objects.filter(pk=options["group"]).first()
        if group is None:
            raise CommandError(f"--group {options['group']}: no such group")
        member = Member.objects.filter(pk=options["member"]).first()
        if member is None:
            raise CommandError(f"--member {options['member']}: no such member")
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"{path}: no such file")
        out = self.stdout.write
        try:
            with path.open("rb") as fh:
                upload = File(fh, name=path.name)
                if options["dry_run"]:
                    r = staging.dry_run(group, member, upload)
                else:
                    result = staging.stage_bank_file(group, member, upload)
        except LedgerError as exc:
            raise CommandError(str(exc)) from exc

        if options["dry_run"]:
            out(
                f"DRY RUN {r.source}  seen {r.rows_seen}  ignored {r.ignored}  "
                f"would create {r.would_create}  would skip {r.would_skip}"
            )
            for currency in sorted(r.cents_by_currency):
                out(
                    f"  {currency}  total {_money(r.cents_by_currency[currency])}"
                    f"  rows {r.rows_by_currency[currency]}"
                )
            kinds = ", ".join(f"{k} {n}" for k, n in sorted(r.kind_counts.items()))
            out(f"  types: {kinds or '-'}")
            out("Nothing written.")
            return
        b = result.batch
        out(
            f"{b.source} batch {b.pk}  seen {b.rows_seen}  created {b.rows_created}  "
            f"skipped {b.rows_skipped}  ignored {result.ignored}"
        )
