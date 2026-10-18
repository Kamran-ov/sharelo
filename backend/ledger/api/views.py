import datetime
from typing import Any

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api.csrf import CsrfProtectedAPIView
from accounts.services.access import GUEST_KEY, add_guest_member, member_for
from ledger.api import serializers as sz
from ledger.api.access import GroupScopedView, profile_of, require_profile
from ledger.api.presets import to_service_preset
from ledger.errors import LedgerError
from ledger.models import (
    Category,
    CategoryDefault,
    Expense,
    ExpensePayer,
    ExpenseSplit,
    Group,
    GroupLink,
    Member,
    RecurringRule,
    Settlement,
)
from ledger.services import balances, expenses, groups, recurring
from ledger.services.rates import resolve_foreign_amount
from ledger.services.splits import default_split_for, split_for_preset

PAGE_SIZE = 50
_ORIGINAL_KEYS = ("original_amount_cents", "original_currency", "rate_used")


def today() -> datetime.date:
    return datetime.date.today()


def _group_detail(request, group: Group, me: Member | None) -> dict:
    profile = profile_of(request)
    link = (
        GroupLink.objects.filter(profile=profile, sub_group=group).first()
        if profile is not None
        else None
    )
    members = group.members.order_by("id")
    return {
        **_group_summary(profile, group),
        "share_token": group.share_token,
        "members": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "profile_id": m.profile_id,
                "is_guest": m.profile_id is None,
            }
            for m in members
        ],
        "my_member_id": me.id if me else None,
        "link_active": link.active if link is not None else None,
    }


def _group_summary(profile, group: Group) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "currency": group.currency,
        "is_main": profile is not None and profile.main_group_id == group.id,
    }


@extend_schema(methods=["GET"], responses=sz.GroupSummarySerializer(many=True))
@extend_schema(
    methods=["POST"], request=sz.GroupCreateSerializer, responses=sz.GroupDetailSerializer
)
class GroupListView(CsrfProtectedAPIView):
    def get(self, request):
        profile = profile_of(request)
        mine = Q(pk__in=[])
        if profile is not None:
            mine |= Q(members__profile=profile)
        ids = request.session.get(GUEST_KEY) or []
        if ids:
            mine |= Q(members__id__in=ids)
        found = Group.objects.filter(mine).distinct().order_by("-id")
        return Response([_group_summary(profile, g) for g in found])

    def post(self, request):
        profile = require_profile(request)
        data = sz.GroupCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        as_main = data.validated_data.get("as_main", profile.main_group_id is None)
        group = groups.create_group(
            profile, data.validated_data["name"], data.validated_data["currency"], as_main
        )
        profile.refresh_from_db()
        me = Member.objects.get(group=group, profile=profile)
        return Response(_group_detail(request, group, me), status=201)


@extend_schema(responses=sz.GroupDetailSerializer)
class GroupDetailView(GroupScopedView):
    def get(self, request, group_id):
        return Response(_group_detail(request, self.group, self.me))


@extend_schema(request=sz.LinkSerializer, responses=sz.LinkResultSerializer)
class LinkView(GroupScopedView):
    def post(self, request, group_id):
        profile = require_profile(request)
        data = sz.LinkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        link = groups.set_link_active(profile, self.group, data.validated_data["active"])
        return Response({"link_active": link.active})


def _group_by_token(token: str) -> Group:
    group = Group.objects.filter(share_token=token).first()
    if group is None:
        raise LedgerError("not_found")
    return group


