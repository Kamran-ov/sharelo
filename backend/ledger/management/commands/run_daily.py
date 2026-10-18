import datetime
import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ledger.services.rates import fetch_ecb_rates
from ledger.services.recurring import generate_due

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Daily job: refresh ECB rates, then create the recurring expenses that are due."

    def add_arguments(self, parser):
        parser.add_argument("--today", help="YYYY-MM-DD; default is today's local date")

    def handle(self, *args, **options):
        if options["today"]:
            try:
                today = datetime.date.fromisoformat(options["today"])
            except ValueError as exc:
                raise CommandError(f"invalid --today {options['today']!r}") from exc
        else:
            today = timezone.localdate()

        # A network failure must not stop the expenses: rates are retried tomorrow and
        # rate lookups tolerate gaps of up to 7 days.
        try:
            rates = fetch_ecb_rates()
        except Exception:
            logger.exception("ECB rate fetch failed")
            self.stderr.write("rate fetch failed; continuing with recurring rules")
            rates = 0

        result = generate_due(today)
        self.stdout.write(
            f"rates upserted: {rates}\n"
            f"expenses created: {len(result.created)}\n"
            f"rules failed: {len(result.failed)}"
        )
        if result.failed:
            detail = ", ".join(f"rule {rid}: {code}" for rid, code in result.failed)
            raise CommandError(f"{len(result.failed)} rule(s) failed ({detail})")
