from ledger.errors import LedgerError
from ledger.models import Group, Member

GUEST_KEY = "guest_member_ids"


def member_for(request, group: Group) -> Member | None:
    """Profile member first, then a guest id that belongs to `group`, whatever the auth state."""
    user = request.user
    if user.is_authenticated:
        profile = getattr(user, "profile", None)
        if profile is not None:
            member = Member.objects.filter(group=group, profile=profile).first()
            if member is not None:
                return member
    ids = request.session.get(GUEST_KEY) or []
    if not ids:
        return None
    return Member.objects.filter(group=group, id__in=ids).first()


def require_member(request, group: Group) -> Member:
    """404, not 403: a non-member must not learn that the group exists."""
    member = member_for(request, group)
    if member is None:
        raise LedgerError("not_found")
    return member


def add_guest_member(request, member: Member) -> None:
    ids = list(request.session.get(GUEST_KEY) or [])
    if member.id not in ids:
        ids.append(member.id)
        request.session[GUEST_KEY] = ids
        request.session.modified = True