@method_decorator(ensure_csrf_cookie, name="get")
class JoinView(CsrfProtectedAPIView):
    @extend_schema(responses=sz.JoinPreviewSerializer)
    def get(self, request, token):
        group = _group_by_token(token)
        names = list(group.members.order_by("id").values_list("display_name", flat=True))
        return Response(
            {"group_name": group.name, "currency": group.currency, "member_names": names}
        )

    @extend_schema(request=sz.JoinSerializer, responses=sz.JoinResultSerializer)
    def post(self, request, token):
        group = _group_by_token(token)
        data = sz.JoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        name = data.validated_data["display_name"]
        profile = profile_of(request)
        existing = member_for(request, group)
        if existing is not None:
            member = existing
        else:
            member = groups.join_group_by_token(token, name, profile)
            if profile is None:
                add_guest_member(request, member)
        return Response({"group_id": group.id, "member_id": member.id})


@extend_schema(responses=sz.CategoryTreeSerializer(many=True))
class CategoryListView(APIView):
    def get(self, request):
        roots = Category.objects.filter(parent__isnull=True).prefetch_related(
            Prefetch("children", queryset=Category.objects.order_by("id"))
        )
        return Response(
            [
                {
                    "id": c.id,
                    "name": c.name,
                    "children": [{"id": k.id, "name": k.name} for k in c.children.all()],
                }
                for c in roots.order_by("id")
            ]
        )


class CategoryDefaultsView(GroupScopedView):
    @extend_schema(responses=sz.CategoryDefaultOutSerializer(many=True))
    def get(self, request, group_id):
        rows = CategoryDefault.objects.filter(group=self.group)
        return Response(
            {str(r.category_id): {"preset": r.split_type, "params": r.split_params} for r in rows}
        )

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses=sz.CategoryDefaultOutSerializer(many=True),
    )
    def put(self, request, group_id):
        if not isinstance(request.data, dict):
            raise exceptions.ParseError("expected an object keyed by category id")
        member_ids = sorted(self.group.members.values_list("id", flat=True))
        parsed: list[tuple[int, str, dict[str, Any]]] = []
        for key, value in request.data.items():
            body = sz.CategoryDefaultSerializer(data=value)
            body.is_valid(raise_exception=True)
            try:
                category_id = int(key)
            except ValueError as exc:
                raise exceptions.ParseError("keys must be category ids") from exc
            split_type, params = to_service_preset(
                body.validated_data["preset"],
                body.validated_data.get("params"),
                self.me.id,
                member_ids,
            )
            # Dry run: a bad default fails when saved, not on the next expense.
            split_for_preset(split_type, 100, member_ids, self.me.id, params)
            if not Category.objects.filter(pk=category_id).exists():
                raise LedgerError("not_found")
            parsed.append((category_id, split_type, params))
        with transaction.atomic():
            CategoryDefault.objects.filter(group=self.group).delete()
            CategoryDefault.objects.bulk_create(
                [
                    CategoryDefault(group=self.group, category_id=c, split_type=t, split_params=p)
                    for c, t, p in parsed
                ]
            )
        return self.get(request, group_id)


def _query(request) -> dict:
    raw = request.query_params
    q = sz.ExpenseQuerySerializer(
        data={
            k: raw[src]
            for k, src in (
                ("date_from", "from"),
                ("date_to", "to"),
                ("category", "category"),
                ("member", "member"),
                ("page", "page"),
            )
            if src in raw
        }
    )
    q.is_valid(raise_exception=True)
    return q.validated_data


def _expense_qs(group: Group, manager=Expense.objects):
    return manager.filter(group=group).prefetch_related(
        Prefetch("payers", queryset=ExpensePayer.objects.order_by("id")),
        Prefetch("splits", queryset=ExpenseSplit.objects.order_by("id")),
    )


