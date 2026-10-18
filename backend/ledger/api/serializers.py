from rest_framework import serializers

from ledger.models import (
    Category,
    Expense,
    ExpensePayer,
    ExpenseSplit,
    Frequency,
    RecurringRule,
    Settlement,
    SplitType,
)


class StrictInt(serializers.IntegerField):
    """JSON integers only: DRF's IntegerField would accept 50.0 and "50" for money."""

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class IdMapField(serializers.DictField):
    """{"<member id>": int} → {member_id: int}."""

    child = StrictInt()

    def to_internal_value(self, data):
        out = super().to_internal_value(data)
        try:
            return {int(k): v for k, v in out.items()}
        except ValueError as exc:
            raise serializers.ValidationError("keys must be member ids") from exc


# ---- input ----


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    as_main = serializers.BooleanField(required=False)


class LinkSerializer(serializers.Serializer):
    active = serializers.BooleanField()


class JoinSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=100)


class CategoryDefaultSerializer(serializers.Serializer):
    preset = serializers.CharField()
    params = serializers.DictField(required=False)


class ExpenseQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    category = serializers.IntegerField(required=False)
    member = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False, min_value=1)


class RateQuerySerializer(serializers.Serializer):
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    date = serializers.DateField()


class ExpenseWriteSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=300)
    amount_cents = StrictInt(required=False)
    date = serializers.DateField()
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    payer_member = StrictInt(required=False)
    preset = serializers.CharField(required=False)
    params = serializers.DictField(required=False)
    original_currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    original_amount_cents = StrictInt(required=False)
    rate_used = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    payers = IdMapField(required=False)
    splits = IdMapField(required=False)
    split_type = serializers.ChoiceField(choices=SplitType.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        advanced = [k for k in ("payers", "splits", "split_type") if k in attrs]
        if advanced and len(advanced) != 3:
            raise serializers.ValidationError("payers, splits and split_type go together")
        if advanced and ("preset" in attrs or "params" in attrs or "payer_member" in attrs):
            raise serializers.ValidationError("use either preset or payers+splits")
        if self.partial:
            return attrs
        if "description" not in attrs:
            raise serializers.ValidationError("description is required")
        if advanced and "amount_cents" not in attrs:
            raise serializers.ValidationError("amount_cents is required with payers+splits")
        if not advanced and "payer_member" not in attrs:
            raise serializers.ValidationError("payer_member is required")
        return attrs


class SettlementWriteSerializer(serializers.Serializer):
    from_member = StrictInt()
    to_member = StrictInt()
    amount_cents = StrictInt()
    date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)


class MoveToHomeSerializer(serializers.Serializer):
    to_profile = StrictInt()
    amount_cents = StrictInt()
    date = serializers.DateField()


class RuleWriteSerializer(serializers.ModelSerializer):
    payer = serializers.IntegerField()
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    amount_cents = StrictInt()
    frequency = serializers.ChoiceField(choices=Frequency.choices)
    split_type = serializers.ChoiceField(choices=SplitType.choices)
    split_params = serializers.DictField(required=False)

    class Meta:
        model = RecurringRule
        fields = [
            "description",
            "amount_cents",
            "payer",
            "split_type",
            "split_params",
            "category",
            "frequency",
            "day_of_month",
            "month",
            "start_date",
            "end_date",
        ]
        extra_kwargs = {"month": {"required": False}, "end_date": {"required": False}}


# ---- output ----


class MemberSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()
    profile_id = serializers.IntegerField(allow_null=True)
    is_guest = serializers.BooleanField()


class GroupSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    currency = serializers.CharField()
    is_main = serializers.BooleanField()
    link_active = serializers.BooleanField(allow_null=True)


class GroupDetailSerializer(GroupSummarySerializer):
    share_token = serializers.CharField()
    members = MemberSerializer(many=True)
    my_member_id = serializers.IntegerField()


class JoinPreviewSerializer(serializers.Serializer):
    group_name = serializers.CharField()
    currency = serializers.CharField()
    member_names = serializers.ListField(child=serializers.CharField())


class JoinResultSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    member_id = serializers.IntegerField()


class LinkResultSerializer(serializers.Serializer):
    link_active = serializers.BooleanField()


class SubCategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class CategoryTreeSerializer(SubCategorySerializer):
    children = SubCategorySerializer(many=True)


class CategoryDefaultOutSerializer(serializers.Serializer):
    preset = serializers.CharField()
    params = serializers.DictField()


class PayerOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpensePayer
        fields = ["member", "paid_cents"]


class SplitOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseSplit
        fields = ["member", "owed_cents"]


class ExpenseOutSerializer(serializers.ModelSerializer):
    payers = PayerOutSerializer(many=True)
    splits = SplitOutSerializer(many=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "description",
            "amount_cents",
            "currency",
            "original_amount_cents",
            "original_currency",
            "rate_used",
            "date",
            "category",
            "split_type",
            "source",
            "recurring_rule",
            "notes",
            "payers",
            "splits",
            "created_at",
        ]


class ExpensePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    month_totals = serializers.DictField(child=serializers.IntegerField())
    results = ExpenseOutSerializer(many=True)


class RateOutSerializer(serializers.Serializer):
    currency = serializers.CharField()
    date = serializers.DateField()
    rate = serializers.CharField()


class TransferSerializer(serializers.Serializer):
    from_member = serializers.IntegerField()
    to_member = serializers.IntegerField()
    amount_cents = serializers.IntegerField()
    can_move_to_home = serializers.BooleanField()
    to_profile = serializers.IntegerField(allow_null=True)


class MemberBalanceSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    paid = serializers.IntegerField()
    owed_share = serializers.IntegerField()
    net = serializers.IntegerField()


class BalancesSerializer(serializers.Serializer):
    currency = serializers.CharField()
    nets = serializers.DictField(child=serializers.IntegerField())
    transfers = TransferSerializer(many=True)
    members = MemberBalanceSerializer(many=True)


class SettlementOutSerializer(serializers.ModelSerializer):
    twin_group_name = serializers.SerializerMethodField()
    is_home_side = serializers.SerializerMethodField()

    def get_twin_group_name(self, obj) -> str | None:
        return obj.twin.group.name if obj.twin_id else None

    def get_is_home_side(self, obj) -> bool:
        if not obj.twin_id:
            return False
        mains = {obj.from_member.profile, obj.to_member.profile} - {None}
        return any(p.main_group_id == obj.group_id for p in mains)

    class Meta:
        model = Settlement
        fields = [
            "id",
            "from_member",
            "to_member",
            "amount_cents",
            "currency",
            "date",
            "notes",
            "twin",
            "twin_group_name",
            "is_home_side",
            "created_at",
        ]


class RuleOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringRule
        fields = [
            "id",
            "description",
            "amount_cents",
            "payer",
            "split_type",
            "split_params",
            "category",
            "frequency",
            "day_of_month",
            "month",
            "start_date",
            "next_date",
            "end_date",
            "paused",
        ]


class RecurringStatusSerializer(serializers.Serializer):
    last_run_at = serializers.DateTimeField(allow_null=True)
