import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, type Page, type TestInfo } from "@playwright/test";

import { BACKEND_ENV } from "../playwright.config";

const SHOTS = (ticket: string) => path.resolve(process.cwd(), `../docs/screenshots/${ticket}`);

/** Wipes user data and re-seeds the known fixture; the command finishes on its own. */
export function resetFixture() {
  execFileSync("python3", ["manage.py", "e2e_reset"], {
    cwd: path.resolve(process.cwd(), "../backend"),
    env: { ...process.env, ...BACKEND_ENV },
    stdio: "pipe",
  });
}

export async function shot(page: Page, testInfo: TestInfo, ticket = "011") {
  await page.screenshot({ path: path.join(SHOTS(ticket), `${testInfo.title}.png`) });
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

export const HOME = 1;
const ALICE = 1;

async function csrf(page: Page): Promise<string> {
  const cookie = (await page.context().cookies()).find((c) => c.name === "csrftoken");
  expect(cookie, "csrftoken cookie").toBeTruthy();
  return cookie!.value;
}

/** Authenticated API call as the logged-in browser user (cookies and CSRF as the app does). */
export async function apiCall(page: Page, method: "GET" | "POST" | "PUT", path: string, data?: unknown) {
  const res = await page.request.fetch(`/api${path}`, {
    method,
    data,
    headers: method === "GET" ? {} : { "X-CSRFToken": await csrf(page) },
  });
  expect(res.ok(), `${method} ${path} -> ${res.status()}`).toBe(true);
  return res.json();
}

export async function generalCategoryId(page: Page): Promise<number> {
  const tree = (await apiCall(page, "GET", "/categories/")) as { name: string; children: { id: number; name: string }[] }[];
  return tree.flatMap((p) => p.children).find((k) => k.name === "General")!.id;
}

export async function categoryId(page: Page, name: string): Promise<number> {
  const tree = (await apiCall(page, "GET", "/categories/")) as { children: { id: number; name: string }[] }[];
  return tree.flatMap((p) => p.children).find((k) => k.name === name)!.id;
}

export function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export async function seedExpense(page: Page, over: Record<string, unknown> = {}) {
  return apiCall(page, "POST", `/groups/${HOME}/expenses/`, {
    description: "Seeded",
    amount_cents: 1000,
    date: today(),
    category: await generalCategoryId(page),
    payer_member: ALICE,
    preset: "half",
    ...over,
  });
}

export async function balances(page: Page) {
  return (await apiCall(page, "GET", `/groups/${HOME}/balances/`)) as {
    transfers: { from_member: number; to_member: number; amount_cents: number }[];
  };
}

export async function openExpenses(page: Page) {
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/expenses`);
  await openAddEnabled(page);
}

async function openAddEnabled(page: Page) {
  await expect(page.getByLabel("Add expense")).toBeEnabled();
}

export async function quickAdd(page: Page, amount: string, description: string) {
  await page.getByLabel("Add expense").click();
  await page.getByLabel(/Amount/).fill(amount);
  await page.getByLabel("Description").fill(description);
  await page.getByRole("button", { name: "Save" }).click();
}