class ExpenseListView(GroupScopedView):
    @extend_schema(
        parameters=[
            OpenApiParameter("from", datetime.date),
            OpenApiParameter("to", datetime.date),
            OpenApiParameter("category", int),
            OpenApiParameter("member", int),
            OpenApiParameter("page", int),
        ],
        responses=sz.ExpensePageSerializer,
    )
    def get(self, request, group_id):
        q = _query(request)
        qs = _expense_qs(self.group)
        if "date_from" in q:
            qs = qs.filter(date__gte=q["date_from"])
        if "date_to" in q:
            qs = qs.filter(date__lte=q["date_to"])
        if "category" in q:
            qs = qs.filter(Q(category_id=q["category"]) | Q(category__parent_id=q["category"]))
        if "member" in q:
            qs = qs.filter(
                Q(id__in=ExpensePayer.objects.filter(member_id=q["member"]).values("expense_id"))
                | Q(id__in=ExpenseSplit.objects.filter(member_id=q["member"]).values("expense_id"))
            )
        page = q.get("page", 1)
        count = qs.count()
        if page > 1 and (page - 1) * PAGE_SIZE >= count:
            raise exceptions.NotFound("no such page")
        rows = qs.order_by("-date", "-id")[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        return Response(
            {"count": count, "page": page, "results": sz.ExpenseOutSerializer(rows, many=True).data}
        )

    @extend_schema(request=sz.ExpenseWriteSerializer, responses={201: sz.ExpenseOutSerializer})
    def post(self, request, group_id):
        data = sz.ExpenseWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expense = _create_expense(self.group, data.validated_data)
        return Response(_expense_body(expense), status=201)


def _expense_body(expense: Expense) -> dict:
    fresh = _expense_qs(expense.group, Expense.all_objects).get(pk=expense.pk)
    return sz.ExpenseOutSerializer(fresh).data


def _create_expense(group: Group, d: dict[str, Any]) -> Expense:
    common: dict[str, Any] = {
        "description": d["description"],
        "currency": group.currency,
        "date": d["date"],
        "category": d["category"],
        "notes": d.get("notes", ""),
        **{k: d[k] for k in _ORIGINAL_KEYS if k in d},
    }
    if "payers" in d:
        return expenses.create_expense(
            group,
            amount_cents=d["amount_cents"],
            payers=d["payers"],
            splits=d["splits"],
            split_type=d["split_type"],
            **common,
        )
    member_ids = sorted(group.members.values_list("id", flat=True))
    payer = d["payer_member"]
    if "preset" in d:
        preset, params = d["preset"], d.get("params")
    else:
        preset, params = default_split_for(group, d["category"])
    split_type, service_params = to_service_preset(preset, params, payer, member_ids)
    return expenses.create_expense_from_preset(
        group,
        preset=split_type,
        payer_id=payer,
        member_ids=member_ids,
        params=service_params,
        amount_cents=d.get("amount_cents"),
        **common,
    )


class ExpenseDetailView(GroupScopedView):
    def _get(self, eid: int, manager=Expense.objects) -> Expense:
        expense = _expense_qs(self.group, manager).filter(pk=eid).first()
        if expense is None:
            raise LedgerError("not_found")
        return expense

    @extend_schema(request=sz.ExpenseWriteSerializer, responses=sz.ExpenseOutSerializer)
    def patch(self, request, group_id, eid):
        expense = self._get(eid)
        data = sz.ExpenseWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        _update_expense(self.group, expense, data.validated_data)
        return Response(_expense_body(expense))

    @extend_schema(responses={204: None})
    def delete(self, request, group_id, eid):
        expenses.delete_expense(self._get(eid, Expense.all_objects))
        return Response(status=204)


def _update_expense(group: Group, e: Expense, d: dict[str, Any]) -> None:
    """Merge the body over the stored expense.

    An expense keeps its `split_type` but not the preset params, so splits are never guessed
    from the old ones: a changed amount or payer needs a body that says how to split, unless the
    stored split_type is derivable without params (checked by reproducing the stored splits).
    """
    cur_payers = {p.member_id: p.paid_cents for p in e.payers.all()}
    cur_splits = {s.member_id: s.owed_cents for s in e.splits.all()}
    member_ids = sorted(group.members.values_list("id", flat=True))
    date = d.get("date", e.date)
    foreign = e.original_currency != e.currency

    original: dict[str, Any]
    if any(k in d for k in _ORIGINAL_KEYS):
        original = {k: d.get(k) for k in _ORIGINAL_KEYS}
        if "amount_cents" in d:
            amount = d["amount_cents"]
        elif original["original_amount_cents"] is not None and original["original_currency"]:
            amount, original["rate_used"] = resolve_foreign_amount(
                group,
                date,
                original["original_amount_cents"],
                original["original_currency"],
                original["rate_used"],
            )
        else:
            raise LedgerError("incomplete_original", "give original amount and currency together")
    elif foreign and date != e.date:
        # The stored rate belongs to the old date: convert again at the new one.
        amount, rate = resolve_foreign_amount(
            group, date, e.original_amount_cents, e.original_currency, d.get("rate_used")
        )
        amount = d.get("amount_cents", amount)
        original = {
            "original_amount_cents": e.original_amount_cents,
            "original_currency": e.original_currency,
            "rate_used": rate,
        }
    elif foreign:
        amount = d.get("amount_cents", e.amount_cents)
        original = {
            "original_amount_cents": e.original_amount_cents,
            "original_currency": e.original_currency,
            "rate_used": d.get("rate_used", e.rate_used),
        }
    else:
        amount = d.get("amount_cents", e.amount_cents)
        original = {k: None for k in _ORIGINAL_KEYS}

    payers, splits, split_type = cur_payers, cur_splits, e.split_type
    if "payers" in d:
        payers, splits, split_type = d["payers"], d["splits"], d["split_type"]
    elif "preset" in d or amount != e.amount_cents or "payer_member" in d:
        if len(cur_payers) != 1 and "payer_member" not in d:
            raise exceptions.ValidationError("send payers+splits for a multi-payer expense")
        payer = d.get("payer_member", next(iter(cur_payers)))
        if "preset" in d:
            split_type, params = to_service_preset(d["preset"], d.get("params"), payer, member_ids)
        else:
            old_payer = next(iter(cur_payers)) if len(cur_payers) == 1 else None
            split_type, params = e.split_type, {}
            try:
                reproduced = (
                    old_payer is not None
                    and split_for_preset(split_type, e.amount_cents, member_ids, old_payer, {})
                    == cur_splits
                )
            except LedgerError:
                reproduced = False
            if not reproduced:
                raise exceptions.ValidationError(
                    f"a {e.split_type} expense needs preset or payers+splits to change"
                )
        splits = split_for_preset(split_type, amount, member_ids, payer, params)
        payers = {payer: amount}

    expenses.update_expense(
        e,
        description=d.get("description", e.description),
        amount_cents=amount,
        currency=group.currency,
        date=date,
        category=d.get("category", e.category),
        payers=payers,
        splits=splits,
        split_type=split_type,
        notes=d.get("notes", e.notes),
        **original,
    )


class BalancesView(GroupScopedView):
    @extend_schema(responses=sz.BalancesSerializer)
    def get(self, request, group_id):
        nets = balances.net_balances(self.group)
        return Response(
            {
                "currency": self.group.currency,
                "nets": {str(m): c for m, c in nets.items()},
                "transfers": [
                    {"from_member": f, "to_member": t, "amount_cents": c}
                    for f, t, c in balances.simplify_debts(nets)
                ],
                "members": [
                    {"member_id": m.id, **balances.member_summary(self.group, m)}
                    for m in self.group.members.order_by("id")
                ],
            }
        )


class SettlementListView(GroupScopedView):
    @extend_schema(responses=sz.SettlementOutSerializer(many=True))
    def get(self, request, group_id):
        rows = Settlement.objects.filter(group=self.group).order_by("-date", "-id")
        return Response(sz.SettlementOutSerializer(rows, many=True).data)

    @extend_schema(
        request=sz.SettlementWriteSerializer, responses={201: sz.SettlementOutSerializer}
    )
    def post(self, request, group_id):
        data = sz.SettlementWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        # Resolved inside the group: another group's member id reads as "not in group".
        sender = Member.objects.filter(group=self.group, pk=d["from_member"]).first()
        receiver = Member.objects.filter(group=self.group, pk=d["to_member"]).first()
        if sender is None or receiver is None:
            raise LedgerError("member_not_in_group", "settlement members must belong to the group")
        row = balances.record_settlement(
            self.group, sender, receiver, d["amount_cents"], d["date"], d.get("notes", "")
        )
        return Response(sz.SettlementOutSerializer(row).data, status=201)


class MoveToHomeView(GroupScopedView):
    @extend_schema(
        request=sz.MoveToHomeSerializer, responses={201: sz.SettlementOutSerializer(many=True)}
    )
    def post(self, request, group_id):
        profile = require_profile(request)
        data = sz.MoveToHomeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        target = type(profile).objects.filter(pk=d["to_profile"]).first()
        if target is None:
            raise LedgerError("unknown_profile", f"profile {d['to_profile']}")
        try:
            pair = groups.move_debt_to_home(
                self.group, profile, target, d["amount_cents"], d["date"]
            )
        except LedgerError as exc:
            if exc.code == "trip_is_main_group":
                raise LedgerError("not_a_sub_group", "move-to-home is for sub-groups") from exc
            raise
        return Response(sz.SettlementOutSerializer(pair, many=True).data, status=201)


class RecurringScopedView(GroupScopedView):
    def rule(self, rid: int) -> RecurringRule:
        rule = RecurringRule.objects.filter(group=self.group, pk=rid).first()
        if rule is None:
            raise LedgerError("not_found")
        return rule


def _rule_fields(group: Group, d: dict[str, Any]) -> dict[str, Any]:
    fields = dict(d)
    if "payer" in fields:
        payer = Member.objects.filter(group=group, pk=fields["payer"]).first()
        if payer is None:
            raise LedgerError("not_a_member", f"payer {fields['payer']} is not in the group")
        fields["payer"] = payer
    return fields


class RuleListView(RecurringScopedView):
    @extend_schema(responses=sz.RuleOutSerializer(many=True))
    def get(self, request, group_id):
        rules = RecurringRule.objects.filter(group=self.group).order_by("id")
        return Response(sz.RuleOutSerializer(rules, many=True).data)

    @extend_schema(request=sz.RuleWriteSerializer, responses={201: sz.RuleOutSerializer})
    def post(self, request, group_id):
        data = sz.RuleWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rule = recurring.create_rule(self.group, **_rule_fields(self.group, data.validated_data))
        return Response(sz.RuleOutSerializer(rule).data, status=201)


class RuleDetailView(RecurringScopedView):
    @extend_schema(request=sz.RuleWriteSerializer, responses=sz.RuleOutSerializer)
    def patch(self, request, group_id, rid):
        rule = self.rule(rid)
        data = sz.RuleWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        recurring.update_rule(rule, today=today(), **_rule_fields(self.group, data.validated_data))
        return Response(sz.RuleOutSerializer(rule).data)

    @extend_schema(responses={204: None})
    def delete(self, request, group_id, rid):
        recurring.delete_rule(self.rule(rid))
        return Response(status=204)


class RuleActionView(RecurringScopedView):
    action = ""

    @extend_schema(request=None, responses=sz.RuleOutSerializer)
    def post(self, request, group_id, rid):
        rule = self.rule(rid)
        if self.action == "pause":
            recurring.pause_rule(rule)
        elif self.action == "resume":
            recurring.resume_rule(rule, today())
        else:
            recurring.skip_next(rule)
        return Response(sz.RuleOutSerializer(rule).data)


class PauseView(RuleActionView):
    action = "pause"


class ResumeView(RuleActionView):
    action = "resume"


class SkipView(RuleActionView):
    action = "skip"
