import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

import {
  apiCall,
  expectNoHorizontalScroll,
  generalCategoryId,
  HOME,
  loginAs,
  loginAsFixtureUser,
  quickAdd,
  resetFixture,
  seedExpense,
  today,
} from "./helpers";

const snap = (page: Page, info: TestInfo, suffix = "") =>
  page.screenshot({ path: path.resolve(process.cwd(), `../docs/screenshots/018/${info.title}${suffix}.png`) });
const shareSheet = (page: Page) => page.getByRole("dialog", { name: "Share summary" });

test.beforeEach(() => resetFixture());

// Independent of the app's own date helper on purpose: a bug there must not hide here.
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayMon(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MON[m - 1]}`;
}

/** Records every navigator.share({text}) in sessionStorage (survives navigations) instead of an OS sheet. */
async function stubWebShare(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, "share", {
      configurable: true,
      value: async (data: { text?: string }) => {
        const seen = JSON.parse(sessionStorage.getItem("e2e-shared") ?? "[]") as string[];
        sessionStorage.setItem("e2e-shared", JSON.stringify([...seen, data.text ?? ""]));
      },
    });
  });
}

async function removeWebShare(page: Page) {
  await page.addInitScript(() => {
    delete (Navigator.prototype as unknown as Record<string, unknown>).share;
    delete (Navigator.prototype as unknown as Record<string, unknown>).canShare;
  });
}

async function openShare(page: Page) {
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(shareSheet(page).getByRole("button", { name: "Share as text" })).toBeEnabled();
}

const shared = (page: Page) => page.evaluate(() => JSON.parse(sessionStorage.getItem("e2e-shared") ?? "[]") as string[]);

test("share text with Web Share stubbed captures the summary", async ({ page }, testInfo) => {
  await stubWebShare(page);
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/balances`);
  await openShare(page);
  await snap(page, testInfo);
  await shareSheet(page).getByRole("button", { name: "Share as text" }).click();
  await expect.poll(() => shared(page)).toHaveLength(1);
  expect((await shared(page))[0]).toBe(
    `Home — total 42.10 EUR\n\nBea pays Alice 21.05\n\nLast expenses:\n${dayMon(today())} Pizza 42.10 (Alice)`,
  );
});

test("share after adding an expense sends the new total", async ({ page }, testInfo) => {
  await stubWebShare(page);
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/balances`);
  await openShare(page);
  await shareSheet(page).getByRole("button", { name: "Share as text" }).click();
  await expect.poll(() => shared(page)).toHaveLength(1);
  expect((await shared(page))[0].split("\n")[0]).toBe("Home — total 42.10 EUR");
  await shareSheet(page).getByRole("button", { name: "Close" }).click();

  await page.goto(`/g/${HOME}/expenses`);
  await expect(page.getByLabel("Add expense")).toBeEnabled();
  await quickAdd(page, "10", "Coffee");
  await expect.poll(async () => ((await apiCall(page, "GET", `/groups/${HOME}/expenses/`)) as { count: number }).count).toBe(2);

  await page.getByRole("link", { name: "Balances" }).click();
  await openShare(page);
  await shareSheet(page).getByRole("button", { name: "Share as text" }).click();
  await expect.poll(() => shared(page)).toHaveLength(2);
  const lines = (await shared(page))[1].split("\n");
  expect(lines[0]).toBe("Home — total 52.10 EUR");
  expect(lines[lines.indexOf("Last expenses:") + 1]).toBe(`${dayMon(today())} Coffee 10.00 (Alice)`);
  await snap(page, testInfo);
});

test("share text without Web Share puts it on the clipboard", async ({ page }, testInfo) => {
  await removeWebShare(page);
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/balances`);
  await openShare(page);
  await shareSheet(page).getByRole("button", { name: "Share as text" }).click();
  await expect(page.getByRole("status")).toHaveText("Copied to clipboard");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    `Home — total 42.10 EUR\n\nBea pays Alice 21.05\n\nLast expenses:\n${dayMon(today())} Pizza 42.10 (Alice)`,
  );
  await snap(page, testInfo);
});

const LONG_GROUP = "Rome, Florence, Siena and the slow coastal way back up to Milan — summer trip with the cousins 2026";
const LONG_DESCRIPTION =
  "Agriturismo dinner for everyone on the last night, with the extra bottle of Brunello and the cake for Carl's birthday";

test("share image without file sharing downloads a PNG", async ({ page, browser }, testInfo) => {
  expect(LONG_DESCRIPTION.length).toBeGreaterThanOrEqual(115);
  await removeWebShare(page);
  await loginAsFixtureUser(page);
  const trip = (await apiCall(page, "POST", "/groups/", { name: LONG_GROUP, currency: "EUR", as_main: false })) as {
    id: number;
    share_token: string;
  };
  const guest = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const carl = await guest.newPage();
  await carl.goto(`/join/${trip.share_token}`);
  await carl.getByLabel("Your name").fill("Carl");
  await carl.getByRole("button", { name: "Join" }).click();
  await expect(carl).toHaveURL(/\/g\/\d+\/expenses$/);
  await guest.close();
  await loginAs(page, "b@example.com");
  await apiCall(page, "POST", `/join/${trip.share_token}/`, { display_name: "Bea" });
  await loginAs(page, "a@example.com");
  const detail = (await apiCall(page, "GET", `/groups/${trip.id}/`)) as { members: { id: number; display_name: string }[] };
  const id = Object.fromEntries(detail.members.map((m) => [m.display_name, m.id]));
  const category = await generalCategoryId(page);
  const lend = (debtor: string, cents: number, description: string) =>
    apiCall(page, "POST", `/groups/${trip.id}/expenses/`, {
      description,
      amount_cents: cents,
      date: today(),
      category,
      payer_member: id.Alice,
      preset: "full_for_other",
      params: { other_id: id[debtor] },
    });
  await lend("Bea", 8250, "Train tickets");
  await lend("Carl", 1000, "Museum");
  await lend("Carl", 1500, LONG_DESCRIPTION);

  await page.goto(`/g/${trip.id}/balances`);
  await openShare(page);
  const imageButton = shareSheet(page).getByRole("button", { name: "Share as image" });
  await expect(imageButton).toBeEnabled();
  const downloading = page.waitForEvent("download");
  await imageButton.click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(/\.png$/);
  const card = path.resolve(process.cwd(), "../docs/screenshots/018/summary-card.png");
  await download.saveAs(card);
  expect([...readFileSync(card).subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  await expect(page.getByRole("status")).toHaveText("Image downloaded");
  await snap(page, testInfo);
});

test("share sheet has no horizontal scroll at 390", async ({ page }, testInfo) => {
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/balances`);
  await expectNoHorizontalScroll(page);
  await openShare(page);
  await expectNoHorizontalScroll(page);
  await snap(page, testInfo);
});
