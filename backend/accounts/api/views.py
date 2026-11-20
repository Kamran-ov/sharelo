from django.conf import settings
from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api import serializers
from accounts.api.csrf import CsrfProtectedAPIView
from accounts.api.throttles import AuthThrottle
from accounts.services import auth, google
from accounts.services.access import GUEST_KEY
from ledger.models import Member
from ledger.services import groups


def me_body(request, guest_refused: list[dict] | None = None) -> dict:
    user = request.user
    profile = getattr(user, "profile", None) if user.is_authenticated else None
    ids = request.session.get(GUEST_KEY) or []
    guests = sorted(Member.objects.filter(id__in=ids).values_list("id", flat=True)) if ids else []
    return {
        "authenticated": profile is not None,
        "profile": None
        if profile is None
        else {
            "id": profile.id,
            "display_name": profile.display_name,
            "email": user.email,
            "main_group_id": profile.main_group_id,
        },
        "guest_memberships": guests,
        "guest_refused": guest_refused or [],
        "google_enabled": bool(settings.GOOGLE_CLIENT_ID),
    }


def sign_in(request, user) -> Response:
    # login() flushes the session when the user changes; guest memberships must survive it.
    guest_ids = list(request.session.get(GUEST_KEY) or [])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    refused: list[dict] = []
    profile = getattr(user, "profile", None)
    if guest_ids and profile is None:
        request.session[GUEST_KEY] = guest_ids
    elif guest_ids:
        # The session's guest members become this profile's; only the refused ones stay guests.
        result = groups.adopt_guest_members(profile, guest_ids)
        request.session[GUEST_KEY] = result.kept
        refused = [{"member_id": m, "group_id": g, "code": c} for m, g, c in result.refused]
    return Response(me_body(request, refused))


@method_decorator(ensure_csrf_cookie, name="get")
class MeView(APIView):
    @extend_schema(responses=serializers.MeSerializer)
    def get(self, request):
        return Response(me_body(request))


class RegisterView(CsrfProtectedAPIView):
    throttle_classes = [AuthThrottle]

    @extend_schema(request=serializers.RegisterSerializer, responses=serializers.MeSerializer)
    def post(self, request):
        data = serializers.RegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        profile = auth.register(**data.validated_data)
        return sign_in(request, profile.user)


class LoginView(CsrfProtectedAPIView):
    throttle_classes = [AuthThrottle]

    @extend_schema(request=serializers.LoginSerializer, responses=serializers.MeSerializer)
    def post(self, request):
        data = serializers.LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return sign_in(request, auth.authenticate_email(**data.validated_data))


class GoogleView(CsrfProtectedAPIView):
    throttle_classes = [AuthThrottle]

    @extend_schema(request=serializers.GoogleSerializer, responses=serializers.MeSerializer)
    def post(self, request):
        data = serializers.GoogleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        claims = google.verify_id_token(data.validated_data["id_token"])
        return sign_in(request, auth.login_with_google(claims).user)


class LogoutView(CsrfProtectedAPIView):
    @extend_schema(request=None, responses=serializers.MeSerializer)
    def post(self, request):
        # logout() flushes the session; free its guest names first so the link can offer them again.
        ids = request.session.get(GUEST_KEY) or []
        for member in Member.objects.filter(id__in=ids):
            groups.release_guest(member)
        logout(request)
        return Response(me_body(request))
