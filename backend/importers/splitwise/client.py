"""The only code that talks to Splitwise. Tests stub `_open`; no test touches the network."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ledger.errors import LedgerError

BASE_URL = "https://secure.splitwise.com/api/v3.0/"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30


def _open(request: urllib.request.Request) -> str:
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https host
        return response.read().decode("utf-8")


class SplitwiseClient:
    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise LedgerError("missing_api_key", "set SPLITWISE_API_KEY")
        self._api_key = api_key.strip()

    @classmethod
    def from_env(cls) -> "SplitwiseClient":
        return cls(os.environ.get("SPLITWISE_API_KEY", ""))

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        )
        try:
            text = _open(request)
        except urllib.error.HTTPError as exc:
            raise LedgerError("splitwise_http", f"{exc.code} {path}") from exc
        except urllib.error.URLError as exc:
            raise LedgerError("splitwise_http", f"{exc.reason} {path}") from exc
        # parse_float=str: a JSON number never becomes a float; amounts stay exact strings.
        return json.loads(text, parse_float=str)

    def get_current_user(self) -> dict[str, Any]:
        return self._get("get_current_user")["user"]

    def get_group(self, group_id: int) -> dict[str, Any]:
        return self._get(f"get_group/{int(group_id)}")["group"]

    def get_categories(self) -> list[dict[str, Any]]:
        return self._get("get_categories")["categories"]

    def get_expenses(self, group_id: int) -> list[dict[str, Any]]:
        """Every expense of the group, deleted ones included, paged until a short page."""
        out: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._get(
                "get_expenses", {"group_id": int(group_id), "limit": PAGE_SIZE, "offset": offset}
            )["expenses"]
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE
