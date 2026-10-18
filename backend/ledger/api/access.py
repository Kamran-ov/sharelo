from accounts.api.csrf import CsrfProtectedAPIView
from accounts.services.access import require_member
from ledger.errors import LedgerError
from ledger.models import Group, Member


def profile_of(request):
    user = request.user
    return getattr(user, "profile", None) if user.is_authenticated else None


def require_profile(request):
    profile = profile_of(request)
    if profile is None:
        raise LedgerError("not_authenticated", "sign in to do this")
    return profile


class GroupScopedView(CsrfProtectedAPIView):
    """Every `groups/<group_id>/...` view derives from this; it is the only membership check.

    CSRF protection comes from the base: DRF skips the token for anonymous (guest) sessions.
    A missing group and a non-member get the same 404 so existence is not revealed.
    """

    group: Group
    me: Member

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        group = Group.objects.filter(pk=kwargs["group_id"]).first()
        if group is None:
            raise LedgerError("not_found")
        self.group = group
        self.me = require_member(request, group)
