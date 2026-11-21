from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from ledger.models import SplitType


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
    # The decision made on this row (021). Kept after an Undo so a re-decision revives the same
    # expense: a soft-deleted expense still holds the row's (source, external_id).
    expense = models.ForeignKey(
        "ledger.Expense", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Preset and params as decided, read together by the "last choice" suggestion: the expense
    # keeps only cents and may be edited later, so its split_type cannot pair with these params.
    split_preset = models.CharField(max_length=20, blank=True, default="")
    split_params = models.JSONField(default=dict, blank=True)

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


class LiveShopRuleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class ShopRule(models.Model):
    """Merchant text → category and split, so the review list can pre-fill a bank row (021)."""

    group = models.ForeignKey("ledger.Group", on_delete=models.PROTECT, related_name="shop_rules")
    match_text = models.CharField(max_length=200)
    category = models.ForeignKey("ledger.Category", on_delete=models.PROTECT, related_name="+")
    preset = models.CharField(max_length=20, choices=SplitType.choices)
    params = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey("ledger.Member", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = LiveShopRuleManager()
    all_objects = models.Manager()

    class Meta:
        base_manager_name = "all_objects"
        constraints = [
            # One live rule per text per group, so "remember" can create-or-update.
            models.UniqueConstraint(
                Lower("match_text"),
                "group",
                condition=Q(deleted_at__isnull=True),
                name="uniq_shoprule_group_text",
            ),
            models.CheckConstraint(condition=~Q(match_text=""), name="shoprule_text_not_empty"),
        ]
