import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models

# The stub table is empty everywhere (nothing created rules before ticket 007), so the
# throwaway defaults below never reach a row; they are dropped (preserve_default=False).


class Migration(migrations.Migration):
    dependencies = [("ledger", "0005_group_link_member_profile_unique")]

    operations = [
        migrations.AddField(
            model_name="recurringrule",
            name="description",
            field=models.CharField(max_length=300, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="amount_cents",
            field=models.IntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="payer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="ledger.member",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="recurringrule",
            name="payer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="ledger.member",
            ),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="split_type",
            field=models.CharField(
                max_length=20,
                default="equal",
                choices=[
                    ("equal", "Equal"),
                    ("personal", "Personal"),
                    ("full_for_other", "Full For Other"),
                    ("percentage", "Percentage"),
                    ("exact", "Exact"),
                    ("shares", "Shares"),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="split_params",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="ledger.category",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="recurringrule",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="ledger.category",
            ),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="frequency",
            field=models.CharField(
                max_length=10,
                default="monthly",
                choices=[("monthly", "Monthly"), ("yearly", "Yearly")],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="day_of_month",
            field=models.SmallIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="month",
            field=models.SmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="start_date",
            field=models.DateField(default="2000-01-01"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="next_date",
            field=models.DateField(default="2000-01-01"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="paused",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default="2000-01-01T00:00:00Z"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default="2000-01-01T00:00:00Z"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="recurringrule",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="recurringrule", options={"base_manager_name": "all_objects"}
        ),
        migrations.AlterModelManagers(
            name="recurringrule",
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="recurringrule",
            constraint=models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0), name="rule_amount_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="recurringrule",
            constraint=models.CheckConstraint(
                condition=models.Q(day_of_month__gte=1, day_of_month__lte=31),
                name="rule_day_in_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="recurringrule",
            constraint=models.CheckConstraint(
                condition=models.Q(frequency="monthly", month__isnull=True)
                | models.Q(frequency="yearly", month__gte=1, month__lte=12),
                name="rule_month_matches_frequency",
            ),
        ),
    ]
