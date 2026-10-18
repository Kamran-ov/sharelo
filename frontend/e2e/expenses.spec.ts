import { expect, test } from "@playwright/test";

import {
  apiCall,
  balances,
  categoryId,
  expectNoHorizontalScroll,
  generalCategoryId,
  HOME,
  openExpenses,
  quickAdd,
  resetFixture,
  seedExpense,
  shot,
  today,
} from "./helpers";

test.beforeEach(() => resetFixture());

const snap = (page: import("@playwright/test").Page, info: import("@playwright/test").TestInfo) => shot(page, info, "012");
const rowOf = (page: import("@playwright/test").Page, text: string) => page.getByTestId("expense-row").filter({ hasText: text });

test("test_two_field_expense_pizza_split_half_and_balances_b_owes_2105", async ({ page }, testInfo) => {
  await openExpenses(page);
  // The three actions of the ticket: amount, description, Save. Nothing else is touched.
  await quickAdd(page, "42.10", "Pizza");
  const row = rowOf(page, "Pizza");
  await expect(row).toContainText("42.10");
  await expect(row).toContainText("you paid");
  await expect(row).toContainText("you lent 21.05");
  expect((await balances(page)).transfers).toEqual([{ from_member: 2, to_member: 1, amount_cents: 2105 }]);
  await snap(page, testInfo);
});

test("test_default_personal_is_honoured_by_the_same_three_actions", async ({ page }, testInfo) => {
  await openExpenses(page);
  const general = await generalCategoryId(page);
  await apiCall(page, "PUT", `/groups/${HOME}/category-defaults/`, { [general]: { preset: "personal", params: {} } });
  await page.reload();
  await expect(page.getByLabel("Add expense")).toBeEnabled();
  await quickAdd(page, "42.10", "Pizza");
  await expect(rowOf(page, "Pizza")).toContainText("personal");
  expect((await balances(page)).transfers).toEqual([]);
  await snap(page, testInfo);
});

test("test_default_removed_falls_back_to_half", async ({ page }, testInfo) => {
  await openExpenses(page);
  await apiCall(page, "PUT", `/groups/${HOME}/category-defaults/`, {});
  await page.reload();
  await expect(page.getByLabel("Add expense")).toBeEnabled();
  await quickAdd(page, "42.10", "Pizza");
  await expect(rowOf(page, "Pizza")).toContainText("you lent 21.05");
  expect((await balances(page)).transfers).toEqual([{ from_member: 2, to_member: 1, amount_cents: 2105 }]);
  await snap(page, testInfo);
});

