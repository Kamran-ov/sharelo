from django.http import JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

from ledger.errors import LedgerError

STATUS = {
    "invalid_credentials": 401,
    "google_invalid": 401,
    "not_authenticated": 401,
    "not_found": 404,
    "google_disabled": 503,
}


def error_body(code: str, detail: str) -> dict:
    return {"code": code, "detail": detail}


def csrf_failure(request, reason: str = "") -> JsonResponse:
    return JsonResponse(error_body("csrf_failed", "CSRF check failed."), status=403)


def handler(exc, context):
    if isinstance(exc, LedgerError):
        return Response(error_body(exc.code, str(exc)), status=STATUS.get(exc.code, 400))
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, exceptions.Throttled):
        code = "throttled"
    elif isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        code = "not_authenticated"
    elif isinstance(exc, exceptions.PermissionDenied):
        # SessionAuthentication raises PermissionDenied("CSRF Failed: ..."); other refusals
        # (010's permissions) must not read as CSRF errors.
        code = "csrf_failed" if str(exc.detail).startswith("CSRF Failed") else "forbidden"
    elif isinstance(exc, exceptions.NotFound):
        code = "not_found"
    else:
        code = "invalid_request"
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = error_body(code, str(detail) if detail else str(response.data))
    return response
