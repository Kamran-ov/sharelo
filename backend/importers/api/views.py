from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from importers.api import serializers as sz
from importers.banks import review, shop_rules, staging
from importers.models import BankRowStatus, BankSource, PendingBankRow, ShopRule
from ledger.api.access import GroupScopedView
from ledger.api.presets import to_service_preset
from ledger.errors import LedgerError
from ledger.models import Category, ImportBatch


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


def _category(category_id: int) -> Category:
    category = Category.objects.filter(pk=category_id).first()
    if category is None:
        raise LedgerError("not_found")
    return category


class ReviewListView(GroupScopedView):
    @extend_schema(responses=sz.ReviewListSerializer)
    def get(self, request, group_id):
        rows = list(
            PendingBankRow.objects.filter(
                group=self.group, uploaded_by=self.me, status=BankRowStatus.PENDING
            ).order_by("date", "id")
        )
        for r in rows:
            r.group = self.group
        suggestions = review.suggest_many(self.group, rows)
        splits = review.shared_splits_for_group(self.group, self.me.id)
        return Response(
            {
                "rows": sz.ReviewRowSerializer(
                    rows, many=True, context={"suggestions": suggestions}
                ).data,
                "category_splits": {
                    str(cid): {"preset": p, "params": params} for cid, (p, params) in splits.items()
                },
            }
        )


class ReviewRowView(GroupScopedView):
    def row(self, rid: int) -> PendingBankRow:
        row = (
            PendingBankRow.objects.filter(pk=rid, group=self.group, uploaded_by=self.me)
            .select_related("group", "uploaded_by", "import_batch")
            .first()
        )
        if row is None:
            raise LedgerError("not_found")
        return row


class ResolveView(ReviewRowView):
    @extend_schema(request=sz.ResolveSerializer, responses=sz.ResolvedSerializer)
    def post(self, request, group_id, row_id):
        row = self.row(row_id)
        data = sz.ResolveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data
        category = _category(body["category"]) if "category" in body else None
        preset, params = body.get("preset"), body.get("params")
        if preset is not None:
            member_ids = sorted(self.group.members.values_list("id", flat=True))
            preset, params = to_service_preset(preset, params, row.uploaded_by_id, member_ids)
        done = review.resolve_row(
            row,
            self.me,
            body["decision"],
            category=category,
            preset=preset,
            params=params,
            remember=body["remember"],
        )
        return Response(
            sz.ResolvedSerializer(
                {
                    "row": done.row,
                    "expense": done.expense.id if done.expense else None,
                    "rule": done.rule.id if done.rule else None,
                }
            ).data
        )


class UndoView(ReviewRowView):
    @extend_schema(request=None, responses=sz.PendingBankRowSerializer)
    def post(self, request, group_id, row_id):
        row = review.undo_row(self.row(row_id), self.me)
        return Response(sz.PendingBankRowSerializer(row).data)


def _rule_values(view: GroupScopedView, data: dict) -> dict:
    member_ids = sorted(view.group.members.values_list("id", flat=True))
    preset, params = to_service_preset(data["preset"], data.get("params"), view.me.id, member_ids)
    return {
        "match_text": data["match_text"],
        "category": _category(data["category"]),
        "preset": preset,
        "params": params,
    }


class ShopRuleListView(GroupScopedView):
    @extend_schema(responses=sz.ShopRuleSerializer(many=True))
    def get(self, request, group_id):
        rules = ShopRule.objects.filter(group=self.group).select_related("category")
        return Response(sz.ShopRuleSerializer(rules.order_by("match_text", "id"), many=True).data)

    @extend_schema(request=sz.ShopRuleWriteSerializer, responses={201: sz.ShopRuleSerializer})
    def post(self, request, group_id):
        data = sz.ShopRuleWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = _rule_values(self, data.validated_data)
        rule = shop_rules.save_rule(self.group, self.me, **values)
        return Response(sz.ShopRuleSerializer(rule).data, status=201)


class ShopRuleDetailView(GroupScopedView):
    def rule(self, rid: int) -> ShopRule:
        rule = ShopRule.objects.filter(pk=rid, group=self.group).first()
        if rule is None:
            raise LedgerError("not_found")
        return rule

    @extend_schema(request=sz.ShopRuleWriteSerializer, responses=sz.ShopRuleSerializer)
    def patch(self, request, group_id, rule_id):
        rule = self.rule(rule_id)
        data = sz.ShopRuleWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        merged = {
            "match_text": rule.match_text,
            "category": rule.category_id,
            "preset": rule.preset,
            "params": rule.params,
            **data.validated_data,
        }
        rule = shop_rules.save_rule(self.group, self.me, rule=rule, **_rule_values(self, merged))
        return Response(sz.ShopRuleSerializer(rule).data)

    @extend_schema(responses={204: None})
    def delete(self, request, group_id, rule_id):
        shop_rules.delete_rule(self.rule(rule_id))
        return Response(status=204)
