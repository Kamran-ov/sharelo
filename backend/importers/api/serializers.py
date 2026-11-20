from rest_framework import serializers

from importers.models import PendingBankRow
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
