import http from "node:http";
import type { Socket } from "node:net";

import { expect, test, type Page } from "@playwright/test";

import { HOME, loginAsFixtureUser, resetFixture, shot } from "./helpers";

// Runs in the `served` project: Django serves the built SPA itself on 8002, no vite preview.
test.beforeEach(() => resetFixture());

const snap = (page: Page, info: import("@playwright/test").TestInfo) => shot(page, info, "015");

async function serviceWorkerControlsPage(page: Page) {
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
}

test("test_manifest_served_with_name_and_icons", async ({ page, request }, testInfo) => {
  await page.goto("/login");
  const response = await request.get("/manifest.webmanifest");
  expect(response.status()).toBe(200);
  const manifest = await response.json();
  expect(manifest.name).toBe("Sharelo");
  expect(manifest.icons.length).toBeGreaterThanOrEqual(2);
  for (const icon of manifest.icons) {
    const res = await request.get(icon.src);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("image/png");
  }
  await snap(page, testInfo);
});

test("test_service_worker_registers", async ({ page }) => {
  await page.goto("/login");
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
  expect(scope).toMatch(/\/$/);
});

// context.setOffline() does not reach the service worker's own fetches in Chromium, so the worker
// would still get the shell from the server. Going offline here means the origin really stops answering:
// the browser talks to a forwarding proxy, and "offline" is closing it.
function startProxy(port: number, target: number): Promise<{ stop: () => Promise<void> }> {
  const sockets = new Set<Socket>();
  const server = http.createServer((req, res) => {
    const upstream = http.request(
      { host: "localhost", port: target, path: req.url, method: req.method, headers: req.headers },
      (up) => {
        res.writeHead(up.statusCode ?? 502, up.headers);
        up.pipe(res);
      },
    );
    upstream.on("error", () => res.destroy());
    req.pipe(upstream);
  });
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  return new Promise((resolve) =>
    server.listen(port, "localhost", () =>
      resolve({
        stop: () =>
          new Promise<void>((done) => {
            sockets.forEach((socket) => socket.destroy());
            server.close(() => done());
          }),
      }),
    ),
  );
}

test("test_offline_reload_shows_offline_page", async ({ browser }, testInfo) => {
  const proxy = await startProxy(8003, 8002);
  const context = await browser.newContext({ baseURL: "http://localhost:8003", viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/expenses`);
  await serviceWorkerControlsPage(page);
  await proxy.stop();
  for (const url of ["/", `/g/${HOME}/expenses`]) {
    await page.goto(url);
    await expect(page).toHaveTitle("Offline — Sharelo");
    await expect(page.getByText("needs a connection")).toBeVisible();
  }
  await snap(page, testInfo);
  await context.close();
});

test("test_api_responses_are_not_kept_in_cache_storage", async ({ page }) => {
  await loginAsFixtureUser(page);
  for (const tab of ["expenses", "balances", "recurring"]) {
    await page.goto(`/g/${HOME}/${tab}`);
    await expect(page.locator("main, [data-testid], h1, h2").first()).toBeVisible();
  }
  await serviceWorkerControlsPage(page);
  const cached = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys()) {
      for (const req of await (await caches.open(name)).keys()) urls.push(new URL(req.url).pathname);
    }
    return urls;
  });
  expect(cached.length).toBeGreaterThan(0);
  expect(cached.filter((u) => u.startsWith("/api/"))).toEqual([]);
  expect(cached.filter((u) => u === "/index.html" || u === "/")).toEqual([]);
});

test("test_unknown_api_path_is_not_the_spa_shell_e2e", async ({ page, request }, testInfo) => {
  await loginAsFixtureUser(page);
  await page.goto(`/g/${HOME}/expenses`);
  await expect(page.getByLabel("Add expense")).toBeEnabled();
  await snap(page, testInfo);

  const unknown = await request.get("/api/does-not-exist/");
  expect(unknown.status()).toBe(404);
  expect(await unknown.text()).not.toContain('<div id="root">');

  const me = await request.get("/api/me");
  expect(me.headers()["content-type"]).toContain("application/json");
});

test("test_install_hint_visible_then_dismissed", async ({ browser }, testInfo) => {
  const context = await browser.newContext({
    baseURL: "http://localhost:8002",
    viewport: { width: 390, height: 844 },
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });
  const page = await context.newPage();
  await page.goto("/login");
  await expect(page.getByRole("region", { name: "Install Sharelo" })).toContainText("Add to Home Screen");
  await snap(page, testInfo);
  await page.getByRole("button", { name: "Dismiss" }).click();
  await page.reload();
  await expect(page.getByRole("heading").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Install Sharelo" })).toHaveCount(0);
  await context.close();
});
