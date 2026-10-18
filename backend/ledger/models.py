import secrets

from django.db import models
from django.db.models import F, Q

from .errors import LedgerError


def new_share_token() -> str:
    return secrets.token_urlsafe(16)


class Group(models.Model):
    name = models.CharField(max_length=200)
    currency = models.CharField(max_length=3)
    share_token = models.CharField(max_length=40, unique=True, default=new_share_token)
    created_at = models.DateTimeField(auto_now_add=True)


class Member(models.Model):
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="members")
    display_name = models.CharField(max_length=100)
    # NULL profile = guest; guest shares never roll into anyone's Home analytics.
    profile = models.ForeignKey(
        "accounts.Profile", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "display_name"], name="uniq_member_group_display_name"
            ),
            models.UniqueConstraint(
                fields=["group", "profile"],
                condition=Q(profile__isnull=False),
                name="uniq_member_group_profile",
            ),
        ]


class GroupLink(models.Model):
    """`profile` feeds `sub_group` into `main_group`; `active=False` unlinks, never deletes."""

    profile = models.ForeignKey("accounts.Profile", on_delete=models.CASCADE, related_name="+")
    sub_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="+")
    main_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="+")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profile", "sub_group"], name="uniq_link_profile_sub"),
            models.CheckConstraint(
                condition=~Q(sub_group=F("main_group")), name="link_sub_not_main"
            ),
        ]


class Category(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            # nulls_distinct=False: two root categories with the same name are rejected too.
            models.UniqueConstraint(
                fields=["parent", "name"], name="uniq_category_parent_name", nulls_distinct=False
            )
        ]

    def check_depth(self) -> None:
        """Max depth 2. A CHECK constraint cannot span rows, so the guard lives here.

        Bounded on purpose: a parent must itself be a root, which also rejects self-parents
        and cycles without walking the tree.
        """
        if self.parent_id is None:
            return
        if self.pk is not None and self.parent_id == self.pk:
            raise LedgerError("category_depth", "a category cannot be its own parent")
        if self.parent.parent_id is not None:
            raise LedgerError("category_depth", "categories are two levels deep at most")
        if self.pk is not None and self.children.exists():
            raise LedgerError("category_depth", "a category with children must stay a root")

    def clean(self) -> None:
        self.check_depth()

    def save(self, *args, **kwargs) -> None:
        self.check_depth()
        super().save(*args, **kwargs)


class ImportBatch(models.Model):
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="import_batches")
    source = models.CharField(max_length=20)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    label = models.CharField(max_length=200, blank=True)
    rows_seen = models.IntegerField(default=0)
    rows_created = models.IntegerField(default=0)
    rows_skipped = models.IntegerField(default=0)


class SplitType(models.TextChoices):
    EQUAL = "equal"
    PERSONAL = "personal"
    FULL_FOR_OTHER = "full_for_other"
    PERCENTAGE = "percentage"
    EXACT = "exact"
    SHARES = "shares"


class Source(models.TextChoices):
    MANUAL = "manual"
    SPLITWISE = "splitwise"
    REVOLUT = "revolut"
    WISE = "wise"
    RECURRING = "recurring"


class Frequency(models.TextChoices):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ActiveRuleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class RecurringRule(models.Model):
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="recurring_rules")
    description = models.CharField(max_length=300)
    amount_cents = models.IntegerField()
    payer = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="+")
    split_type = models.CharField(max_length=20, choices=SplitType.choices)
    # Same shape as CategoryDefault.split_params.
    split_params = models.JSONField(default=dict, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="+")
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    day_of_month = models.SmallIntegerField()
    month = models.SmallIntegerField(null=True, blank=True)
    start_date = models.DateField()
    next_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    paused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveRuleManager()
    all_objects = models.Manager()

    class Meta:
        # Expense.recurring_rule must still resolve after the rule is soft-deleted.
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(condition=Q(amount_cents__gt=0), name="rule_amount_positive"),
            models.CheckConstraint(
                condition=Q(day_of_month__gte=1, day_of_month__lte=31), name="rule_day_in_range"
            ),
            models.CheckConstraint(
                condition=(Q(frequency="monthly", month__isnull=True))
                | Q(frequency="yearly", month__gte=1, month__lte=12),
                name="rule_month_matches_frequency",
            ),
        ]


class CategoryDefault(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="category_defaults")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="+")
    split_type = models.CharField(max_length=20, choices=SplitType.choices, default=SplitType.EQUAL)
    # JSON, so object keys are strings; split_for_preset normalises them back to int.
    split_params = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "category"], name="uniq_category_default")
        ]


class ActiveExpenseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Expense(models.Model):
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="expenses")
    description = models.CharField(max_length=300)
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=3)
    original_amount_cents = models.IntegerField()
    original_currency = models.CharField(max_length=3)
    rate_used = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    date = models.DateField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="expenses")
    split_type = models.CharField(max_length=20, choices=SplitType.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    external_id = models.CharField(max_length=200, null=True, blank=True)
    import_batch = models.ForeignKey(
        ImportBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )
    recurring_rule = models.ForeignKey(
        RecurringRule, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveExpenseManager()
    all_objects = models.Manager()

    class Meta:
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(condition=Q(amount_cents__gt=0), name="expense_amount_positive"),
            # Not filtered by deleted_at: a soft-deleted row still blocks re-import of its id.
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=Q(external_id__isnull=False),
                name="uniq_expense_source_external_id",
            ),
        ]


class ExpensePayer(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="payers")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="+")
    paid_cents = models.IntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "member"], name="uniq_payer_expense_member"),
            models.CheckConstraint(condition=Q(paid_cents__gte=0), name="payer_paid_nonnegative"),
        ]


class ExpenseSplit(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="splits")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="+")
    owed_cents = models.IntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "member"], name="uniq_split_expense_member"),
            models.CheckConstraint(condition=Q(owed_cents__gte=0), name="split_owed_nonnegative"),
        ]


class ActiveSettlementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Settlement(models.Model):
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="settlements")
    from_member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="settlements_out"
    )
    to_member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="settlements_in")
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=3)
    date = models.DateField()
    notes = models.TextField(blank=True)
    twin = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    external_id = models.CharField(max_length=200, null=True, blank=True)
    import_batch = models.ForeignKey(
        ImportBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="settlements"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveSettlementManager()
    all_objects = models.Manager()

    class Meta:
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_cents__gt=0), name="settlement_amount_positive"
            ),
            models.CheckConstraint(
                condition=~Q(from_member=F("to_member")), name="settlement_distinct_members"
            ),
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=Q(external_id__isnull=False),
                name="uniq_settlement_source_external_id",
            ),
        ]


class ExchangeRate(models.Model):
    """Units of `currency` per 1 EUR, as the ECB publishes them. EUR itself is never stored."""

    date = models.DateField()
    currency = models.CharField(max_length=3)
    rate_to_eur = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["date", "currency"], name="uniq_rate_date_currency"),
            models.CheckConstraint(condition=Q(rate_to_eur__gt=0), name="exchange_rate_positive"),
        ]


class JobRun(models.Model):
    """When a scheduled job last ran; one row per job name."""

    name = models.CharField(max_length=50, unique=True)
    last_run_at = models.DateTimeField()
