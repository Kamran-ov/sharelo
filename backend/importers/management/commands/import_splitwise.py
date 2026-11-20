from django.core.management.base import BaseCommand, CommandError

from importers.splitwise import importer
from importers.splitwise.client import SplitwiseClient
from importers.splitwise.mapper import MappedExpense, format_cents
from ledger.errors import LedgerError
from ledger.models import Group, Member

FIRST_ROWS = 10
FIRST_SHIFTED = 20


def _parse_map(values: list[str]) -> dict[int, int]:
    out: dict[int, int] = {}
    for value in values:
        left, sep, right = value.partition("=")
        if not sep or not left.strip().isdigit() or not right.strip().isdigit():
            raise CommandError(f"--map {value!r}: expected <splitwise_user_id>=<member_id>")
        if int(left) in out:
            raise CommandError(f"--map: Splitwise user {left} given twice")
        out[int(left)] = int(right)
    return out


class Command(BaseCommand):
    help = "Import a Splitwise group's history into one of our groups. Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--group", type=int, required=True, help="Splitwise group id")
        parser.add_argument("--into", type=int, required=True, help="our group id")
        parser.add_argument(
            "--map", action="append", default=[], help="<splitwise_user_id>=<member_id>"
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        user_map = _parse_map(options["map"])
        group = Group.objects.filter(pk=options["into"]).first()
        if group is None:
            raise CommandError(f"--into {options['into']}: no such group")
        try:
            client = SplitwiseClient.from_env()
            result = importer.import_group(
                client,
                splitwise_group_id=options["group"],
                group=group,
                user_map=user_map,
                dry_run=options["dry_run"],
            )
        except LedgerError as exc:
            raise CommandError(str(exc)) from exc

        names = dict(Member.objects.filter(group=group).values_list("id", "display_name"))
        out = self.stdout.write
        if result.unmapped_users:
            out("Unmapped Splitwise users:")
            for user_id, name in result.unmapped_users:
                out(f"  {user_id}  {name}")
            out(f"Members of our group {group.pk} ({group.name}):")
            for member_id, name in sorted(names.items()):
                out(f"  {member_id}  {name}")
            raise CommandError("unmapped Splitwise users; add --map for each. Nothing written.")
        if result.errors:
            out(f"Rows that cannot be imported ({len(result.errors)}):")
            for sw_id, code, detail in result.errors:
                out(f"  {sw_id}  {code}  {detail}")
            raise CommandError("mapping errors; nothing written.")
        if result.other_groups:
            out("Already imported into another group:")
            for group_id, count in sorted(result.other_groups.items()):
                out(f"  group {group_id}: {count} rows")
            raise CommandError("rows already held by another group; nothing written.")

        self._print_summary(result)
        if result.dry_run:
            self._print_dry_run(result, names)
            out("Dry run: nothing written.")
            return
        out(f"Import batch {result.batch.pk}.")
        out("Balance check (imported rows only):")
        for line in result.balance_lines:
            out(f"  {line}")
        out(f"Balance check: {result.balance_mismatches} ✗")

    def _print_summary(self, result: importer.ImportResult) -> None:
        out = self.stdout.write
        skipped = result.skipped
        verb = "to create" if result.dry_run else "created"
        out(f"Splitwise group {result.sw_group_id} ({result.sw_group_name})")
        out(
            f"seen {result.seen} / {verb}: expenses {len(result.expenses)}, "
            f"settlements {len(result.settlements)} / skipped: existing {skipped['existing']}, "
            f"deleted {skipped['deleted']}, zero cost {skipped['zero_cost']}"
        )
        unknown = result.unknown_categories
        out(f"Unknown categories (→ Uncategorized/General): {len(unknown)}")
        for sw_id, name in unknown:
            out(f"  {sw_id}  {name}")
        adjustments = result.adjustments
        out(f"Cent adjustments: {len(adjustments)}")
        for adj in adjustments:
            out(f"  {adj.sw_id}  member {adj.member_id}  {adj.delta:+d} cent ({adj.currency})")

    def _print_dry_run(self, result: importer.ImportResult, names: dict[int, str]) -> None:
        out = self.stdout.write
        shifted = result.date_shifted
        out(f"Dates shifted by Europe/Rome: {len(shifted)}")
        for row in shifted[:FIRST_SHIFTED]:
            out(f"  {row.sw_id}  UTC {row.utc_date}  Rome {row.date}")
        out(f"First {FIRST_ROWS} rows:")
        for row in result.to_write[:FIRST_ROWS]:
            if isinstance(row, MappedExpense):
                payers = ", ".join(f"{names[m]} {format_cents(c)}" for m, c in row.payers.items())
                owers = ", ".join(f"{names[m]} {format_cents(c)}" for m, c in row.splits.items())
                out(
                    f"  {row.date}  {row.description}  {format_cents(row.amount_cents)}  "
                    f"{row.split_type}  {payers} → {owers}"
                )
            else:
                out(
                    f"  {row.date}  payment  {format_cents(row.amount_cents)}  "
                    f"{names[row.from_member_id]} → {names[row.to_member_id]}"
                )
