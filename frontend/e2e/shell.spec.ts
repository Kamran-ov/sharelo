import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll, loginAsFixtureUser, resetFixture, shot } from "./helpers";

test.beforeEach(() => resetFixture());

test("test_register_new_account_lands_on_groups", async ({ page }, testInfo) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Your name").fill("Newcomer");
  await page.getByLabel("Email").fill("new@example.com");
  await page.getByLabel("Password").fill("Tr0ub4dor&3-horse-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/groups$/);
  await expect(page.getByRole("heading", { name: "Groups" })).toBeVisible();
  await shot(page, testInfo);
});

test("test_login_as_fixture_user_shows_home_with_main_badge", async ({ page }, testInfo) => {
  await loginAsFixtureUser(page);
  const home = page.getByRole("link", { name: /Home/ });
  await expect(home).toBeVisible();
  await expect(home).toContainText("main");
  await shot(page, testInfo);
});

test("test_wrong_password_shows_message_inline_without_redirect", async ({ page }, testInfo) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("a@example.com");
  await page.getByLabel("Password").fill("not-the-password");
  const response = page.waitForResponse((r) => r.url().endsWith("/api/auth/login"));
  await page.getByRole("button", { name: "Sign in" }).click();
  const body = await (await response).json();
  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toHaveText(body.detail || body.code);
  await expect(page).toHaveURL(/\/login$/);
  await shot(page, testInfo);
});

test("test_create_trip_group_is_listed_linked_to_home", async ({ page }, testInfo) => {
  await loginAsFixtureUser(page);
  await page.getByRole("button", { name: "New group" }).click();
  await page.getByLabel("Name").fill("Lisbon trip");
  await page.getByRole("button", { name: "Create group" }).click();
  const trip = page.getByRole("link", { name: /Lisbon trip/ });
  await expect(trip).toBeVisible();
  await expect(trip).toContainText("linked to Home");
  await shot(page, testInfo);
});

test("test_guest_joins_by_link_and_sees_name_in_settings", async ({ page }, testInfo) => {
  await page.goto("/join/e2e-rome-token");
  await expect(page.getByRole("heading", { name: "Join Rome trip" })).toBeVisible();
  await page.getByLabel("Your name").fill("Guest Gina");
  await page.getByRole("button", { name: "Join" }).click();
  await expect(page).toHaveURL(/\/g\/\d+\/expenses$/);
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("Guest Gina")).toBeVisible();
  await page.getByRole("button", { name: "Copy link" }).click();
  await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
  await shot(page, testInfo);
});

test("test_anonymous_groups_redirects_to_login", async ({ page }, testInfo) => {
  await page.goto("/groups");
  await expect(page).toHaveURL(/\/login$/);
  await shot(page, testInfo);
});

test("test_guest_with_membership_sees_only_own_group_in_groups_list", async ({ page }, testInfo) => {
  await page.goto("/join/e2e-rome-token");
  await page.getByLabel("Your name").fill("Guest Gina");
  await page.getByRole("button", { name: "Join" }).click();
  await expect(page).toHaveURL(/\/g\/\d+\/expenses$/);
  await page.goto("/groups");
  await expect(page.getByRole("link", { name: /Rome trip/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Home/ })).toHaveCount(0);
  await shot(page, testInfo);
});

test("test_no_horizontal_scroll_at_390", async ({ page }, testInfo) => {
  await page.goto("/login");
  await expectNoHorizontalScroll(page);
  await loginAsFixtureUser(page);
  await expectNoHorizontalScroll(page);
  await page.getByRole("link", { name: /Rome trip|Home/ }).first().click();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("Share link")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await shot(page, testInfo);
});
