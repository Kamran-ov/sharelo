import datetime
import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from accounts.models import Profile
from ledger.models import Category, CategoryDefault, ExchangeRate, Group
from ledger.services import groups
from sharelo.e2e import is_e2e_database

# Reference data that migrations seed; wiping it would leave the app unusable.
KEEP_TABLES = {
    "django_migrations",
    "django_content_type",
    "auth_permission",
    "ledger_category",
    "ledger_exchangerate",
}
ROME_TOKEN = "e2e-rome-token"
PASSWORD = "password1234"


def database_name() -> str:
    return connection.settings_dict["NAME"]


def wipe() -> None:
    with connection.cursor() as cur:
        # Deferred FK checks from earlier writes in this transaction would block TRUNCATE.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = sorted(t for (t,) in cur.fetchall() if t not in KEEP_TABLES)
        quoted = ", ".join(connection.ops.quote_name(t) for t in tables)
        cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")


def _profile(email: str, display_name: str) -> Profile:
    # Direct creation, not `register`: the ticket's fixture password is on the common-password list.
    user = get_user_model().objects.create_user(username=email, email=email, password=PASSWORD)
    return Profile.objects.create(user=user, display_name=display_name)


def seed() -> None:
    alice = _profile("a@example.com", "Alice")
    bea = _profile("b@example.com", "Bea")
    home = groups.create_group(alice, "Home", "EUR", as_main=True)
    groups.join_group_by_token(home.share_token, "Bea", bea, as_main=True)
    rome = groups.create_group(bea, "Rome trip", "EUR")
    Group.objects.filter(pk=rome.pk).update(share_token=ROME_TOKEN)
    # General is the category the add sheet preselects in a group with no expenses.
    CategoryDefault.objects.create(
        group=home, category=Category.objects.get(name="General"), split_type="equal"
    )
    # ledger_exchangerate survives the wipe, so these are idempotent rather than created.
    ExchangeRate.objects.filter(currency="GBP").delete()
    ExchangeRate.objects.update_or_create(
        date=datetime.date.today(), currency="USD", defaults={"rate_to_eur": Decimal("1.10")}
    )


class Command(BaseCommand):
    help = "Wipe user data and seed the fixed browser-test fixture. Only on a *_e2e database."

    def handle(self, *args, **options):
        if os.environ.get("E2E") != "1" or not settings.E2E:
            raise CommandError("e2e_reset only runs with E2E=1")
        if not is_e2e_database(database_name()):
            raise CommandError(
                f"refusing to wipe {database_name()!r}: the database name must end in '_e2e'"
            )
        with transaction.atomic():
            wipe()
            seed()
        self.stdout.write("e2e fixture ready")
