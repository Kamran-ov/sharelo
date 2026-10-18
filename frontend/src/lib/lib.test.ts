import { buildPatchBody, buildCreateBody, type FormValues } from "./expenseBody";
import { localToday, monthKey } from "./dates";
import { formatCents, parseAmount } from "./money";
import { descriptionSuggestions, detectPreset, orderByUse, shareFor, toApiPreset, whoFromDefault, type Who } from "./presets";

test("test_parse_amount_accepts_comma_dot_and_integer", () => {
  expect(parseAmount("12,50")).toBe(1250);
  expect(parseAmount("12.50")).toBe(1250);
  expect(parseAmount("12")).toBe(1200);
  expect(parseAmount("0.05")).toBe(5);
  expect(parseAmount("100")).toBe(10000);
  expect(parseAmount(".50")).toBe(50);
  expect(parseAmount("  7.5 ")).toBe(750);
});

test("test_parse_amount_rejects_three_decimals_and_junk", () => {
  for (const bad of ["12.345", "", " ", "-3", "0", "0.00", "1,234.50", "12.", "abc", "1e3", "12.5.0"]) {
    expect(parseAmount(bad), bad).toBeNull();
  }
});

test("test_format_cents_is_locale_free_two_decimals", () => {
  expect(formatCents(4210)).toBe("42.10");
  expect(formatCents(5)).toBe("0.05");
  expect(formatCents(123456)).toBe("1234.56");
});

const IDS = [1, 2];
const CASES: [Who, number, object][] = [
  ["half", 1, { preset: "half" }],
  ["half", 2, { preset: "half" }],
  ["personal", 1, { preset: "personal" }],
  ["personal", 2, { preset: "personal" }],
  ["all_other", 1, { preset: "full_for_other", params: { other_id: 2 } }],
  ["all_other", 2, { preset: "full_for_other", params: { other_id: 1 } }],
  ["custom", 1, { preset: "percentage", params: { percent_payer: 70 } }],
  ["custom", 2, { preset: "percentage", params: { percent_payer: 70 } }],
];

test.each(CASES)("test_preset_mapping_is_exhaustive %s paid by member %i", (who, payer, expected) => {
  expect(toApiPreset(who, payer, IDS, 70)).toEqual(expected);
});

test("test_custom_percent_is_always_the_payers_share", () => {
  const body = buildCreateBody(values({ who: "custom", percent: 70, payerId: 2 }), group, null);
  expect(body.payer_member).toBe(2);
  expect(body.params).toEqual({ percent_payer: 70 });
});

const group = { currency: "EUR", members: [{ id: 1 }, { id: 2 }] };
function values(over: Partial<FormValues> = {}): FormValues {
  return {
    amountText: "12,50",
    currency: "EUR",
    manualRate: "",
    description: "Pizza",
    category: 21,
    date: "2026-10-18",
    payerId: 1,
    who: "half",
    percent: 50,
    mode: "none",
    exactTexts: {},
    sharesTexts: {},
    subset: [1, 2],
    ...over,
  };
}

test("test_amount_sent_to_api_is_an_integer", () => {
  const body = buildCreateBody(values(), group, null);
  expect(body.amount_cents).toBe(1250);
  expect(Number.isInteger(body.amount_cents)).toBe(true);
});

test("test_foreign_body_sends_original_amount_and_no_converted_amount", () => {
  const body = buildCreateBody(values({ currency: "USD" }), group, "0.9");
  expect(body).toMatchObject({ original_currency: "USD", original_amount_cents: 1250, rate_used: "0.9" });
  expect(body).not.toHaveProperty("amount_cents");
});

test("test_default_preset_falls_back_to_half_without_category_default", () => {
  expect(whoFromDefault(undefined, 2, 1)).toEqual({ who: "half", percent: 50 });
  expect(whoFromDefault({ preset: "personal" }, 2, 1)).toEqual({ who: "personal", percent: 100 });
  expect(whoFromDefault({ preset: "equal" }, 3, 1)).toEqual({ who: "equal", percent: 50 });
  expect(whoFromDefault({ preset: "full_for_other" }, 3, 1).who).toBe("equal");
  expect(whoFromDefault({ preset: "percentage", params: { basis_points: { 1: 7000, 2: 3000 } } }, 2, 1)).toEqual({ who: "custom", percent: 70 });
  expect(whoFromDefault({ preset: "percentage", params: { basis_points: { 1: 7000, 2: 3000 } } }, 3, 1).who).toBe("equal");
});

