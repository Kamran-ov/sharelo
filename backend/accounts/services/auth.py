from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from accounts.models import Profile
from ledger.errors import LedgerError

User = get_user_model()

USERNAME_CONSTRAINT = "auth_user_username_key"
MAX_USERNAME = 150


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise LedgerError("invalid_email") from exc
    if len(email) > MAX_USERNAME:
        raise LedgerError("invalid_email")
    return email


def register(email: str, password: str, display_name: str) -> Profile:
    email = normalize_email(email)
    display_name = (display_name or "").strip()
    if not 1 <= len(display_name) <= 100:
        raise LedgerError("invalid_display_name")
    if User.objects.filter(username=email).exists():
        raise LedgerError("email_taken")
    try:
        validate_password(password, User(username=email, email=email))
    except ValidationError as exc:
        raise LedgerError("weak_password", " ".join(exc.messages)) from exc
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)
            return Profile.objects.create(user=user, display_name=display_name)
    except IntegrityError as exc:
        # A race on the username; any other integrity failure is a bug and must surface.
        if USERNAME_CONSTRAINT in str(exc):
            raise LedgerError("email_taken") from exc
        raise


def authenticate_email(email: str, password: str):
    try:
        email = normalize_email(email)
    except LedgerError:
        raise LedgerError("invalid_credentials") from None
    user = User.objects.filter(username=email).first()
    if user is None or not user.is_active or not user.check_password(password or ""):
        raise LedgerError("invalid_credentials")
    return user


def login_with_google(claims: dict) -> Profile:
    if not claims.get("email_verified"):
        raise LedgerError("google_invalid", "email not verified")
    sub = claims["sub"]
    profile = Profile.objects.select_related("user").filter(google_sub=sub).first()
    if profile is not None:
        return profile
    email = normalize_email(claims["email"])
    user = User.objects.filter(username=email).first()
    if user is not None:
        profile = Profile.objects.select_related("user").filter(user=user).first()
        if profile is None:
            profile = Profile.objects.create(
                user=user, display_name=(claims.get("name") or email.split("@")[0])[:100]
            )
        if profile.google_sub and profile.google_sub != sub:
            raise LedgerError("google_conflict")
        profile.google_sub = sub
        profile.save(update_fields=["google_sub"])
        return profile
    with transaction.atomic():
        user = User(username=email, email=email)
        user.set_unusable_password()
        user.save()
        return Profile.objects.create(
            user=user,
            display_name=(claims.get("name") or email.split("@")[0])[:100],
            google_sub=sub,
        )
