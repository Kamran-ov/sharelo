from django.db import models
from django.db.models import Q


class BankSource(models.TextChoices):
    # A subset of ledger.Source: the banks this app reads files from.
    REVOLUT = "revolut"
    WISE = "wise"


class BankRowStatus(models.TextChoices):
    PENDING = "pending"
    SHARED = "shared"
    PERSONAL = "personal"
    SKIPPED = "skipped"


class PendingBankRow(models.Model):
    """One money-out row of an uploaded bank file, waiting for the review list (021).

    Never deleted: a row nobody wants becomes `skipped`, so re-uploads keep skipping it.
    """

    group = models.ForeignKey("ledger.Group", on_delete=models.PROTECT, related_name="+")
    uploaded_by = models.ForeignKey("ledger.Member", on_delete=models.PROTECT, related_name="+")
    source = models.CharField(max_length=20, choices=BankSource.choices)
    import_batch = models.ForeignKey(
        "ledger.ImportBatch", on_delete=models.PROTECT, related_name="bank_rows"
    )
    date = models.DateField()
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=3)
    description = models.TextField()
    merchant = models.TextField(blank=True, default="")
    external_id = models.CharField(max_length=200)
    raw = models.JSONField()
    status = models.CharField(
        max_length=10, choices=BankRowStatus.choices, default=BankRowStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # The only duplicate guard: staging inserts with ON CONFLICT DO NOTHING against it.
            models.UniqueConstraint(
                fields=["source", "external_id", "group"], name="uniq_bankrow_source_extid_group"
            ),
            models.CheckConstraint(condition=Q(amount_cents__gt=0), name="bankrow_amount_positive"),
            models.CheckConstraint(
                condition=Q(status__in=BankRowStatus.values), name="bankrow_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(source__in=BankSource.values), name="bankrow_source_valid"
            ),
        ]
