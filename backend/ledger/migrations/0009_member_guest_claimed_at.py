from django.db import migrations, models
from django.db.models.functions import Now


def mark_existing_members_claimed(apps, schema_editor):
    # Every member that exists before 017 was created by a guest session or a profile; none
    # was meant to be claimable from the link, so none may turn "unclaimed" at deploy.
    Member = apps.get_model("ledger", "Member")
    Member.objects.filter(guest_claimed_at__isnull=True).update(guest_claimed_at=Now())


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0008_jobrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="guest_claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_members_claimed, migrations.RunPython.noop),
    ]
