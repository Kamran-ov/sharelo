"""Home analytics: the main group's spending plus every linked sub-group, in Home's currency.

Who contributes: a profile that has a Member in the main group AND an active `GroupLink` from a
sub-group into it. Only that profile's own Member in the sub-group counts, so trip guests,
inactive links, and members whose link points at another main group never appear here.
Settlements are never queried: a Move-to-Home pair is not spending.

Rounding rule (cell level): each sub-group is read as cells of (expense date, member, category),
and every cell is converted once at its own date's rate, half-even. All figures here (by member,
category at either level and in either trip mode, month, trip line, breakdown) are Python sums of
those same converted cells, so they agree to the cent. Converting a whole day at once would give
a different cent on some days; that is deliberately not done.

Query cost depends on the number N of linked sub-groups only: three constant queries (the
main-group `analytics` call, Home members with a profile, active links) plus per sub-group one
cell aggregate and at most one rate query. A missing rate raises `LedgerError(no_rate)`.
"""

import datetime
from dataclasses import dataclass
from typing import Literal

from django.db.models import Sum

from ledger.errors import LedgerError
from ledger.models import Group, GroupLink, Member
from ledger.services import analytics, rates

Trips = Literal["lines", "spread"]
CategoryKey = int | tuple[str, int]


@dataclass(frozen=True)
class LinkedTrip:
    group_id: int
    name: str
    currency: str


@dataclass(frozen=True)
class _Cell:
    group_id: int
    date: datetime.date
    member_id: int
    profile_id: int
    category_id: int
    parent_id: int | None
    cents: int  # already in the main group's currency

    def category(self, level: int) -> int:
        return (self.parent_id or self.category_id) if level == 1 else self.category_id


def _check_trips(trips: str) -> None:
    if trips not in ("lines", "spread"):
        raise LedgerError("invalid_trips", f"trips={trips!r}")


def _check_level(level: int) -> None:
    if level not in (1, 2):
        raise LedgerError("invalid_level", f"level={level}")


def _links(main_group: Group) -> list[tuple[int, str, str, int]]:
    """(sub_group_id, name, currency, profile_id) of every contributing active link."""
    home_profiles = Member.objects.filter(group=main_group, profile__isnull=False).values(
        "profile_id"
    )
    return list(
        GroupLink.objects.filter(main_group=main_group, active=True, profile_id__in=home_profiles)
        .order_by("sub_group_id", "profile_id")
        .values_list("sub_group_id", "sub_group__name", "sub_group__currency", "profile_id")
    )


def linked_trips(main_group: Group) -> list[LinkedTrip]:
    seen: dict[int, LinkedTrip] = {}
    for group_id, name, currency, _ in _links(main_group):
        seen.setdefault(group_id, LinkedTrip(group_id, name, currency))
    return list(seen.values())


def _trip_cells(
    main_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    only_group_id: int | None = None,
) -> tuple[list[_Cell], list[LinkedTrip]]:
    by_group: dict[int, list[int]] = {}
    trips: dict[int, LinkedTrip] = {}
    for group_id, name, currency, profile_id in _links(main_group):
        if only_group_id is not None and group_id != only_group_id:
            continue
        by_group.setdefault(group_id, []).append(profile_id)
        trips.setdefault(group_id, LinkedTrip(group_id, name, currency))

    cells: list[_Cell] = []
    for group_id, profile_ids in by_group.items():
        trip = trips[group_id]
        rows = list(
            analytics._splits_in_range(Group(pk=group_id), date_from, date_to, None)
            .filter(member__profile_id__in=profile_ids)
            .values(
                "expense__date",
                "member_id",
                "member__profile_id",
                "expense__category_id",
                "expense__category__parent_id",
            )
            .annotate(total=Sum("owed_cents"))
            .values_list(
                "expense__date",
                "member_id",
                "member__profile_id",
                "expense__category_id",
                "expense__category__parent_id",
                "total",
            )
        )
        if not rows:
            continue
        days = [r[0] for r in rows]
        to_main = rates.range_converter(trip.currency, main_group.currency, min(days), max(days))
        for day, member_id, profile_id, category_id, parent_id, total in rows:
            cells.append(
                _Cell(
                    group_id,
                    day,
                    member_id,
                    profile_id,
                    category_id,
                    parent_id,
                    to_main(day, total),
                )
            )
    return cells, list(trips.values())


def home_spending_by_member(
    main_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    trips: Trips = "lines",
) -> dict[int, int]:
    _check_trips(trips)
    result = analytics.spending_by_member(main_group, date_from, date_to)
    cells, _ = _trip_cells(main_group, date_from, date_to)
    if not cells:
        return result
    home_member = dict(
        Member.objects.filter(group=main_group, profile__isnull=False).values_list(
            "profile_id", "id"
        )
    )
    for cell in cells:
        result[home_member[cell.profile_id]] += cell.cents
    return result


def home_spending_by_category(
    main_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    trips: Trips = "lines",
    level: int = 1,
) -> dict[CategoryKey, int]:
    _check_trips(trips)
    _check_level(level)
    result: dict[CategoryKey, int] = dict(
        analytics.spending_by_category(main_group, date_from, date_to, level=level)
    )
    cells, _ = _trip_cells(main_group, date_from, date_to)
    for cell in cells:
        key: CategoryKey = ("trip", cell.group_id) if trips == "lines" else cell.category(level)
        result[key] = result.get(key, 0) + cell.cents
    return result


def home_spending_by_month(
    main_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    trips: Trips = "lines",
) -> dict[str, int]:
    _check_trips(trips)
    result = dict(analytics.spending_by_month(main_group, date_from, date_to))
    cells, _ = _trip_cells(main_group, date_from, date_to)
    for cell in cells:
        month = cell.date.strftime("%Y-%m")
        result[month] = result.get(month, 0) + cell.cents
    return result


def home_trip_breakdown(
    main_group: Group,
    trip_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    level: int = 1,
) -> dict[int, dict[int, int]]:
    _check_level(level)
    cells, trips = _trip_cells(main_group, date_from, date_to, only_group_id=trip_group.id)
    if not trips:
        raise LedgerError("trip_not_linked", f"group {trip_group.id} is not linked")
    result: dict[int, dict[int, int]] = {}
    for cell in cells:
        by_category = result.setdefault(cell.member_id, {})
        key = cell.category(level)
        by_category[key] = by_category.get(key, 0) + cell.cents
    return result
