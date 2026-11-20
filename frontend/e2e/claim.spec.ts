import { expect, test, type Browser, type Page } from "@playwright/test";

import { apiCall, expectNoHorizontalScroll, loginAsFixtureUser, resetFixture, shot } from "./helpers";

test.beforeEach(() => resetFixture());

/** Alice creates "Flat", adds Janet and Cami in Settings and a 30.00 equal expense among 3. */
async function flatWithPlaceholders(page: Page, screenshot?: () => Promise<void>) {
  await loginAsFixtureUser(page);
  await page.getByRole("button", { name: "New group" }).click();
  await page.getByLabel("Name").fill("Flat");
  await page.getByRole("button", { name: "Create group" }).click();
  await page.getByRole("link", { name: /Flat/ }).click();
  await page.getByRole("link", { name: "Settings" }).click();
  for (const name of ["Janet", "Cami"]) {
    await page.getByLabel("Add person").fill(name);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText(`${name} · not joined yet`)).toBeVisible();
  }
  if (screenshot) await screenshot();
  await page.getByRole("link", { name: "Expenses" }).click();
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill("30");
  await page.getByLabel("Description").fill("Groceries");
  const choose = page.getByRole("button", { name: "Choose…" });
  if (await choose.isVisible()) {
    await choose.click();
    await page.getByRole("button", { name: /Uncategorized › General/ }).click();
  }
  await page.getByRole("button", { name: "Equal among everyone" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Groceries").first()).toBeVisible();
  const groups = (await apiCall(page, "GET", "/groups/")) as { id: number; name: string }[];
  const flat = groups.find((g) => g.name === "Flat")!;
  const detail = (await apiCall(page, "GET", `/groups/${flat.id}/`)) as {
    share_token: string;
    members: { id: number; display_name: string }[];
  };
  const ids = Object.fromEntries(detail.members.map((m) => [m.display_name, m.id])) as Record<string, number>;
  return { id: flat.id, token: detail.share_token, ids };
}

async function freshPage(browser: Browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  return context.newPage();
}

async function claimAs(page: Page, token: string, name: string) {
  await page.goto(`/join/${token}`);
  await expect(page.getByRole("heading", { name: "Are you one of these?" })).toBeVisible();
  await page.getByRole("button", { name, exact: true }).click();
  await expect(page).toHaveURL(/\/g\/\d+\/expenses$/);
}

test("test_add_person_and_split_before_they_join", async ({ page }, testInfo) => {
  const flat = await flatWithPlaceholders(page, () => shot(page, testInfo, "017", "-add-person"));
  await page.getByRole("link", { name: "Balances" }).click();
  const rows = page.getByTestId("member-row");
  await expect(rows.filter({ hasText: "Janet" })).toContainText("owes 10.00");
  await expect(rows.filter({ hasText: "Cami" })).toContainText("owes 10.00");
  await expect(rows.filter({ hasText: "Alice" })).toContainText("is owed 20.00");
  expect(Object.keys(flat.ids).sort()).toEqual(["Alice", "Cami", "Janet"]);
  await shot(page, testInfo, "017");
});

test("test_fresh_browser_claims_janet_and_second_browser_no_longer_sees_her", async ({ page, browser }, testInfo) => {
  const flat = await flatWithPlaceholders(page);
  const b = await freshPage(browser);
  await b.goto(`/join/${flat.token}`);
  await expect(b.getByRole("button", { name: "Janet", exact: true })).toBeVisible();
  await expect(b.getByRole("button", { name: "Cami", exact: true })).toBeVisible();
  await shot(b, testInfo, "017", "-join-list");
  await b.getByRole("button", { name: "Janet", exact: true }).click();
  await expect(b).toHaveURL(new RegExp(`/g/${flat.id}/expenses$`));
  await expect(b.getByText("Groceries").first()).toBeVisible();
  await b.getByRole("link", { name: "Settings" }).click();
  await expect(b.getByTestId(`member-${flat.ids.Janet}`)).toHaveText("Janet (you) · guest");
  await shot(b, testInfo, "017", "-claimed");

  const c = await freshPage(browser);
  await c.goto(`/join/${flat.token}`);
  await expect(c.getByRole("button", { name: "Cami", exact: true })).toBeVisible();
  await expect(c.getByRole("button", { name: "Janet", exact: true })).toHaveCount(0);
  await shot(c, testInfo, "017", "-second-browser");
});

test("test_guest_banner_then_register_keeps_member", async ({ page, browser }, testInfo) => {
  const flat = await flatWithPlaceholders(page);
  const janet = await freshPage(browser);
  await claimAs(janet, flat.token, "Janet");
  await expect(janet.getByText("Groceries").first()).toBeVisible();
  const banner = janet.getByRole("region", { name: "Guest" });
  await expect(banner).toContainText("You're a guest. Create an account to keep access on any device.");
  await shot(janet, testInfo, "017", "-guest-banner");

  await banner.getByRole("button", { name: "Create account" }).click();
  const sheet = janet.getByRole("dialog", { name: "Create account" });
  await sheet.getByLabel("Your name").fill("Janet");
  await sheet.getByLabel("Email").fill("janet@example.com");
  await sheet.getByLabel("Password").fill("password1234janet");
  await sheet.getByRole("button", { name: "Create account" }).first().click();
  await expect(sheet).toHaveCount(0);
  await expect(janet.getByRole("region", { name: "Guest" })).toHaveCount(0);

  await janet.getByRole("link", { name: "Settings" }).click();
  await expect(janet.getByTestId(`member-${flat.ids.Janet}`)).toHaveText("Janet (you) · joined");
  await shot(janet, testInfo, "017", "-guest-to-account");
  const detail = (await apiCall(janet, "GET", `/groups/${flat.id}/`)) as { my_member_id: number };
  expect(detail.my_member_id).toBe(flat.ids.Janet);
  const me = (await apiCall(janet, "GET", "/me")) as { authenticated: boolean; guest_memberships: number[] };
  expect(me).toMatchObject({ authenticated: true, guest_memberships: [] });
  await janet.getByRole("link", { name: "Balances" }).click();
  await expect(janet.getByTestId("top-card")).toHaveText("you owe 10.00");
  await shot(janet, testInfo, "017", "-history-kept");
});

test("test_guest_logout_warns_and_frees_the_name", async ({ page, browser }, testInfo) => {
  const flat = await flatWithPlaceholders(page);
  const cami = await freshPage(browser);
  await claimAs(cami, flat.token, "Cami");
  await cami.getByRole("region", { name: "Guest" }).getByRole("button", { name: "Sign out" }).click();
  const dialog = cami.getByRole("dialog", { name: "Sign out" });
  await expect(dialog).toContainText("You will lose access on this device. Save the group link or create an account first.");
  await expect(dialog.getByRole("button", { name: "Copy link" })).toBeVisible();
  await shot(cami, testInfo, "017", "-logout-warning");
  await dialog.getByRole("button", { name: "Sign out anyway" }).click();
  await expect(cami).toHaveURL(/\/login$/);

  const next = await freshPage(browser);
  await next.goto(`/join/${flat.token}`);
  await expect(next.getByRole("button", { name: "Cami", exact: true })).toBeVisible();
  await shot(next, testInfo, "017", "-name-free-again");
});

test("test_no_horizontal_scroll_on_join_settings_and_sheets_at_390", async ({ page, browser }, testInfo) => {
  const flat = await flatWithPlaceholders(page);
  await expectNoHorizontalScroll(page);
  const g = await freshPage(browser);
  await g.goto(`/join/${flat.token}`);
  await expect(g.getByRole("heading", { name: "Are you one of these?" })).toBeVisible();
  await expectNoHorizontalScroll(g);
  await claimAs(g, flat.token, "Janet");
  await expectNoHorizontalScroll(g);
  await g.getByRole("region", { name: "Guest" }).getByRole("button", { name: "Create account" }).click();
  await expectNoHorizontalScroll(g);
  await g.getByRole("button", { name: "Close" }).click();
  await g.getByRole("region", { name: "Guest" }).getByRole("button", { name: "Sign out" }).click();
  await expectNoHorizontalScroll(g);
  await shot(g, testInfo, "017");
});
