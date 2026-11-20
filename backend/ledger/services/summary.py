"""The shareable group summary: one read built only from the balance services.

Every number here comes from `net_balances`, `simplify_debts` and `member_summaries`; nothing is
recomputed, so the shared message can never disagree with the Balances page.
"""

from typing import Any

from django.db.models import Prefetch, Sum

from ledger.models import Expense, ExpensePayer, Group
from ledger.services import balances

RECENT_LIMIT = 10


def group_summary(group: Group) -> dict[str, Any]:
    nets = balances.net_balances(group)
    rows = balances.member_summaries(group)
    live = Expense.objects.filter(group=group)
    total = live.aggregate(total=Sum("amount_cents"))["total"] or 0
    recent = live.order_by("-date", "-id").prefetch_related(
        Prefetch("payers", queryset=ExpensePayer.objects.order_by("member_id"))
    )[:RECENT_LIMIT]
    return {
        "group": {"id": group.pk, "name": group.name},
        "currency": group.currency,
        "total_spent_cents": total,
        "per_member": [
            {"member_id": mid, "display_name": name, **rows[mid]}
            for mid, name in group.members.order_by("id").values_list("id", "display_name")
        ],
        "transfers": [
            {"from_member": f, "to_member": t, "amount_cents": c}
            for f, t, c in balances.simplify_debts(nets)
        ],
        "recent_expenses": [
            {
                "id": e.pk,
                "date": e.date,
                "description": e.description,
                "amount_cents": e.amount_cents,
                "paid_by": [p.member_id for p in e.payers.all()],
            }
            for e in recent
        ],
    }
