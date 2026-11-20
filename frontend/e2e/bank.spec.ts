import path from "node:path";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { expectNoHorizontalScroll, HOME, loginAsFixtureUser, resetFixture, shot } from "./helpers";

test.beforeEach(() => resetFixture());

const snap = (page: Page, info: TestInfo, suffix = "") => shot(page, info, "021", suffix);
const fixture = (name: string) => path.resolve(process.cwd(), "e2e/fixtures", name);
const bankRow = (page: Page, shop: string) => page.getByTestId("bank-row").filter({ hasText: shop });

async function openImport(page: Page, file = "revolut_review.csv") {
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/expenses`);
  await page.getByRole("link", { name: /Import bank file/ }).click();
  await expect(page).toHaveURL(/\/bank-import$/);
  await page.getByLabel(/Revolut or Wise statement/).setInputFiles(fixture(file));
  await expect(page.getByTestId("upload-result")).toBeVisible();
}

/** Esselunga → Groceries, remembered, Shared; Farmacia → Personal; Transfer → Skip. */
async function reviewThree(page: Page, info?: TestInfo) {
  await expect(page.getByTestId("bank-row")).toHaveCount(3);
  for (const shop of ["Esselunga", "Farmacia Centrale", "Transfer to Bea"]) {
    await expect(bankRow(page, shop).getByLabel(`Category for ${shop}`)).toHaveValue(/\d+/);
    await expect(bankRow(page, shop).locator("select option:checked")).toHaveText("General");
  }
  const essel = bankRow(page, "Esselunga");
  await essel.getByLabel("Category for Esselunga").selectOption({ label: "Groceries" });
  await expect(essel.getByTestId("split-label")).toHaveText("50/50");
  await essel.getByLabel("Remember for this shop").check();
  if (info) await snap(page, info, "-before");
  await essel.getByRole("button", { name: "Shared" }).click();
  await expect(essel.getByTestId("result-line")).toHaveText("Shared · Groceries · 50/50");
  await bankRow(page, "Farmacia Centrale").getByRole("button", { name: "Personal" }).click();
  await expect(bankRow(page, "Farmacia Centrale").getByTestId("result-line")).toHaveText("Personal · General");
  await bankRow(page, "Transfer to Bea").getByRole("button", { name: "Skip" }).click();
  await expect(bankRow(page, "Transfer to Bea").getByTestId("result-line")).toHaveText("Skipped");
}

test("test_review_three_rows_with_three_decisions_creates_two_expenses", async ({ page }, testInfo) => {
  await openImport(page);
  await expect(page.getByTestId("upload-result")).toHaveText("3 new, 0 already imported, 0 not money out");
  await reviewThree(page, testInfo);
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo, "-after");

  await page.getByRole("link", { name: "Back to expenses" }).click();
  const rows = page.getByTestId("expense-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Esselunga" })).toContainText("Groceries");
  await expect(rows.filter({ hasText: "Esselunga" })).toContainText("45.20");
  await expect(rows.filter({ hasText: "Farmacia Centrale" })).toContainText("personal");
  await expect(page.getByTestId("to-review")).toHaveCount(0);

  await page.goto(`/g/${HOME}/settings`);
  const rule = page.getByTestId("shop-rule");
  await expect(rule).toHaveCount(1);
  await expect(rule).toContainText("Esselunga → Groceries · 50/50");
  await rule.scrollIntoViewIfNeeded();
  await snap(page, testInfo, "-shop-rules");
});

test("test_undo_returns_row_to_pending_and_removes_expense", async ({ page }, testInfo) => {
  await openImport(page);
  const essel = bankRow(page, "Esselunga");
  await essel.getByRole("button", { name: "Shared" }).click();
  await expect(essel.getByTestId("result-line")).toHaveText("Shared · General · 50/50");
  await essel.getByRole("button", { name: "Undo" }).click();
  await expect(essel.getByRole("button", { name: "Shared" })).toBeVisible();
  await snap(page, testInfo);
  await page.getByRole("link", { name: "Back to expenses" }).click();
  await expect(page.getByText("No expenses yet.")).toBeVisible();
  await expect(page.getByTestId("to-review")).toHaveText("3 to review");
});

test("test_remembered_shop_prefills_the_next_upload", async ({ page }, testInfo) => {
  await openImport(page);
  await reviewThree(page);
  await page.getByLabel(/Revolut or Wise statement/).setInputFiles(fixture("revolut_review_next.csv"));
  await expect(page.getByTestId("upload-result")).toHaveText("1 new, 0 already imported, 0 not money out");
  const next = bankRow(page, "ESSELUNGA MILANO");
  await expect(next.locator("select option:checked")).toHaveText("Groceries");
  await expect(next.getByTestId("split-label")).toHaveText("50/50");
  await snap(page, testInfo);
  await next.getByRole("button", { name: "Shared" }).click();
  await expect(next.getByTestId("result-line")).toHaveText("Shared · Groceries · 50/50");
});
