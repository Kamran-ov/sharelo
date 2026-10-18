from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from ledger.errors import LedgerError


def verify_id_token(token: str) -> dict:
    """The only place the google-auth library is called; tests stub this function."""
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise LedgerError("google_disabled")
    try:
        info = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
        return {
            "email": info["email"],
            "sub": info["sub"],
            "name": info.get("name", ""),
            "email_verified": bool(info.get("email_verified")),
        }
    except Exception as exc:
        raise LedgerError("google_invalid", str(exc)) from exc
