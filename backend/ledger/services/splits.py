"""Turn a one-tap split choice into exact per-member cents.

Every function returns ``dict[member_id, cents]`` and the values always sum to ``total_cents``.

Rounding rule (the only place it lives): floor every share, then hand the leftover cents one
each to members in ascending ``member_id`` order. 10.00 / 3 -> 334 / 333 / 333.

Units: percentages are integer basis points (5000 = 50.00%, must sum to 10000), so no float or
Decimal ever touches money.

Error codes, one per condition:
  amount_not_positive   total_cents <= 0
  empty_members         no members given
  duplicate_member      a member id appears twice
  invalid_share         shares weight is zero or negative (split_shares only)
  negative_share        negative basis points or negative exact cents
  percent_sum_mismatch  basis points do not sum to 10000
  exact_sum_mismatch    exact cents do not sum to total_cents
  invalid_params        preset params missing, or not a number where one is required
  unknown_preset        preset is not a SplitType value

The pure functions never touch the database; ``default_split_for`` at the bottom is the one
exception.
"""

from collections.abc import Collection, Mapping
from typing import Any

from ledger.errors import LedgerError
from ledger.models import Category, CategoryDefault, Group, SplitType

BASIS_POINTS_TOTAL = 10_000


def _check_int(value: object, what: str) -> int:
    # bool is an int subclass; True as a member id or a share is always a bug.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError("invalid_params", f"{what} must be an int, got {value!r}")
    return value


def _check_total(total_cents: int) -> None:
    _check_int(total_cents, "total_cents")
    if total_cents <= 0:
        raise LedgerError("amount_not_positive", f"total_cents={total_cents}")


def _check_members(member_ids: Collection[int]) -> None:
    if not member_ids:
        raise LedgerError("empty_members")
    for m in member_ids:
        _check_int(m, "member id")
    if len(set(member_ids)) != len(member_ids):
        raise LedgerError("duplicate_member", f"{sorted(member_ids)}")


def _distribute(total_cents: int, weights: Mapping[int, int]) -> dict[int, int]:
    weight_sum = sum(weights.values())
    result = {m: total_cents * w // weight_sum for m, w in weights.items()}
    leftover = total_cents - sum(result.values())
    assert 0 <= leftover < len(weights)
    for m in sorted(weights)[:leftover]:
        result[m] += 1
    return result


def split_equal(total_cents: int, member_ids: Collection[int]) -> dict[int, int]:
    _check_total(total_cents)
    _check_members(member_ids)
    return _distribute(total_cents, dict.fromkeys(member_ids, 1))


def split_personal(total_cents: int, payer_id: int) -> dict[int, int]:
    _check_total(total_cents)
    _check_members([payer_id])
    return {payer_id: total_cents}


def split_full_for_other(total_cents: int, other_id: int) -> dict[int, int]:
    _check_total(total_cents)
    _check_members([other_id])
    return {other_id: total_cents}


def split_percentage(total_cents: int, basis_points: Mapping[int, int]) -> dict[int, int]:
    _check_total(total_cents)
    _check_members(list(basis_points))
    for bp in basis_points.values():
        if _check_int(bp, "basis points") < 0:
            raise LedgerError("negative_share", f"basis points {bp}")
    if sum(basis_points.values()) != BASIS_POINTS_TOTAL:
        raise LedgerError(
            "percent_sum_mismatch", f"{sum(basis_points.values())} != {BASIS_POINTS_TOTAL}"
        )
    return _distribute(total_cents, basis_points)


def split_exact(total_cents: int, cents: Mapping[int, int]) -> dict[int, int]:
    _check_total(total_cents)
    _check_members(list(cents))
    for c in cents.values():
        if _check_int(c, "cents") < 0:
            raise LedgerError("negative_share", f"cents {c}")
    if sum(cents.values()) != total_cents:
        raise LedgerError("exact_sum_mismatch", f"{sum(cents.values())} != {total_cents}")
    return dict(cents)


def split_shares(total_cents: int, shares: Mapping[int, int]) -> dict[int, int]:
    _check_total(total_cents)
    _check_members(list(shares))
    for s in shares.values():
        if _check_int(s, "shares") <= 0:
            raise LedgerError("invalid_share", f"shares {s}")
    return _distribute(total_cents, shares)


def _int_keys(mapping: Any, key: str) -> dict[int, Any]:
    # split_params is stored as JSON, whose object keys are always strings.
    if not isinstance(mapping, Mapping):
        raise LedgerError("invalid_params", f"{key} must be a mapping")
    try:
        return {int(k): v for k, v in mapping.items()}
    except (TypeError, ValueError) as exc:
        raise LedgerError("invalid_params", f"{key} has a non-integer member id") from exc


def _param(params: Mapping[str, Any], key: str) -> Any:
    if key not in params:
        raise LedgerError("invalid_params", f"missing {key!r}")
    return params[key]


def split_for_preset(
    preset: str,
    total_cents: int,
    member_ids: Collection[int],
    payer_id: int,
    params: Mapping[str, Any] | None = None,
) -> dict[int, int]:
    """Dispatcher for the API. ``params`` shape per preset:

    equal, personal: {}; full_for_other: {"other_id": int}, optional with exactly two members;
    percentage: {"basis_points": {id: int}}; exact: {"cents": {id: int}};
    shares: {"shares": {id: int}}.
    """
    params = params or {}
    if preset == SplitType.EQUAL:
        result = split_equal(total_cents, member_ids)
    elif preset == SplitType.PERSONAL:
        result = split_personal(total_cents, payer_id)
    elif preset == SplitType.FULL_FOR_OTHER:
        if "other_id" in params:
            other_id = params["other_id"]
        else:
            others = [m for m in member_ids if m != payer_id]
            if len(member_ids) != 2 or len(others) != 1:
                raise LedgerError("invalid_params", "missing 'other_id'")
            other_id = others[0]
        result = split_full_for_other(total_cents, other_id)
    elif preset == SplitType.PERCENTAGE:
        result = split_percentage(
            total_cents, _int_keys(_param(params, "basis_points"), "basis_points")
        )
    elif preset == SplitType.EXACT:
        result = split_exact(total_cents, _int_keys(_param(params, "cents"), "cents"))
    elif preset == SplitType.SHARES:
        result = split_shares(total_cents, _int_keys(_param(params, "shares"), "shares"))
    else:
        raise LedgerError("unknown_preset", repr(preset))
    if sum(result.values()) != total_cents:  # last guard before anything is written
        raise LedgerError("splits_sum_mismatch", f"{sum(result.values())} != {total_cents}")
    return result


def default_split_for(group: Group, category: Category) -> tuple[str, dict[str, Any]]:
    row = CategoryDefault.objects.filter(group=group, category=category).first()
    if row is None:
        return SplitType.EQUAL.value, {}
    return row.split_type, row.split_params
