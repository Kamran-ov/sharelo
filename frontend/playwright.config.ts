import path from "node:path";

import { defineConfig } from "@playwright/test";

// `localhost`, never 127.0.0.1: the browser Origin must equal the Host Django sees through the proxy.
const BASE = "http://localhost:4173";
const SERVED = "http://localhost:8002";
export const BACKEND_ENV = {
  E2E: "1",
  SECRET_KEY: process.env.SECRET_KEY ?? "test-only-not-a-secret",
  DATABASE_URL: process.env.DATABASE_URL ?? "postgres://sharelo:sharelo@localhost:5432/sharelo_e2e",
};

export default defineConfig({
  testDir: "./e2e",
  // One database, so one worker and no parallelism.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE,
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
    permissions: ["clipboard-read", "clipboard-write"],
  },
  // `preview` goes through vite preview (4173); `served` is Django serving the built SPA itself (8002).
  projects: [
    { name: "preview", testIgnore: "pwa.spec.ts" },
    { name: "served", testMatch: "pwa.spec.ts", use: { baseURL: SERVED } },
  ],
  // Playwright owns every server: it starts them and stops them. Nobody runs them by hand.
  webServer: [
    {
      command: "python3 manage.py e2e_prepare && python3 manage.py runserver 8001 --noreload",
      cwd: "../backend",
      url: "http://localhost:8001/api/me",
      env: BACKEND_ENV,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npx vite preview --port 4173 --strictPort",
      url: BASE,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // No e2e_prepare: the first entry already prepared the shared sharelo_e2e database.
      // frontend/dist comes from `make e2e`'s build step, shared with vite preview.
      command: "python3 manage.py runserver 8002 --noreload",
      cwd: "../backend",
      url: "http://localhost:8002/api/me",
      env: { ...BACKEND_ENV, FRONTEND_DIST: path.resolve(process.cwd(), "dist") },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
