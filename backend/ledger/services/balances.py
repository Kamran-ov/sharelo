"""Balances are computed on every call from expenses and settlements, never stored.

Sign convention: a positive net means the member is owed money, a negative net means they owe.
For each non-deleted expense a member's net grows by what they paid and shrinks by what they owe.
A settlement raises the sender's net and lowers the receiver's by the same amount. The nets of a
group therefore always sum to 0; if they do not, `LedgerError("balance_drift")` is raised rather
than returning wrong balances.

`simplify_debts` is greedy: the largest debtor pays the largest creditor, ties broken by lowest
member id, so the output is deterministic. Every step settles at least one person, so the
number of transfers is below the number of people involved.
"""

import datetime

from django.db.models import Sum

from ledger.errors import LedgerError
from ledger.models import ExpensePayer, ExpenseSplit, Group, Member, Settlement


def _sum_by_member(rows, field: str) -> dict[int, int]:
    return {r["member_id"]: r["total"] for r in rows.values("member_id").annotate(total=Sum(field))}


def _settlement_flows(group: Group) -> tuple[dict[int, int], dict[int, int]]:
    sent = _sum_by_member_key(group, "from_member_id")
    received = _sum_by_member_key(group, "to_member_id")
    return sent, received


def _sum_by_member_key(group: Group, key: str) -> dict[int, int]:
    rows = Settlement.objects.filter(group=group).values(key).annotate(total=Sum("amount_cents"))
    return {r[key]: r["total"] for r in rows}


def _paid_and_owed(group: Group) -> tuple[dict[int, int], dict[int, int]]:
    live = {"expense__group": group, "expense__deleted_at__isnull": True}
    paid = _sum_by_member(ExpensePayer.objects.filter(**live), "paid_cents")
    owed = _sum_by_member(ExpenseSplit.objects.filter(**live), "owed_cents")
    return paid, owed


def _check_balanced(nets: dict[int, int]) -> None:
    total = sum(nets.values())
    if total != 0:
        raise LedgerError("balance_drift", f"nets sum to {total}, not 0")


def net_balances(group: Group) -> dict[int, int]:
    paid, owed = _paid_and_owed(group)
    sent, received = _settlement_flows(group)
    nets = {
        member_id: (
            paid.get(member_id, 0)
            - owed.get(member_id, 0)
            + sent.get(member_id, 0)
            - received.get(member_id, 0)
        )
        for member_id in group.members.values_list("id", flat=True)
    }
    _check_balanced(nets)
    return nets


def simplify_debts(nets: dict[int, int]) -> list[tuple[int, int, int]]:
    """Return (from_member_id, to_member_id, cents) transfers that bring every net to zero."""
    _check_balanced(nets)
    debtors = {m: -c for m, c in nets.items() if c < 0}
    creditors = {m: c for m, c in nets.items() if c > 0}
    transfers: list[tuple[int, int, int]] = []
    while debtors:
        debtor = min(debtors, key=lambda m: (-debtors[m], m))
        creditor = min(creditors, key=lambda m: (-creditors[m], m))
        cents = min(debtors[debtor], creditors[creditor])
        transfers.append((debtor, creditor, cents))
        for side, member in ((debtors, debtor), (creditors, creditor)):
            side[member] -= cents
            if side[member] == 0:
                del side[member]
    return transfers


def record_settlement(
    group: Group,
    from_member: Member,
    to_member: Member,
    amount_cents: int,
    date: datetime.date,
    notes: str = "",
) -> Settlement:
    if amount_cents <= 0:
        raise LedgerError("amount_not_positive", f"amount_cents={amount_cents}")
    if from_member.pk == to_member.pk:
        raise LedgerError("same_member", "a settlement needs two different members")
    if from_member.group_id != group.pk or to_member.group_id != group.pk:
        raise LedgerError("member_not_in_group", "settlement members must belong to the group")
    return Settlement.objects.create(
        group=group,
        from_member=from_member,
        to_member=to_member,
        amount_cents=amount_cents,
        currency=group.currency,
        date=date,
        notes=notes,
    )


def member_summary(group: Group, member: Member) -> dict[str, int]:
    if member.group_id != group.pk:
        raise LedgerError("member_not_in_group", f"member {member.pk}")
    paid, owed = _paid_and_owed(group)
    sent, received = _settlement_flows(group)
    mid = member.pk
    return {
        "paid": paid.get(mid, 0),
        "owed_share": owed.get(mid, 0),
        "net": paid.get(mid, 0) - owed.get(mid, 0) + sent.get(mid, 0) - received.get(mid, 0),
    }
