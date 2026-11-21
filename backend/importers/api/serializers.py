from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from importers.models import PendingBankRow, ShopRule
from ledger.models import ImportBatch


class BankBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "source",
            "label",
            "rows_seen",
            "rows_created",
            "rows_skipped",
            "started_at",
            "finished_at",
        ]


class PendingBankRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingBankRow
        # `raw` stays server-side: it is the whole bank line, kept for 021 and debugging.
        fields = [
            "id",
            "date",
            "amount_cents",
            "currency",
            "description",
            "merchant",
            "external_id",
            "status",
        ]


class BankImportSerializer(serializers.Serializer):
    batch = BankBatchSerializer()
    rows = PendingBankRowSerializer(many=True)


class BankUploadResultSerializer(BankImportSerializer):
    ignored = serializers.IntegerField(help_text="rows that are not money out (top-ups, declined)")


class BankUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class SuggestionSerializer(serializers.Serializer):
    category = serializers.IntegerField(source="category.id")
    category_name = serializers.CharField(source="category.name")
    decision = serializers.ChoiceField(choices=["shared", "personal"])
    preset = serializers.CharField(help_text="the split the Shared button uses; never personal")
    params = serializers.DictField()
    basis = serializers.ChoiceField(choices=["rule", "history", "default"])
    rule = serializers.IntegerField(source="rule.id", allow_null=True, default=None)


class ReviewRowSerializer(serializers.ModelSerializer):
    suggestion = serializers.SerializerMethodField()

    class Meta:
        model = PendingBankRow
        fields = [
            "id",
            "date",
            "amount_cents",
            "currency",
            "description",
            "merchant",
            "source",
            "status",
            "suggestion",
        ]

    @extend_schema_field(SuggestionSerializer)
    def get_suggestion(self, row):
        return SuggestionSerializer(self.context["suggestions"][row.id]).data


class CategorySplitSerializer(serializers.Serializer):
    preset = serializers.CharField()
    params = serializers.DictField()


class ReviewListSerializer(serializers.Serializer):
    rows = ReviewRowSerializer(many=True)
    category_splits = serializers.DictField(
        child=CategorySplitSerializer(),
        help_text="the Shared split per leaf category id, used when a row's category changes",
    )


class ResolveSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["shared", "personal", "skip"])
    category = serializers.IntegerField(required=False)
    preset = serializers.CharField(required=False)
    params = serializers.DictField(required=False)
    remember = serializers.BooleanField(required=False, default=False)


class ResolvedSerializer(serializers.Serializer):
    row = PendingBankRowSerializer()
    expense = serializers.IntegerField(allow_null=True)
    rule = serializers.IntegerField(allow_null=True)


class ShopRuleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ShopRule
        fields = [
            "id",
            "match_text",
            "category",
            "category_name",
            "preset",
            "params",
            "created_by",
            "last_used_at",
        ]


class ShopRuleWriteSerializer(serializers.Serializer):
    match_text = serializers.CharField(max_length=200)
    category = serializers.IntegerField()
    preset = serializers.CharField()
    params = serializers.DictField(required=False)