test("test_only_me_shows_personal_and_leaves_balances_unchanged", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("30");
  await page.getByLabel("Description").fill("Haircut");
  await page.getByRole("button", { name: "Only me" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(rowOf(page, "Haircut")).toContainText("personal");
  expect((await balances(page)).transfers).toEqual([]);
  await snap(page, testInfo);
});

test("test_all_other_makes_b_owe_the_full_amount", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("20");
  await page.getByLabel("Description").fill("Bea's ticket");
  await page.getByRole("button", { name: "All Bea" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(rowOf(page, "Bea's ticket")).toContainText("you lent 20.00");
  expect((await balances(page)).transfers).toEqual([{ from_member: 2, to_member: 1, amount_cents: 2000 }]);
  await snap(page, testInfo);
});

test("test_custom_70_percent_shows_70_30_in_edit_sheet", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("100");
  await page.getByLabel("Description").fill("Groceries run");
  await page.getByRole("button", { name: "Custom %" }).click();
  await page.getByLabel("Payer's percent").fill("70");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(rowOf(page, "Groceries run")).toContainText("you lent 30.00");
  await rowOf(page, "Groceries run").click();
  const sheet = page.getByRole("dialog", { name: "Edit expense" });
  await expect(sheet.getByLabel("Payer's percent")).toHaveValue("70");
  await expect(sheet).toContainText("Me 70% · Bea 30%");
  await snap(page, testInfo);
});

test("test_edit_amount_updates_month_total", async ({ page }, testInfo) => {
  await openExpenses(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.reload();
  const month = today().slice(0, 7);
  await expect(page.getByTestId(`month-total-${month}`)).toContainText("42.10");
  await rowOf(page, "Pizza").click();
  await page.getByLabel(/Amount/).fill("50");
  await page.getByRole("dialog", { name: "Edit expense" }).getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId(`month-total-${month}`)).toContainText("50.00");
  await expect(rowOf(page, "Pizza")).toContainText("50.00");
  await snap(page, testInfo);
});

test("test_delete_removes_row_after_confirm", async ({ page }, testInfo) => {
  await openExpenses(page);
  await seedExpense(page, { description: "Pizza" });
  await page.reload();
  await rowOf(page, "Pizza").click();
  await page.getByRole("button", { name: "Delete" }).click();
  await snap(page, testInfo);
  await page.getByRole("button", { name: "Delete for good" }).click();
  await expect(rowOf(page, "Pizza")).toHaveCount(0);
});

test("test_undo_after_save_removes_row_and_balance_change", async ({ page }, testInfo) => {
  await openExpenses(page);
  await quickAdd(page, "42.10", "Pizza");
  await expect(rowOf(page, "Pizza")).toContainText("you lent 21.05");
  expect((await balances(page)).transfers).toHaveLength(1);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(rowOf(page, "Pizza")).toHaveCount(0);
  expect((await balances(page)).transfers).toEqual([]);
  await snap(page, testInfo);
});

test("test_foreign_usd_shows_converted_eur_in_row", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("100");
  await page.getByLabel("Description").fill("Hotel");
  await page.getByText("Advanced").click();
  await page.getByLabel("Currency").selectOption("USD");
  await expect(page.getByTestId("converted")).toContainText("≈ 90.91 EUR");
  await page.getByRole("button", { name: "Save" }).click();
  const row = rowOf(page, "Hotel");
  await expect(row).toContainText("90.91");
  await expect(row).toContainText("100.00 USD");
  await snap(page, testInfo);
});

test("test_gbp_without_rate_disables_save_until_manual_rate", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("10");
  await page.getByLabel("Description").fill("Tea");
  await page.getByText("Advanced").click();
  await page.getByLabel("Currency").selectOption("GBP");
  await expect(page.getByRole("alert")).toContainText("No rate for GBP");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await snap(page, testInfo);
  await page.getByLabel("Manual rate").fill("1.17");
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(rowOf(page, "Tea")).toContainText("11.70");
});

test("test_no_horizontal_scroll_in_list_and_sheet_at_390", async ({ page }, testInfo) => {
  await openExpenses(page);
  await seedExpense(page, { description: "A very long description ".repeat(6).trim() });
  await page.reload();
  await expect(rowOf(page, "A very long")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).focus();
  await expectNoHorizontalScroll(page);
  // Playwright cannot raise the soft keyboard; a short viewport stands in for it.
  await page.setViewportSize({ width: 390, height: 500 });
  await page.getByText("Advanced").click();
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo);
});

test("test_default_split_per_category_setting_prefills_the_sheet", async ({ page }, testInfo) => {
  await openExpenses(page);
  await page.goto(`/g/${HOME}/settings`);
  await page.getByLabel("Default split for Food and drink › Groceries").selectOption("personal");
  await expect(page.getByTestId(`default-${await categoryId(page, "Groceries")}`)).toContainText("Saved");
  await page.goto(`/g/${HOME}/expenses`);
  await expect(page.getByLabel("Add expense")).toBeEnabled();
  await page.getByLabel("Add expense").click();
  await page.getByRole("button", { name: /Uncategorized › General/ }).click();
  await page.getByRole("tab", { name: "Food and drink" }).click();
  await page.getByRole("option", { name: "Groceries" }).click();
  await expect(page.getByRole("button", { name: "Only me" })).toHaveAttribute("aria-pressed", "true");
  await snap(page, testInfo);
});

test("test_load_more_appends_older_expenses", async ({ page }, testInfo) => {
  await openExpenses(page);
  for (let i = 0; i < 55; i++) await seedExpense(page, { description: `Item ${i}`, amount_cents: 100 });
  await page.reload();
  await expect(page.getByTestId("expense-row")).toHaveCount(50);
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(page.getByTestId("expense-row")).toHaveCount(55);
  await expect(page.getByRole("button", { name: "Load more" })).toHaveCount(0);
  await snap(page, testInfo);
});
