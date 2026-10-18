import psycopg
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

from sharelo.e2e import is_e2e_database


class Command(BaseCommand):
    help = "Create the *_e2e database if it is missing, then migrate it."

    def handle(self, *args, **options):
        if not settings.E2E:
            raise CommandError("e2e_prepare only runs with E2E=1")
        cfg = connection.settings_dict
        name = cfg["NAME"]
        if not is_e2e_database(name):
            raise CommandError(f"database {name!r} does not end in '_e2e'")
        try:
            with psycopg.connect(
                dbname="postgres",
                user=cfg["USER"],
                password=cfg["PASSWORD"],
                host=cfg["HOST"],
                port=cfg["PORT"],
                autocommit=True,
            ) as conn:
                exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
                if exists.fetchone() is None:
                    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        except psycopg.errors.InsufficientPrivilege as exc:
            raise CommandError(
                f"role {cfg['USER']!r} cannot create databases; run: createdb {name}"
            ) from exc
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write(f"{name} ready")
