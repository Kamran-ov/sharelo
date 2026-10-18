import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_clear_stub_profiles"),
        ("ledger", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(model_name="profile", name="email"),
        migrations.AddField(
            model_name="profile",
            name="user",
            field=models.OneToOneField(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile",
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="profile",
            name="display_name",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="profile",
            name="main_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="ledger.group",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default="2026-01-01T00:00:00Z"),
            preserve_default=False,
        ),
    ]
