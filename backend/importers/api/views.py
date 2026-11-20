from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from importers.api import serializers as sz
from importers.banks import staging
from importers.models import BankSource, PendingBankRow
from ledger.api.access import GroupScopedView
from ledger.errors import LedgerError
from ledger.models import ImportBatch


def _rows(batch: ImportBatch):
    return PendingBankRow.objects.filter(import_batch=batch).order_by("date", "id")


class BankImportListView(GroupScopedView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": sz.BankUploadSerializer},
        responses={201: sz.BankUploadResultSerializer},
    )
    def post(self, request, group_id):
        upload = request.FILES.get("file")
        if upload is None:
            raise LedgerError("invalid_request", "send the CSV as the multipart field 'file'")
        result = staging.stage_bank_file(self.group, self.me, upload)
        body = {"batch": result.batch, "rows": _rows(result.batch), "ignored": result.ignored}
        return Response(sz.BankUploadResultSerializer(body).data, status=201)


class BankImportDetailView(GroupScopedView):
    @extend_schema(responses=sz.BankImportSerializer)
    def get(self, request, group_id, batch_id):
        batch = ImportBatch.objects.filter(
            pk=batch_id, group=self.group, source__in=BankSource.values
        ).first()
        if batch is None:
            raise LedgerError("not_found")
        rows = list(_rows(batch))
        # A statement is personal: only its uploader reads it. A batch without rows carries no
        # bank data, so its counts are visible to any member.
        if rows and rows[0].uploaded_by_id != self.me.id:
            raise LedgerError("not_found")
        return Response(sz.BankImportSerializer({"batch": batch, "rows": rows}).data)
