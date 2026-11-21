import type { ShareSummary } from "../api";
import { shortDate, summaryText } from "./summaryText";

const fixture: ShareSummary = {
  group: { id: 7, name: "Rome trip" },
  currency: "EUR",
  total_spent_cents: 124000,
  per_member: [
    { member_id: 1, display_name: "Alice", paid: 124000, owed_share: 41250, net: 9250 },
    { member_id: 2, display_name: "Bea", paid: 0, owed_share: 8250, net: -8250 },
    { member_id: 3, display_name: "Carl", paid: 0, owed_share: 1000, net: -1000 },
  ],
  transfers: [
    { from_member: 2, to_member: 1, amount_cents: 8250 },
    { from_member: 3, to_member: 1, amount_cents: 1000 },
  ],
  recent_expenses: [
    { id: 12, date: "2026-11-12", description: "Dinner", amount_cents: 6000, paid_by: [1] },
    { id: 11, date: "2026-11-02", description: "Taxi", amount_cents: 2450, paid_by: [1, 3] },
  ],
};

test("test_summary_text_for_three_members_equals_expected_string", () => {
  expect(summaryText(fixture)).toBe(
    [
      "Rome trip — total 1240.00 EUR",
      "",
      "Bea pays Alice 82.50",
      "Carl pays Alice 10.00",
      "",
      "Last expenses:",
      "12 Nov Dinner 60.00 (Alice)",
      "2 Nov Taxi 24.50 (Alice, Carl)",
    ].join("\n"),
  );
});

test("test_summary_text_says_all_settled_when_no_transfers", () => {
  const text = summaryText({ ...fixture, transfers: [] });
  expect(text.split("\n").slice(0, 3)).toEqual(["Rome trip — total 1240.00 EUR", "", "All settled up."]);
});

test("test_summary_text_omits_last_expenses_when_none", () => {
  const text = summaryText({ ...fixture, total_spent_cents: 0, transfers: [], recent_expenses: [] });
  expect(text).toBe("Rome trip — total 0.00 EUR\n\nAll settled up.");
});

test("test_summary_dates_are_locale_free", () => {
  expect(shortDate("2026-11-02")).toBe("2 Nov");
  expect(shortDate("2026-01-31")).toBe("31 Jan");
});