test("test_edit_sheet_detects_half_on_odd_cent_total", () => {
  const d = detectPreset(4211, 1, IDS, [{ member: 1, owed_cents: 2106 }, { member: 2, owed_cents: 2105 }]);
  expect(d?.who).toBe("half");
});

test("test_edit_sheet_detects_custom_percent_from_splits", () => {
  const d = detectPreset(4210, 1, IDS, [{ member: 1, owed_cents: 2947 }, { member: 2, owed_cents: 1263 }]);
  expect(d).toEqual({ who: "custom", percent: 70 });
});

test("test_edit_sheet_shows_custom_split_for_exact_amounts", () => {
  expect(detectPreset(4210, 1, IDS, [{ member: 1, owed_cents: 2000 }, { member: 2, owed_cents: 2210 }])).toBeNull();
  expect(detectPreset(4210, 1, IDS, [{ member: 1, owed_cents: 4210 }])?.who).toBe("personal");
  expect(detectPreset(4210, 1, IDS, [{ member: 2, owed_cents: 4210 }])?.who).toBe("all_other");
});

test("test_patch_of_untouched_custom_split_carries_no_preset", () => {
  const initial = values({ who: null, mode: "exact", exactTexts: { 1: "20.00", 2: "22.10" }, amountText: "42.10" });
  expect(buildPatchBody({ ...initial, description: "Renamed" }, initial, group)).not.toHaveProperty("preset");
  const changed = buildPatchBody({ ...initial, amountText: "40.00", exactTexts: { 1: "20.00", 2: "20.00" } }, initial, group);
  expect(changed).toMatchObject({ amount_cents: 4000, preset: "exact", params: { cents: { 1: 2000, 2: 2000 } } });
});

test("test_row_wording_owe_lent_personal_settled", () => {
  const payers = [{ member: 1, paid_cents: 4210 }];
  expect(shareFor(2, payers, [{ member: 1, owed_cents: 2105 }, { member: 2, owed_cents: 2105 }], "equal")).toEqual({ kind: "owe", cents: 2105 });
  expect(shareFor(1, payers, [{ member: 1, owed_cents: 2105 }, { member: 2, owed_cents: 2105 }], "equal")).toEqual({ kind: "lent", cents: 2105 });
  expect(shareFor(1, payers, [{ member: 1, owed_cents: 4210 }], "personal")).toEqual({ kind: "personal" });
  expect(shareFor(1, payers, [{ member: 1, owed_cents: 4210 }], "equal")).toEqual({ kind: "settled" });
  expect(shareFor(3, payers, [{ member: 1, owed_cents: 2105 }, { member: 2, owed_cents: 2105 }], "equal")).toEqual({ kind: "not_involved" });
});

test("test_default_date_is_local_calendar_date", () => {
  const before = process.env.TZ;
  try {
    process.env.TZ = "Europe/Rome";
    expect(localToday(new Date("2026-10-18T23:30:00Z"))).toBe("2026-10-19");
    process.env.TZ = "America/New_York";
    expect(localToday(new Date("2026-10-19T00:30:00Z"))).toBe("2026-10-18");
  } finally {
    process.env.TZ = before;
  }
});

test("test_month_header_groups_on_date_string", () => {
  const before = process.env.TZ;
  try {
    process.env.TZ = "Pacific/Auckland";
    expect(monthKey("2026-10-31")).toBe("2026-10");
    expect(monthKey("2026-11-01")).toBe("2026-11");
  } finally {
    process.env.TZ = before;
  }
});

test("test_description_suggestions_are_distinct_latest_with_their_category", () => {
  const rows = [
    { description: "Pizza", category: 11 },
    { description: "pizza", category: 12 },
    { description: "Rent", category: 30 },
  ];
  expect(descriptionSuggestions(rows)).toEqual([
    { description: "Pizza", category: 11 },
    { description: "Rent", category: 30 },
  ]);
  const many = Array.from({ length: 30 }, (_, i) => ({ description: `d${i}`, category: 1 }));
  expect(descriptionSuggestions(many)).toHaveLength(20);
});

test("test_order_by_use_then_seed_order", () => {
  const kids = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];
  expect(orderByUse(kids, new Map([[3, 5], [2, 1]])).map((k) => k.id)).toEqual([3, 2, 1, 4]);
});
