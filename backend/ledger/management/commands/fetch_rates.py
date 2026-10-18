import datetime

from django.core.management.base import BaseCommand, CommandError

from ledger.services.rates import fetch_ecb_rates


class Command(BaseCommand):
    help = "Download ECB reference rates (latest day, or everything since --since)."

    def add_arguments(self, parser):
        parser.add_argument("--since", help="YYYY-MM-DD")

    def handle(self, *args, **options):
        since = None
        if options["since"]:
            try:
                since = datetime.date.fromisoformat(options["since"])
            except ValueError as exc:
                raise CommandError(f"invalid --since {options['since']!r}") from exc
        self.stdout.write(f"{fetch_ecb_rates(since)} rates written")
