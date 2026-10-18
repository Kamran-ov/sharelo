"""API vocabulary → the service presets in `ledger.services.splits`.

Only renames and param reshaping live here; the splitting arithmetic stays in `splits.py`.
"""

from collections.abc import Collection, Mapping
from typing import Any

from ledger.errors import LedgerError


def to_service_preset(
    preset: str, params: Mapping[str, Any] | None, payer_id: int, member_ids: Collection[int]
) -> tuple[str, dict[str, Any]]:
    params = dict(params or {})
    if preset == "half":
        if len(member_ids) != 2:
            raise LedgerError("invalid_params", "half needs exactly two members")
        return "equal", {}
    if preset == "percentage" and "percent_payer" in params:
        percent = params["percent_payer"]
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise LedgerError("invalid_params", "percent_payer must be an integer from 0 to 100")
        others = [m for m in member_ids if m != payer_id]
        if len(member_ids) != 2 or len(others) != 1:
            raise LedgerError("invalid_params", "percent_payer needs exactly two members")
        return "percentage", {
            "basis_points": {payer_id: percent * 100, others[0]: (100 - percent) * 100}
        }
    return preset, params
