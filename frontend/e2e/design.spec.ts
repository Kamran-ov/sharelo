// Ticket 023: the look comes from tokens.css alone. The override values below live here, outside
// the guarded src/ tree, on purpose: they are test inputs, not brand values.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { expectNoHorizontalScroll, HOME, loginAs, loginAsFixtureUser, resetFixture, ROME_TOKEN, seedExpense, shot } from "./helpers";

test.beforeEach(() => resetFixture());

const OVERRIDE = `:root { --brand-primary: rgb(1, 2, 3) !important; --font-heading: "Courier New", monospace !important; --radius-lg: 3px !important; }`;
const MODES = ["light", "dark"] as const;

const css = (page: Page, selector: string, prop: string) =>
  page.locator(selector).first().evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop);
const override = (page: Page) => page.addStyleTag({ content: OVERRIDE });

for (const mode of MODES) {
  test(`test_tokens_override_reaches_every_page (${mode})`, async ({ page, browser }, testInfo) => {
    await page.emulateMedia({ colorScheme: mode });
    await loginAsFixtureUser(page);
    await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
    await page.goto(`/g/${HOME}/expenses`);
    await expect(page.getByLabel("Add expense")).toBeEnabled();
    await override(page);

    expect(await css(page, '[aria-label="Add expense"]', "background-color")).toBe("rgb(1, 2, 3)");
    expect(await css(page, "header h1", "font-family")).toMatch(/^"Courier New"/);
    const list = page.getByTestId("expense-row").first().locator("xpath=..");
    expect(await list.evaluate((el) => getComputedStyle(el).borderTopLeftRadius)).toBe("3px");
    await shot(page, testInfo, "023", "-expenses");

    // Client-side navigation keeps the injected style.
    await page.getByRole("link", { name: "Balances" }).click();
    const settle = page.getByTestId("transfer").getByRole("button", { name: "Settle" });
    await expect(settle).toBeVisible();
    expect(await settle.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(1, 2, 3)");
    expect(await css(page, 'nav[aria-label="Group"] a[aria-current="page"]', "color")).toBe("rgb(1, 2, 3)");
    await shot(page, testInfo, "023", "-balances");

    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: mode });
    const anon = await context.newPage();
    await anon.goto("/login");
    await override(anon);
    const signIn = anon.getByRole("button", { name: "Sign in" });
    expect(await signIn.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(1, 2, 3)");
    expect(await css(anon, "h1", "font-family")).toMatch(/^"Courier New"/);
    await context.close();
  });
}

test("test_dark_mode_changes_ground_from_tokens", async ({ page }) => {
  await page.goto("/login");
  await page.emulateMedia({ colorScheme: "light" });
  expect(await css(page, "body", "background-color")).toBe("rgb(244, 249, 248)");
  await page.emulateMedia({ colorScheme: "dark" });
  expect(await css(page, "body", "background-color")).toBe("rgb(15, 46, 51)");
});

