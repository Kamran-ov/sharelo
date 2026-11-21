"""Analytics as API rows: the numbers of `analytics` and `home`, labelled and ordered.

No money arithmetic happens here beyond summing a member's nested rows: every figure comes
from the two services, so a report and the service it calls always agree to the cent.
Every key is a string so one row shape fits members, categories, trip lines and months.
"""

import calendar
import datetime
from collections.abc import Iterable, Mapping
from typing import Any

from ledger.errors import LedgerError
from ledger.models import Category, Group, Member
from ledger.services import analytics, home

BY = ("member", "category", "month", "member_category")
HOME_BY = ("member", "category", "month")
MAX_YEARS = 5

Row = dict[str, Any]


def default_range(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last)


def _add_years(day: datetime.date, years: int) -> datetime.date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 Feb into a non-leap year
        return day.replace(year=day.year + years, day=28)


def check_range(date_from: datetime.date, date_to: datetime.date) -> None:
    if date_from > date_to:
        raise LedgerError("invalid_range", f"from {date_from} is after to {date_to}")
    if date_to >= _add_years(date_from, MAX_YEARS):
        raise LedgerError("range_too_long", f"at most {MAX_YEARS} years")


def _check_by(by: str, allowed: tuple[str, ...]) -> None:
    if by not in allowed:
        raise LedgerError("invalid_by", f"by={by!r}; one of {', '.join(allowed)}")


def _member_names(ids: Iterable[int]) -> dict[int, str]:
    return dict(Member.objects.filter(pk__in=list(ids)).values_list("id", "display_name"))


def _category_names(ids: Iterable[int], level: int) -> dict[int, str]:
    rows = Category.objects.filter(pk__in=list(ids)).select_related("parent")
    if level == 1:
        return {c.id: c.name for c in rows}
    return {c.id: f"{c.parent.name} › {c.name}" if c.parent else c.name for c in rows}


def _by_cents(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda r: (-r["cents"], r["key"]))


def _member_rows(totals: Mapping[int, int]) -> list[Row]:
    names = _member_names(totals)
    return [{"key": str(m), "label": names[m], "cents": totals[m]} for m in sorted(totals)]


def _category_rows(
    totals: Mapping[Any, int], level: int, trip_names: Mapping[int, str]
) -> list[Row]:
    names = _category_names((k for k in totals if isinstance(k, int)), level)
    rows = []
    for key, cents in totals.items():
        if isinstance(key, tuple):  # ("trip", group_id): a trip line in Home `lines` mode
            rows.append({"key": f"trip:{key[1]}", "label": trip_names[key[1]], "cents": cents})
        else:
            rows.append({"key": str(key), "label": names[key], "cents": cents})
    return _by_cents(rows)


def _month_rows(totals: Mapping[str, int]) -> list[Row]:
    return [{"key": m, "label": m, "cents": totals[m]} for m in sorted(totals)]


def _nested_rows(totals: Mapping[int, Mapping[int, int]], level: int) -> list[Row]:
    members = _member_names(totals)
    categories = _category_names({c for inner in totals.values() for c in inner}, level)
    rows = []
    for member_id in sorted(totals):
        inner = _by_cents(
            [
                {"key": str(c), "label": categories[c], "cents": cents}
                for c, cents in totals[member_id].items()
            ]
        )
        rows.append(
            {
                "key": str(member_id),
                "label": members[member_id],
                "cents": sum(r["cents"] for r in inner),
                "rows": inner,
            }
        )
    return rows


def _report(group: Group, date_from: datetime.date, date_to: datetime.date, rows: list[Row]):
    return {"currency": group.currency, "from": date_from, "to": date_to, "rows": rows}


def group_report(
    group: Group, date_from: datetime.date, date_to: datetime.date, by: str, level: int = 1
) -> dict:
    _check_by(by, BY)
    check_range(date_from, date_to)
    if by == "member":
        rows = _member_rows(analytics.spending_by_member(group, date_from, date_to))
    elif by == "category":
        totals = analytics.spending_by_category(group, date_from, date_to, level=level)
        rows = _category_rows(totals, level, {})
    elif by == "month":
        rows = _month_rows(analytics.spending_by_month(group, date_from, date_to))
    else:
        totals = analytics.spending_by_member_and_category(group, date_from, date_to, level=level)
        rows = _nested_rows(totals, level)
    return _report(group, date_from, date_to, rows)


def home_report(
    main_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    by: str,
    trips: str = "lines",
    level: int = 1,
) -> dict:
    _check_by(by, HOME_BY)
    check_range(date_from, date_to)
    if by == "member":
        rows = _member_rows(home.home_spending_by_member(main_group, date_from, date_to, trips))
    elif by == "category":
        totals = home.home_spending_by_category(main_group, date_from, date_to, trips, level)
        trip_names = (
            {t.group_id: t.name for t in home.linked_trips(main_group)} if trips == "lines" else {}
        )
        rows = _category_rows(totals, level, trip_names)
    else:
        rows = _month_rows(home.home_spending_by_month(main_group, date_from, date_to, trips))
    return _report(main_group, date_from, date_to, rows)


def trip_report(
    main_group: Group,
    trip_group: Group,
    date_from: datetime.date,
    date_to: datetime.date,
    level: int = 1,
) -> dict:
    check_range(date_from, date_to)
    totals = home.home_trip_breakdown(main_group, trip_group, date_from, date_to, level)
    return _report(main_group, date_from, date_to, _nested_rows(totals, level))
