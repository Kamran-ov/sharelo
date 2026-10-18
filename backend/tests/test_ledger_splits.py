import itertools

import pytest

from ledger.errors import LedgerError
from ledger.models import SplitType
from ledger.services.splits import (
    split_equal,
    split_exact,
    split_for_preset,
    split_full_for_other,
    split_percentage,
    split_personal,
    split_shares,
)


def refused(code, fn, *args):
    with pytest.raises(LedgerError) as exc:
        fn(*args)
    assert exc.value.code == code


def test_every_split_sums_to_total():
    for total, n in itertools.product(range(1, 1001), range(2, 6)):
        ids = list(range(1, n + 1))
        bps = {i: 10_000 // n for i in ids}
        bps[ids[-1]] += 10_000 - sum(bps.values())
        results = [
            split_equal(total, ids),
            split_percentage(total, bps),
            split_shares(total, {i: i for i in ids}),
        ]
        for result in results:
            assert sum(result.values()) == total, (total, n, result)
            assert all(v >= 0 for v in result.values())


def test_leftover_cents_go_to_lowest_member_ids():
    assert split_equal(1000, [1, 2, 3]) == {1: 334, 2: 333, 3: 333}
    assert split_equal(1000, [9, 3, 5]) == {3: 334, 5: 333, 9: 333}
    assert split_equal(1001, [1, 2, 3]) == {1: 334, 2: 334, 3: 333}
    assert split_equal(999, [1, 2, 3]) == {1: 333, 2: 333, 3: 333}
    assert split_equal(1, [1, 2, 3]) == {1: 1, 2: 0, 3: 0}


def test_percentage_must_sum_to_100():
    refused("percent_sum_mismatch", split_percentage, 1000, {1: 5000, 2: 4999})
    refused("percent_sum_mismatch", split_percentage, 1000, {1: 5000, 2: 5001})
    refused("negative_share", split_percentage, 1000, {1: 11_000, 2: -1000})
    assert split_percentage(1000, {1: 5000, 2: 5000}) == {1: 500, 2: 500}
    assert split_percentage(1000, {1: 3333, 2: 3333, 3: 3334}) == {1: 334, 2: 333, 3: 333}


def test_exact_must_sum_to_total():
    refused("exact_sum_mismatch", split_exact, 1000, {1: 600, 2: 399})
    refused("exact_sum_mismatch", split_exact, 1000, {1: 600, 2: 401})
    refused("negative_share", split_exact, 1000, {1: 1100, 2: -100})
    assert split_exact(1000, {1: 600, 2: 400}) == {1: 600, 2: 400}


def test_shares_must_be_positive():
    refused("invalid_share", split_shares, 1000, {1: 0, 2: 1})
    refused("invalid_share", split_shares, 1000, {1: -1, 2: 2})
    assert split_shares(900, {1: 2, 2: 1}) == {1: 600, 2: 300}
    assert split_shares(1000, {1: 2, 2: 1}) == {1: 667, 2: 333}


def test_empty_members_refused():
    refused("empty_members", split_equal, 1000, [])
    refused("empty_members", split_shares, 1000, {})
    refused("empty_members", split_percentage, 1000, {})
    assert split_equal(1000, [7]) == {7: 1000}


def test_duplicate_member_ids_refused():
    refused("duplicate_member", split_equal, 1000, [1, 1, 2])
    assert split_equal(1000, [1, 2]) == {1: 500, 2: 500}


def test_total_must_be_positive():
    refused("amount_not_positive", split_equal, 0, [1, 2])
    refused("amount_not_positive", split_equal, -1, [1, 2])
    assert split_equal(1, [1, 2]) == {1: 1, 2: 0}


def test_bool_is_not_a_member_id():
    refused("invalid_params", split_equal, 1000, [True, 2])


def test_personal_owes_everything_to_payer():
    assert split_personal(1000, 4) == {4: 1000}
    assert split_full_for_other(1000, 5) == {5: 1000}
    assert split_for_preset("full_for_other", 1000, [1, 2], 1, {}) == {2: 1000}
    assert split_for_preset("full_for_other", 1000, [1, 2, 3], 1, {"other_id": 3}) == {3: 1000}
    refused("invalid_params", split_for_preset, "full_for_other", 1000, [1, 2, 3], 1, {})
    assert split_for_preset("personal", 2599, [1, 2, 3, 4], 4, {}) == {4: 2599}


def test_json_string_keys_accepted():
    from_json = {"basis_points": {"1": 7000, "2": 3000}}
    from_ints = {"basis_points": {1: 7000, 2: 3000}}
    expected = {1: 700, 2: 300}
    assert split_for_preset("percentage", 1000, [1, 2], 1, from_json) == expected
    assert split_for_preset("percentage", 1000, [1, 2], 1, from_ints) == expected
    refused("invalid_params", split_for_preset, "percentage", 1000, [1, 2], 1, {})
    refused(
        "invalid_params",
        split_for_preset,
        "percentage",
        1000,
        [1, 2],
        1,
        {"basis_points": {"x": 10_000}},
    )


def test_unknown_preset_refused():
    refused("unknown_preset", split_for_preset, "bogus", 1000, [1, 2], 1, {})
    params = {
        "equal": {},
        "personal": {},
        "full_for_other": {"other_id": 2},
        "percentage": {"basis_points": {1: 6000, 2: 4000}},
        "exact": {"cents": {1: 100, 2: 900}},
        "shares": {"shares": {1: 1, 2: 1}},
    }
    assert set(params) == set(SplitType.values)
    for preset, p in params.items():
        result = split_for_preset(preset, 1000, [1, 2], 1, p)
        assert sum(result.values()) == 1000
