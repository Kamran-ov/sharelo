import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Profile

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


def register(client, email="Ann@Example.com", **over):
    body = {"email": email, "password": PASSWORD, "display_name": "Ann"} | over
    return client.post("/api/auth/register", body, format="json")


def login(client, email="ann@example.com", password=PASSWORD, **extra):
    return client.post(
        "/api/auth/login", {"email": email, "password": password}, format="json", **extra
    )


def test_register_logs_in_and_me_shows_display_name():
    c = APIClient()
    r = register(c)
    assert r.status_code == 200
    me = c.get("/api/me").json()
    assert me["authenticated"] is True
    assert me["profile"]["display_name"] == "Ann"
    assert me["profile"]["email"] == "ann@example.com"
    assert User.objects.get().username == "ann@example.com"
    assert Profile.objects.count() == 1


def test_register_same_email_different_case_refused_as_email_taken():
    register(APIClient())
    r = register(APIClient(), email="ANN@example.COM")
    assert (r.status_code, r.json()["code"]) == (400, "email_taken")
    assert User.objects.count() == 1


def test_register_other_email_succeeds_after_a_refusal():
    register(APIClient())
    assert register(APIClient(), email="bob@example.com").status_code == 200
    assert User.objects.count() == 2


def test_register_weak_password_refused_and_strong_passes():
    r = register(APIClient(), password="12345678")
    assert (r.status_code, r.json()["code"]) == (400, "weak_password")
    assert User.objects.count() == 0
    assert register(APIClient()).status_code == 200


def test_register_invalid_email_refused():
    r = register(APIClient(), email="not-an-email")
    assert (r.status_code, r.json()["code"]) == (400, "invalid_email")


def test_register_blank_display_name_refused():
    r = register(APIClient(), display_name="   ")
    assert (r.status_code, r.json()["code"]) == (400, "invalid_display_name")
    assert User.objects.count() == 0


def test_login_wrong_password_is_401_and_correct_is_200_with_working_cookie():
    register(APIClient())
    c = APIClient()
    assert login(c, password="nope-nope-nope").status_code == 401
    assert c.get("/api/me").json()["authenticated"] is False
    assert login(c).status_code == 200
    assert c.get("/api/me").json()["authenticated"] is True


def test_login_unknown_email_indistinguishable_from_wrong_password():
    register(APIClient())
    wrong = login(APIClient(), password="nope-nope-nope")
    unknown = login(APIClient(), email="ghost@example.com")
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
    assert wrong.json()["code"] == "invalid_credentials"


def test_login_is_case_insensitive_on_email():
    register(APIClient())
    assert login(APIClient(), email="ANN@EXAMPLE.COM").status_code == 200


def test_logout_clears_session_and_me_is_anonymous():
    c = APIClient()
    register(c)
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/me").json()["authenticated"] is False


def test_me_anonymous_shape():
    me = APIClient().get("/api/me").json()
    assert me == {
        "authenticated": False,
        "profile": None,
        "guest_memberships": [],
        "google_enabled": False,
    }


def test_me_authenticated_shape():
    c = APIClient()
    register(c)
    me = c.get("/api/me").json()
    assert set(me) == {"authenticated", "profile", "guest_memberships", "google_enabled"}
    assert set(me["profile"]) == {"id", "display_name", "email", "main_group_id"}


def test_eleventh_auth_attempt_in_a_minute_is_429():
    c = APIClient()
    codes = [login(c, email="x@example.com").status_code for _ in range(10)]
    assert codes == [401] * 10
    r = login(c, email="x@example.com")
    assert (r.status_code, r.json()["code"]) == (429, "throttled")


def test_throttle_resets_when_the_window_is_cleared():
    from django.core.cache import cache

    c = APIClient()
    for _ in range(11):
        login(c, email="x@example.com")
    cache.clear()
    assert login(c, email="x@example.com").status_code == 401


def test_throttle_bucket_is_shared_across_login_register_google():
    c = APIClient()
    for _ in range(5):
        login(c, email="x@example.com")
    for i in range(5):
        register(c, email=f"u{i}@example.com", password="1")
    assert login(c, email="x@example.com").status_code == 429


