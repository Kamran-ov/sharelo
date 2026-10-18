import { expect, test, type Browser, type Page, type TestInfo } from "@playwright/test";

import {
  apiCall,
  expectNoHorizontalScroll,
  HOME,
  loginAs,
  loginAsFixtureUser,
  owes,
  resetFixture,
  ROME_TOKEN,
  romeMembers,
  seedExpense,
  shot,
} from "./helpers";

test.beforeEach(() => resetFixture());

const snap = (page: Page, info: TestInfo) => shot(page, info, "013");
const card = (page: Page) => page.getByTestId("top-card");
const transfer = (page: Page) => page.getByTestId("transfer");
const sheet = (page: Page, name: string) => page.getByRole("dialog", { name });

/** Alice lent Bea 21.05: a 42.10 expense split 50/50 in Home. */
async function aliceLent(page: Page) {
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/balances`);
}

/** Bea owes Alice 200.00 in Rome trip; Bea is logged in afterwards. Alice has to join first. */
/** Gus opens the invite link in his own browser context and picks a name (a guest has no profile). */
async function guestJoinsRome(browser: Browser, name: string) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const guest = await context.newPage();
  await guest.goto(`/join/${ROME_TOKEN}`);
  await guest.getByLabel("Your name").fill(name);
  await guest.getByRole("button", { name: "Join" }).click();
  await expect(guest).toHaveURL(/\/g\/\d+\/expenses$/);
  await context.close();
}

async function beaOwesAliceInRome(page: Page) {
  await loginAsFixtureUser(page);
  await apiCall(page, "POST", `/join/${ROME_TOKEN}/`, { display_name: "Alice" });
  await loginAs(page, "b@example.com");
  const rome = await romeMembers(page);
  await owes(page, rome.id, rome.byName.Bea, rome.byName.Alice, 20000);
  return rome;
}

test("test_settle_prefilled_amount_clears_the_balance", async ({ page }, testInfo) => {
  await aliceLent(page);
  await expect(card(page)).toHaveText("you are owed 21.05");
  await expect(transfer(page)).toHaveCount(1);
  await expect(transfer(page)).toContainText("Bea pays Alice 21.05");
  await transfer(page).getByRole("button", { name: "Settle" }).click();
  await expect(sheet(page, "Settle up").getByLabel(/Amount/)).toHaveValue("21.05");
  await sheet(page, "Settle up").getByRole("button", { name: "Settle" }).click();
  await expect(card(page)).toHaveText("all settled");
  await page.getByText("History").click();
  await expect(page.getByTestId("history-row")).toHaveCount(1);
  await snap(page, testInfo);
});

test("test_settle_zero_shows_api_error_and_creates_nothing", async ({ page }, testInfo) => {
  await aliceLent(page);
  await transfer(page).getByRole("button", { name: "Settle" }).click();
  await sheet(page, "Settle up").getByLabel(/Amount/).fill("0.00");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/api/groups/${HOME}/settlements/`) && r.request().method() === "POST"),
    sheet(page, "Settle up").getByRole("button", { name: "Settle" }).click(),
  ]);
  expect(response.status()).toBe(400);
  const { detail } = (await response.json()) as { detail: string };
  await expect(sheet(page, "Settle up").getByRole("alert")).toHaveText(detail);
  expect(await apiCall(page, "GET", `/groups/${HOME}/settlements/`)).toEqual([]);
  await sheet(page, "Settle up").getByLabel("Close").click();
  await expect(card(page)).toHaveText("you are owed 21.05");
  await snap(page, testInfo);
});

test("test_undo_after_settle_restores_the_previous_balances", async ({ page }, testInfo) => {
  await aliceLent(page);
  await transfer(page).getByRole("button", { name: "Settle" }).click();
  await sheet(page, "Settle up").getByRole("button", { name: "Settle" }).click();
  await expect(card(page)).toHaveText("all settled");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(card(page)).toHaveText("you are owed 21.05");
  await expect(transfer(page)).toContainText("Bea pays Alice 21.05");
  expect(await apiCall(page, "GET", `/groups/${HOME}/settlements/`)).toEqual([]);
  await snap(page, testInfo);
});

test("test_move_to_home_from_trip_settles_trip_and_mirrors_in_home", async ({ page }, testInfo) => {
  const rome = await beaOwesAliceInRome(page);
  await page.goto(`/g/${rome.id}/balances`);
  await expect(transfer(page)).toContainText("Bea pays Alice 200.00");
  await transfer(page).getByRole("button", { name: "Move to Home" }).click();
  const move = sheet(page, "Move to Home");
  await expect(move.getByRole("listitem").nth(0)).toHaveText("In Rome trip: Bea pays Alice 200.00 — settles the trip");
  await expect(move.getByRole("listitem").nth(1)).toHaveText("In Home: Bea owes Alice 200.00");
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo);
  await move.getByRole("button", { name: "Move to Home" }).click();
  await expect(card(page)).toHaveText("all settled");
  await page.getByText("History").click();
  await expect(page.getByTestId("move-badge")).toHaveText("Rome trip: moved to Home");

  await page.goto(`/g/${HOME}/balances`);
  await expect(card(page)).toHaveText("you owe 200.00");
  await expect(page.getByTestId("member-row").filter({ hasText: "Alice" })).toContainText("is owed 200.00");
  await page.getByText("History").click();
  await expect(page.getByTestId("move-badge")).toHaveText("Rome trip: moved to Home");
});

test("test_move_to_home_button_absent_when_creditor_is_a_guest", async ({ page, browser }, testInfo) => {
  await loginAsFixtureUser(page);
  await loginAs(page, "b@example.com");
  await guestJoinsRome(browser, "Gus");
  const rome = await romeMembers(page);
  await owes(page, rome.id, rome.byName.Bea, rome.byName.Gus, 1000);
  await page.goto(`/g/${rome.id}/balances`);
  await expect(transfer(page)).toContainText("Bea pays Gus 10.00");
  await expect(transfer(page).getByRole("button", { name: "Settle" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Move to Home" })).toHaveCount(0);
  await snap(page, testInfo);
});

test("test_move_to_home_button_absent_when_the_guest_is_the_debtor", async ({ page, browser }, testInfo) => {
  await loginAs(page, "b@example.com");
  await guestJoinsRome(browser, "Gus");
  const rome = await romeMembers(page);
  await owes(page, rome.id, rome.byName.Gus, rome.byName.Bea, 1000);
  await page.goto(`/g/${rome.id}/balances`);
  await expect(transfer(page)).toContainText("Gus pays Bea 10.00");
  await expect(page.getByRole("button", { name: "Move to Home" })).toHaveCount(0);
  await snap(page, testInfo);
});

test("test_move_to_home_button_absent_in_main_group", async ({ page }, testInfo) => {
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await loginAs(page, "b@example.com");
  await page.goto(`/g/${HOME}/balances`);
  await expect(card(page)).toHaveText("you owe 21.05");
  await expect(transfer(page).getByRole("button", { name: "Settle" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Move to Home" })).toHaveCount(0);
  await snap(page, testInfo);
});

test("test_no_horizontal_scroll_on_balances_and_settle_sheet_at_390", async ({ page }, testInfo) => {
  await aliceLent(page);
  await expect(card(page)).toBeVisible();
  await expectNoHorizontalScroll(page);
  await transfer(page).getByRole("button", { name: "Settle" }).click();
  await expect(sheet(page, "Settle up")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo);
});
