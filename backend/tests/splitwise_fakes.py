"""A stand-in for `SplitwiseClient` that serves the recorded fixture; no network."""

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "splitwise"
SW_GROUP_ID = 555
ALICE, BEA, CARL = 101, 102, 103


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(), parse_float=str)


def fixture_expenses() -> list[dict]:
    return load("expenses_page1.json")["expenses"] + load("expenses_page2.json")["expenses"]


class FakeClient:
    def __init__(self, extra_expenses: list[dict] | None = None, group: dict | None = None):
        self.expenses = fixture_expenses() + list(extra_expenses or [])
        self.group = group or load("group.json")["group"]

    def get_current_user(self) -> dict:
        return load("current_user.json")["user"]

    def get_group(self, group_id: int) -> dict:
        assert group_id == SW_GROUP_ID
        return copy.deepcopy(self.group)

    def get_categories(self) -> list[dict]:
        return load("categories.json")["categories"]

    def get_expenses(self, group_id: int) -> list[dict]:
        assert group_id == SW_GROUP_ID
        return copy.deepcopy(self.expenses)


def sw_user(user_id: int, paid: str, owed: str) -> dict:
    names = {ALICE: "Alice", BEA: "Bea", CARL: "Carl"}
    return {
        "user": {"id": user_id, "first_name": names.get(user_id, "Dan"), "last_name": "X"},
        "user_id": user_id,
        "paid_share": paid,
        "owed_share": owed,
    }


def sw_expense(sw_id: int, cost: str, users: list[dict], **kw) -> dict:
    row = {
        "id": sw_id,
        "description": kw.pop("description", f"expense {sw_id}"),
        "details": None,
        "payment": False,
        "cost": cost,
        "currency_code": "EUR",
        "date": "2021-07-01T12:00:00Z",
        "deleted_at": None,
        "category": {"id": 12, "name": "Groceries"},
        "users": users,
    }
    row.update(kw)
    return row