test("test_fonts_load_from_own_origin", async ({ page }) => {
  const hosts = new Set<string>();
  const fontResponses: number[] = [];
  page.on("request", (r) => hosts.add(new URL(r.url()).hostname));
  page.on("response", (r) => {
    if (/\/fonts\/[^/]+\.woff2$/.test(new URL(r.url()).pathname)) fontResponses.push(r.status());
  });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  const faces = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].map((f) => ({ family: f.family.replace(/["']/g, ""), weight: f.weight, status: f.status }));
  });
  expect(faces.some((f) => f.family === "Inter" && f.status === "loaded")).toBe(true);
  expect(faces.some((f) => f.family === "Space Grotesk" && f.status === "loaded")).toBe(true);
  expect(fontResponses).toContain(200);
  expect([...hosts]).toEqual(["localhost"]);
});

test("test_built_css_defines_no_token_twice", () => {
  const dir = path.resolve(process.cwd(), "dist/assets");
  const built = readdirSync(dir)
    .filter((f) => f.endsWith(".css"))
    .map((f) => readFileSync(path.join(dir, f), "utf8"))
    .join("\n");
  const selfRefs = (text: string) => [...text.matchAll(/--([\w-]+):\s*var\(--\1\)/g)].map((m) => m[0]);
  expect(selfRefs(built)).toEqual([]);
  expect(selfRefs("a{--font-heading:var(--font-heading)}")).toEqual(["--font-heading:var(--font-heading)"]);

  const tokens = readFileSync(path.resolve(process.cwd(), "src/styles/tokens.css"), "utf8");
  const values = (text: string, name: string) => [...text.matchAll(new RegExp(`${name}:\\s*([^;}]+)`, "g"))].map((m) => m[1].trim().toLowerCase());
  for (const name of ["--font-heading", "--radius-lg", "--brand-primary"]) {
    // Minification may drop spaces after commas; compare without whitespace.
    const norm = (v: string) => v.replace(/\s+/g, "");
    expect(values(built, name).map(norm).sort(), name).toEqual(values(tokens, name).map(norm).sort());
  }
});

test("test_pages_have_no_horizontal_scroll_at_390", async ({ page }) => {
  await page.goto("/login");
  await expectNoHorizontalScroll(page);
  await page.goto(`/join/${ROME_TOKEN}`);
  await expect(page.getByRole("heading", { name: "Join Rome trip" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await loginAsFixtureUser(page);
  await expectNoHorizontalScroll(page);
  await seedExpense(page, { description: "A rather long description that should wrap and never push the page sideways", amount_cents: 4210 });
  for (const tab of ["expenses", "balances", "recurring", "settings", "bank-import"]) {
    await page.goto(`/g/${HOME}/${tab}`);
    await expect(page.getByRole("navigation", { name: "Group" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expectNoHorizontalScroll(page);
  }
  await page.goto(`/g/${HOME}/expenses`);
  await page.getByLabel("Add expense").click();
  await expect(page.getByRole("dialog", { name: "New expense" })).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("test_no_horizontal_scroll_helper_detects_a_wide_element", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() => {
    const wide = document.createElement("div");
    wide.style.width = "600px";
    wide.style.height = "10px";
    document.body.appendChild(wide);
  });
  await expect(expectNoHorizontalScroll(page)).rejects.toThrow();
});

test("test_expenses_hero_shows_overall_balance_and_counterparts", async ({ page }, testInfo) => {
  await loginAsFixtureUser(page);
  await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
  await page.goto(`/g/${HOME}/expenses`);
  const hero = page.getByTestId("hero");
  await expect(hero.getByTestId("hero-label")).toHaveText("Overall, you are owed");
  await expect(hero.getByTestId("hero-total")).toHaveText("21.05 EUR");
  await expect(hero.getByTestId("hero-line")).toHaveText(["Bea owes you 21.05"]);
  await shot(page, testInfo, "023", "-creditor");

  await loginAs(page, "b@example.com");
  await page.goto(`/g/${HOME}/expenses`);
  await expect(hero.getByTestId("hero-label")).toHaveText("Overall, you owe");
  await expect(hero.getByTestId("hero-total")).toHaveText("21.05 EUR");
  await expect(hero.getByTestId("hero-line")).toHaveText(["you owe Alice 21.05"]);
  await shot(page, testInfo, "023", "-debtor");

  await page.getByRole("link", { name: "Balances" }).click();
  await page.getByTestId("transfer").getByRole("button", { name: "Settle" }).click();
  await page.getByRole("dialog", { name: "Settle up" }).getByRole("button", { name: "Settle" }).click();
  await expect(page.getByTestId("top-card")).toHaveText("all settled");
  await page.getByRole("link", { name: "Expenses" }).click();
  await expect(hero.getByTestId("hero-label")).toHaveText("Overall, all settled");
  await expect(hero.getByTestId("hero-total")).toHaveCount(0);
  await expect(hero.getByTestId("hero-line")).toHaveCount(0);
});

/** One screenshot per screen and mode, for comparison with docs/design/screens (no pixel assertion). */
for (const mode of MODES) {
  test(`test_design_screenshots (${mode})`, async ({ page }, testInfo: TestInfo) => {
    const snap = (name: string) => page.screenshot({ path: path.resolve(process.cwd(), `../docs/screenshots/023/${name}-${mode}.png`) });
    await page.emulateMedia({ colorScheme: mode });
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await snap("login");
    await page.goto(`/join/${ROME_TOKEN}`);
    await expect(page.getByRole("heading", { name: "Join Rome trip" })).toBeVisible();
    await snap("join");
    await loginAsFixtureUser(page);
    await seedExpense(page, { description: "Pizza", amount_cents: 4210 });
    await seedExpense(page, { description: "Groceries", amount_cents: 3120, preset: "personal" });
    await page.goto("/groups");
    await expect(page.getByRole("heading", { name: "Groups" })).toBeVisible();
    await snap("groups");
    await page.goto(`/g/${HOME}/expenses`);
    await expect(page.getByTestId("hero")).toBeVisible();
    await snap("expenses");
    await page.getByLabel("Add expense").click();
    await page.getByLabel(/Amount/).fill("12.50");
    await expect(page.getByRole("dialog", { name: "New expense" })).toBeVisible();
    await snap("add-sheet");
    await page.keyboard.press("Escape");
    await page.getByRole("link", { name: "Balances" }).click();
    await expect(page.getByTestId("transfer")).toBeVisible();
    await snap("balances");
    await page.getByRole("link", { name: "Recurring" }).click();
    await expect(page.getByLabel("Add recurring expense")).toBeVisible();
    await snap("recurring");
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByTestId("share-url")).toBeVisible();
    await snap("settings");
    expect(testInfo.title).toContain(mode);
  });
}
