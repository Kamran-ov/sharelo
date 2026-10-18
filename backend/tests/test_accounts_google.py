import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Profile
from accounts.services import google
from ledger.errors import LedgerError

pytestmark = pytest.mark.django_db

User = get_user_model()


def claims(email="ann@example.com", sub="sub-1", verified=True, name="Ann G"):
    return {"email": email, "sub": sub, "name": name, "email_verified": verified}


@pytest.fixture
def google_on(settings):
    settings.GOOGLE_CLIENT_ID = "client-id"


def post(c, token="tok"):
    return c.post("/api/auth/google", {"id_token": token}, format="json")


def stub(monkeypatch, value):
    def fake(token):
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(google, "verify_id_token", fake)


def test_google_new_email_creates_user_and_profile_with_google_sub(google_on, monkeypatch):
    stub(monkeypatch, claims())
    c = APIClient()
    assert post(c).status_code == 200
    assert (User.objects.count(), Profile.objects.count()) == (1, 1)
    profile = Profile.objects.get()
    assert (profile.google_sub, profile.display_name) == ("sub-1", "Ann G")
    assert c.get("/api/me").json()["authenticated"] is True


def test_google_existing_email_logs_in_without_creating_anything(google_on, monkeypatch):
    user = User.objects.create_user(
        username="ann@example.com", email="ann@example.com", password="x-y-z-1234"
    )
    Profile.objects.create(user=user, display_name="Ann")
    stub(monkeypatch, claims(email="Ann@Example.com"))
    c = APIClient()
    assert post(c).status_code == 200
    assert (User.objects.count(), Profile.objects.count()) == (1, 1)
    assert c.get("/api/me").json()["profile"]["email"] == "ann@example.com"
    assert Profile.objects.get().google_sub == "sub-1"


def test_google_matches_by_sub_when_email_changed(google_on, monkeypatch):
    stub(monkeypatch, claims())
    post(APIClient())
    stub(monkeypatch, claims(email="renamed@example.com"))
    assert post(APIClient()).status_code == 200
    assert User.objects.count() == 1


def test_google_unverified_email_refused_and_does_not_take_over_password_account(
    google_on, monkeypatch
):
    user = User.objects.create_user(username="ann@example.com", email="ann@example.com")
    Profile.objects.create(user=user, display_name="Ann")
    stub(monkeypatch, claims(verified=False))
    c = APIClient()
    r = post(c)
    assert (r.status_code, r.json()["code"]) == (401, "google_invalid")
    assert c.get("/api/me").json()["authenticated"] is False
    assert Profile.objects.get().google_sub is None
    stub(monkeypatch, claims(verified=True))
    assert post(APIClient()).status_code == 200


def test_google_sub_conflict_refused(google_on, monkeypatch):
    user = User.objects.create_user(username="ann@example.com", email="ann@example.com")
    Profile.objects.create(user=user, display_name="Ann", google_sub="other")
    stub(monkeypatch, claims())
    r = post(APIClient())
    assert (r.status_code, r.json()["code"]) == (400, "google_conflict")


def test_google_verifier_raising_gives_401_google_invalid(google_on, monkeypatch):
    stub(monkeypatch, LedgerError("google_invalid"))
    r = post(APIClient())
    assert (r.status_code, r.json()["code"]) == (401, "google_invalid")
    assert User.objects.count() == 0


def test_google_library_error_is_wrapped_as_google_invalid(google_on, monkeypatch):
    def explode(*a, **k):
        raise ValueError("bad signature")

    monkeypatch.setattr(google.id_token, "verify_oauth2_token", explode)
    with pytest.raises(LedgerError) as e:
        google.verify_id_token("tok")
    assert e.value.code == "google_invalid"


def test_google_unset_client_id_gives_503_and_me_reports_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(google.id_token, "verify_oauth2_token", lambda *a: called.append(a))
    with override_settings(GOOGLE_CLIENT_ID=""):
        c = APIClient()
        r = post(c)
        assert (r.status_code, r.json()["code"]) == (503, "google_disabled")
        assert c.get("/api/me").json()["google_enabled"] is False
    assert called == []


def test_google_enabled_when_client_id_set(google_on, monkeypatch):
    stub(monkeypatch, claims())
    c = APIClient()
    assert c.get("/api/me").json()["google_enabled"] is True
    assert post(c).status_code == 200


def test_google_created_user_has_no_usable_password(google_on, monkeypatch):
    stub(monkeypatch, claims())
    post(APIClient())
    assert User.objects.get().has_usable_password() is False
    r = APIClient().post(
        "/api/auth/login", {"email": "ann@example.com", "password": ""}, format="json"
    )
    assert r.status_code == 401


def test_google_sub_unique_when_present_and_many_nulls_allowed():
    from django.db import IntegrityError, transaction

    def mk(name, sub):
        u = User.objects.create_user(username=name)
        return Profile.objects.create(user=u, display_name=name, google_sub=sub)

    mk("a", None)
    mk("b", None)
    mk("c", "s")
    with pytest.raises(IntegrityError), transaction.atomic():
        mk("d", "s")
