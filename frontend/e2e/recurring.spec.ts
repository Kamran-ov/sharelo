import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { apiCall, expectNoHorizontalScroll, HOME, loginAsFixtureUser, resetFixture, shot } from "./helpers";

test.beforeEach(() => resetFixture());

const snap = (page: Page, info: TestInfo, suffix = "") => shot(page, info, "014", suffix);
const row = (page: Page) => page.getByTestId("rule-row");
const sheet = (page: Page) => page.getByRole("dialog", { name: "New recurring expense" });

const pad = (n: number) => String(n).padStart(2, "0");
/** The 1st of the month `ahead` months after the browser's current one: never today, so the result cannot depend on the clock's day or timezone. */
function firstOfMonth(ahead: number): string {
  const now = new Date();
  const index = now.getFullYear() * 12 + now.getMonth() + ahead;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}-01`;
}
const START = firstOfMonth(1);
const SECOND = firstOfMonth(2);
const THIRD = firstOfMonth(3);

async function openRecurring(page: Page) {
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/recurring`);
  await expect(page.getByLabel("Add recurring expense")).toBeEnabled();
}

/** "Rent 950 monthly on 1" paid by Alice, 50/50, starting on START. */
async function createRent(page: Page) {
  await page.getByLabel("Add recurring expense").click();
  await sheet(page).getByLabel(/Amount/).fill("950");
  await sheet(page).getByLabel("Description").fill("Rent");
  await sheet(page).getByLabel("Day of month").fill("1");
  await sheet(page).getByLabel("Start date").fill(START);
}

test("test_skip_next_advances_next_date_by_one_month", async ({ page }, testInfo) => {
  await openRecurring(page);
  await createRent(page);
  await expect(sheet(page).getByTestId("preview")).toHaveText(`Next: ${START}, ${SECOND}, ${THIRD}`);
  await snap(page, testInfo, "-sheet");
  await sheet(page).getByRole("button", { name: "Save" }).click();
  await expect(row(page)).toHaveCount(1);
  await expect(row(page)).toContainText("monthly on the 1st");
  await expect(row(page).getByTestId("next-date")).toHaveText(START);
  await row(page).getByRole("button", { name: "Skip next" }).click();
  await expect(page.getByRole("alertdialog", { name: "Confirm skip" })).toContainText(`Skip ${START}?`);
  await page.getByRole("button", { name: "Skip it" }).click();
  await expect(row(page).getByTestId("next-date")).toHaveText(SECOND);
  await snap(page, testInfo);
});

test("test_skip_on_paused_rule_shows_api_error_inline", async ({ page }, testInfo) => {
  await openRecurring(page);
  await createRent(page);
  await sheet(page).getByRole("button", { name: "Save" }).click();
  await row(page).getByRole("button", { name: "Pause" }).click();
  await expect(row(page).getByText("Paused")).toBeVisible();
  await row(page).getByRole("button", { name: "Skip next" }).click();
  const answered = page.waitForResponse((r) => r.url().endsWith("/skip") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Skip it" }).click();
  const response = await answered;
  expect(response.status()).toBe(400);
  const detail = ((await response.json()) as { detail: string }).detail;
  expect(detail).not.toBe("");
  await expect(row(page).getByRole("alert")).toHaveText(detail);
  await expect(row(page).getByTestId("next-date")).toHaveText(START);
  await snap(page, testInfo);
  await row(page).getByRole("button", { name: "Resume" }).click();
  await expect(row(page).getByText("Paused")).toHaveCount(0);
});

test("test_run_daily_expense_shows_repeat_icon_and_next_date_moves", async ({ page }, testInfo) => {
  resetFixture("--with-recurring-run");
  await loginAsFixtureUser(page);
  const rules = (await apiCall(page, "GET", `/groups/${HOME}/recurring/`)) as { id: number }[];
  await page.goto(`/g/${HOME}/expenses`);
  const expense = page.getByTestId("expense-row").filter({ hasText: "Rent" });
  await expect(expense).toHaveCount(1);
  await expect(expense).toContainText("950.00");
  await snap(page, testInfo, "-list");
  await expense.getByLabel("Created by a recurring rule").click();
  await expect(page).toHaveURL(new RegExp(`/g/${HOME}/recurring#rule-${rules[0].id}$`));
  await expect(page.locator(`#rule-${rules[0].id}`)).toHaveAttribute("data-highlight", "true");
  await expect(page.locator(`#rule-${rules[0].id}`).getByTestId("next-date")).toHaveText("2026-02-01");
  await snap(page, testInfo);
});

test("test_edit_amount_keeps_existing_expense_amount", async ({ page }, testInfo) => {
  resetFixture("--with-recurring-run");
  await loginAsFixtureUser(page);
  const before = (await apiCall(page, "GET", `/groups/${HOME}/expenses/`)) as { results: { id: number; amount_cents: number }[] };
  expect(before.results).toHaveLength(1);
  const expenseId = before.results[0].id;
  await page.goto(`/g/${HOME}/expenses`);
  await expect(page.getByTestId("expense-row")).toContainText("950.00");
  await page.goto(`/g/${HOME}/recurring`);
  await expect(row(page).getByTestId("rule-amount")).toHaveText("950.00");
  await row(page).getByRole("button", { name: "Edit" }).click();
  await page.getByRole("dialog", { name: "Edit recurring expense" }).getByLabel(/Amount/).fill("1000");
  await page.getByRole("dialog", { name: "Edit recurring expense" }).getByRole("button", { name: "Save" }).click();
  await expect(row(page).getByTestId("rule-amount")).toHaveText("1000.00");
  await snap(page, testInfo, "-rule");
  await page.goto(`/g/${HOME}/expenses`);
  await expect(page.getByTestId("expense-row")).toContainText("950.00");
  const after = (await apiCall(page, "GET", `/groups/${HOME}/expenses/`)) as { results: { id: number; amount_cents: number }[] };
  expect(after.results.map((e) => [e.id, e.amount_cents])).toEqual([[expenseId, 95000]]);
  await snap(page, testInfo);
});

test("test_settings_shows_last_run", async ({ page }, testInfo) => {
  resetFixture("--with-recurring-run");
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/settings`);
  await expect(page.getByTestId("recurring-status")).toHaveText("Recurring expenses are created by the daily job; last run: 2026-01-15");
  await snap(page, testInfo);
});

test("test_no_horizontal_scroll_on_recurring_and_sheet_at_390", async ({ page }, testInfo) => {
  resetFixture("--with-recurring-run");
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/recurring`);
  await expect(row(page)).toHaveCount(1);
  await expectNoHorizontalScroll(page);
  await row(page).getByRole("button", { name: "Skip next" }).click();
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo, "-confirm");
  await page.getByRole("button", { name: "Keep" }).click();
  await page.getByLabel("Add recurring expense").click();
  await page.getByRole("button", { name: "Yearly" }).click();
  await expect(sheet(page).getByTestId("preview")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo, "-sheet");
});