def test_authenticated_caller_is_throttled_like_anonymous():
    User.objects.create_user(username="bob@example.com", password=PASSWORD)
    c = APIClient()
    register(c, email="ann@example.com")  # attempt 1, leaves c signed in
    codes = [
        login(c, email="bob@example.com", password="wrong-wrong-1").status_code for _ in range(9)
    ]
    assert codes == [401] * 9
    assert login(c, email="bob@example.com", password="wrong-wrong-1").status_code == 429


def test_spoofed_forwarded_for_header_shares_the_bucket():
    c = APIClient()
    for i in range(10):
        r = login(c, email="x@example.com", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}")
        assert r.status_code == 401
    r = login(c, email="x@example.com", HTTP_X_FORWARDED_FOR="10.0.0.99")
    assert r.status_code == 429


def test_unsafe_post_without_csrf_token_is_403():
    for path, body in (
        ("/api/auth/login", {"email": "a@example.com", "password": "x"}),
        (
            "/api/auth/register",
            {"email": "a@example.com", "password": PASSWORD, "display_name": "A"},
        ),
        ("/api/auth/google", {"id_token": "t"}),
    ):
        r = APIClient(enforce_csrf_checks=True).post(path, body, format="json")
        assert r.status_code == 403, path
        assert r.json()["code"] == "csrf_failed"
        assert set(r.json()) == {"code", "detail"}


def test_post_with_csrf_token_from_me_cookie_succeeds():
    register(APIClient())
    c = APIClient(enforce_csrf_checks=True)
    token = c.get("/api/me").cookies["csrftoken"].value
    r = c.post(
        "/api/auth/login",
        {"email": "ann@example.com", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert r.status_code == 200


def test_authenticated_session_csrf_failure_has_the_same_body(rf):
    from django.test import override_settings
    from django.urls import path
    from rest_framework.response import Response
    from rest_framework.views import APIView

    class Probe(APIView):
        def post(self, request):
            return Response({})

    urlconf = type("U", (), {"urlpatterns": [path("probe", Probe.as_view())]})
    register(APIClient())
    c = APIClient(enforce_csrf_checks=True)
    token = c.get("/api/me").cookies["csrftoken"].value
    c.post(
        "/api/auth/login",
        {"email": "ann@example.com", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    with override_settings(ROOT_URLCONF=urlconf):
        r = c.post("/probe", {}, format="json")
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"
    assert set(r.json()) == {"code", "detail"}


def test_error_bodies_always_have_code_and_detail():
    c = APIClient()
    samples = [
        c.post("/api/auth/register", {}, format="json"),
        login(c, email="ghost@example.com"),
        register(c, password="1"),
    ]
    for r in samples:
        assert set(r.json()) == {"code", "detail"}, r.json()
    assert [r.status_code for r in samples] == [400, 401, 400]


def test_non_csrf_permission_denied_is_not_reported_as_csrf():
    from django.test import override_settings
    from django.urls import path
    from rest_framework.exceptions import PermissionDenied
    from rest_framework.views import APIView

    class Deny(APIView):
        def get(self, request):
            raise PermissionDenied("nope")

    urlconf = type("U", (), {"urlpatterns": [path("deny", Deny.as_view())]})
    with override_settings(ROOT_URLCONF=urlconf):
        r = APIClient().get("/deny")
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")


def test_register_integrity_error_other_than_username_is_not_email_taken(monkeypatch):
    from django.db import IntegrityError

    from accounts.services import auth
    from ledger.errors import LedgerError

    def boom(*a, **k):
        raise IntegrityError("some_other_constraint")

    monkeypatch.setattr(Profile.objects, "create", boom)
    with pytest.raises(IntegrityError):
        auth.register("a@example.com", PASSWORD, "A")
    assert LedgerError  # imported for clarity of the contrast


def test_register_race_on_username_is_email_taken(monkeypatch):
    from accounts.services import auth
    from ledger.errors import LedgerError

    real = auth.User.objects.filter

    class Hidden:
        def exists(self):
            return False

    def blind(*a, **k):
        return Hidden() if k.get("username") else real(*a, **k)

    User.objects.create_user(username="ann@example.com", email="ann@example.com")
    monkeypatch.setattr(auth.User.objects, "filter", blind)
    with pytest.raises(LedgerError) as e:
        auth.register("ann@example.com", PASSWORD, "Ann")
    assert e.value.code == "email_taken"
    assert User.objects.count() == 1
