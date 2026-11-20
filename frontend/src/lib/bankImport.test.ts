import { expect, test } from "vitest";

import { resolveBody, resultLine, rowChoice, splitLabel } from "./bankImport";

const ME = 1;
const MEMBERS = [1, 2];
const GROCERIES = 12;
const DINING = 11;
const GENERAL = 21;

// A rule says Groceries 50/50; Dining out's own default is 70/30 for me.
const suggestion = { category: GROCERIES, preset: "equal", params: {} };
const seventyThirty = { basis_points: { "1": 7000, "2": 3000 } };
const categorySplits = {
  [GROCERIES]: { preset: "full_for_other", params: {} }, // differs from the rule on purpose
  [DINING]: { preset: "percentage", params: seventyThirty },
  [GENERAL]: { preset: "equal", params: {} },
};

test("test_changed_category_label_and_body_use_the_server_split", () => {
  const triple = rowChoice(suggestion, categorySplits, DINING)!;
  expect(triple).toEqual({ category: DINING, preset: "percentage", params: seventyThirty });
  expect(splitLabel(triple.preset, triple.params, ME, MEMBERS)).toBe("70/30");
  expect(resolveBody("shared", triple, false)).toEqual({
    decision: "shared",
    category: DINING,
    preset: "percentage",
    params: seventyThirty,
    remember: false,
  });
});

test("test_changing_back_to_suggested_category_restores_the_suggested_split", () => {
  const away = rowChoice(suggestion, categorySplits, DINING)!;
  expect(away.preset).toBe("percentage");
  const back = rowChoice(suggestion, categorySplits, GROCERIES)!;
  // The rule's own split, not categorySplits[Groceries]: same rule as resolve_row step 3.
  expect(back).toEqual({ category: GROCERIES, preset: "equal", params: {} });
  expect(splitLabel(back.preset, back.params, ME, MEMBERS)).toBe("50/50");
  expect(resolveBody("shared", back, true)).toMatchObject({ preset: "equal", params: {}, remember: true });
});

test("test_unchanged_chip_sends_the_suggestion_triple", () => {
  const triple = rowChoice(suggestion, categorySplits)!;
  expect(resolveBody("shared", triple, false)).toEqual({ decision: "shared", category: GROCERIES, preset: "equal", params: {}, remember: false });
});

test("test_category_without_server_split_offers_nothing", () => {
  expect(rowChoice(suggestion, categorySplits, 999)).toBeNull();
});

test("test_remember_is_never_sent_with_skip", () => {
  const triple = rowChoice(suggestion, categorySplits)!;
  expect(resolveBody("skip", triple, true)).toEqual({ decision: "skip" });
  expect(resolveBody("personal", triple, true)).toEqual({ decision: "personal", category: GROCERIES, remember: true });
});

test("test_result_line_per_decision", () => {
  expect(resultLine("shared", "Groceries", "50/50")).toBe("Shared · Groceries · 50/50");
  expect(resultLine("personal", "Groceries", "50/50")).toBe("Personal · Groceries");
  expect(resultLine("skip", "Groceries", "50/50")).toBe("Skipped");
});

test("test_split_label_shapes", () => {
  expect(splitLabel("equal", {}, ME, [1, 2, 3])).toBe("Equal (3)");
  expect(splitLabel("full_for_other", {}, ME, MEMBERS)).toBe("All the other");
  expect(splitLabel("percentage", { basis_points: { "1": 3333, "2": 6667 } }, ME, MEMBERS)).toBe("Custom %");
  expect(splitLabel("shares", {}, ME, MEMBERS)).toBe("Custom");
});
