import { describeRule, nextOccurrences, type Schedule } from "./recurrence";
import { ruleBody, rulePatchBody, ruleSplit, splitText, whoOfRule, type RuleValues } from "./ruleBody";

const monthly = (day: number): Schedule => ({ frequency: "monthly", day_of_month: day, month: null });

// Fixtures copied from backend/tests/test_ledger_recurring.py::test_monthly_day_31_clamps_to_month_end
test("test_next_occurrences_match_backend_day31_and_feb29", () => {
  expect(nextOccurrences(monthly(31), "2027-01-31", 4)).toEqual(["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"]);
  expect(nextOccurrences(monthly(31), "2028-01-31", 2)[1]).toBe("2028-02-29");
  // ...and ::test_yearly_feb_29_clamps_in_non_leap_years
  const yearly: Schedule = { frequency: "yearly", day_of_month: 29, month: 2 };
  expect(nextOccurrences(yearly, "2027-01-01", 3)).toEqual(["2027-02-28", "2028-02-29", "2029-02-28"]);
});

test("test_next_occurrences_includes_from_when_it_is_the_rule_day", () => {
  expect(nextOccurrences(monthly(1), "2026-11-01", 3)).toEqual(["2026-11-01", "2026-12-01", "2027-01-01"]);
  expect(nextOccurrences(monthly(1), "2026-11-02", 1)).toEqual(["2026-12-01"]);
});

test("test_next_occurrences_strictly_after_is_what_skip_uses", () => {
  expect(nextOccurrences(monthly(1), "2026-11-01", 1, false)).toEqual(["2026-12-01"]);
  expect(nextOccurrences(monthly(31), "2027-01-31", 1, false)).toEqual(["2027-02-28"]);
});

test("test_next_occurrences_roll_over_december_and_yearly_past_date", () => {
  expect(nextOccurrences(monthly(15), "2026-12-20", 2)).toEqual(["2027-01-15", "2027-02-15"]);
  const yearly: Schedule = { frequency: "yearly", day_of_month: 14, month: 3 };
  expect(nextOccurrences(yearly, "2026-03-15", 2)).toEqual(["2027-03-14", "2028-03-14"]);
});

test("test_describe_rule_wording", () => {
  expect(describeRule(monthly(1))).toBe("monthly on the 1st");
  expect(describeRule(monthly(2))).toBe("monthly on the 2nd");
  expect(describeRule(monthly(3))).toBe("monthly on the 3rd");
  expect(describeRule(monthly(11))).toBe("monthly on the 11th");
  expect(describeRule(monthly(22))).toBe("monthly on the 22nd");
  expect(describeRule({ frequency: "yearly", day_of_month: 14, month: 3 })).toBe("yearly on 14 Mar");
});

const values: RuleValues = {
  amountText: "950",
  description: " Rent ",
  category: 5,
  payerId: 1,
  who: "half",
  percent: 50,
  frequency: "monthly",
  day: 1,
  month: 1,
  startDate: "2026-11-01",
  endDate: "",
};

test("test_rule_body_sends_integer_cents_and_service_split", () => {
  const body = ruleBody(values, [1, 2]);
  expect(body.amount_cents).toBe(95000);
  expect(Number.isInteger(body.amount_cents)).toBe(true);
  expect(body).toMatchObject({ description: "Rent", split_type: "equal", split_params: {}, month: null, end_date: null, payer: 1 });
});

test("test_rule_split_forms", () => {
  expect(ruleSplit("all_other", 1, [1, 2], 50)).toEqual({ split_type: "full_for_other", split_params: { other_id: 2 } });
  expect(ruleSplit("custom", 1, [1, 2], 30)).toEqual({ split_type: "percentage", split_params: { basis_points: { 1: 3000, 2: 7000 } } });
  expect(whoOfRule({ split_type: "percentage", split_params: { basis_points: { 1: 3000, 2: 7000 } }, payer: 1 }, 2)).toEqual({ who: "custom", percent: 30 });
  expect(whoOfRule({ split_type: "exact", split_params: {}, payer: 1 }, 2)).toBeNull();
  expect(splitText({ split_type: "exact", split_params: {}, payer: 1 }, 2)).toBe("custom split");
  expect(splitText({ split_type: "equal", split_params: {}, payer: 1 }, 2)).toBe("50/50");
});

test("test_rule_patch_body_for_amount_edit_does_not_touch_schedule_or_split", () => {
  const patch = rulePatchBody({ ...values, amountText: "1000" }, values, [1, 2]);
  expect(patch).toEqual({ amount_cents: 100000 });
});

test("test_rule_patch_body_restates_split_when_payer_changes", () => {
  const patch = rulePatchBody({ ...values, payerId: 2 }, values, [1, 2]);
  expect(patch).toMatchObject({ payer: 2, split_type: "equal" });
});
