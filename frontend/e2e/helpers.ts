import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, type Page, type TestInfo } from "@playwright/test";

import { BACKEND_ENV } from "../playwright.config";

const SHOTS = path.resolve(process.cwd(), "../docs/screenshots/011");

/** Wipes user data and re-seeds the known fixture; the command finishes on its own. */
export function resetFixture() {
  execFileSync("python3", ["manage.py", "e2e_reset"], {
    cwd: path.resolve(process.cwd(), "../backend"),
    env: { ...process.env, ...BACKEND_ENV },
    stdio: "pipe",
  });
}

export async function shot(page: Page, testInfo: TestInfo) {
  await page.screenshot({ path: path.join(SHOTS, `${testInfo.title}.png`) });
}

export async function loginAsFixtureUser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("a@example.com");
  await page.getByLabel("Password").fill("password1234");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/groups$/);
}

export async function expectNoHorizontalScroll(page: Page) {
  const m = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    maxRight: Math.max(...[...document.querySelectorAll("body *")].map((e) => e.getBoundingClientRect().right)),
  }));
  expect(m.scrollWidth).toBeLessThanOrEqual(390);
  expect(m.maxRight).toBeLessThanOrEqual(390);
}
