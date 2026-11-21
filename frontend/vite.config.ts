/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

import { defineConfig, type Plugin } from "vite";
import { VitePWA } from "vite-plugin-pwa";

import { lightToken } from "./src/lib/designTokens";

// Brand colours outside CSS (manifest, <meta theme-color>) are read from the one token file.
const TOKENS = readFileSync(new URL("./src/styles/tokens.css", import.meta.url), "utf8");
const THEME_COLOR = lightToken(TOKENS, "--brand-primary");
const BACKGROUND_COLOR = lightToken(TOKENS, "--surface-ground");

const themeColorMeta = (): Plugin => ({
  name: "sharelo-theme-color",
  transformIndexHtml: () => [{ tag: "meta", attrs: { name: "theme-color", content: THEME_COLOR }, injectTo: "head" }],
});

// changeOrigin stays false so Host matches the browser Origin and Django's CSRF check passes.
const apiProxy = (target: string) => ({ "/api": { target, changeOrigin: false } });

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    themeColorMeta(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Sharelo",
        short_name: "Sharelo",
        description: "Shared expenses, simply",
        start_url: "/",
        scope: "/",
        display: "standalone",
        theme_color: THEME_COLOR,
        background_color: BACKGROUND_COLOR,
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        clientsClaim: true,
        // woff2 so offline.html renders in the brand fonts with no network.
        globPatterns: ["**/*.{js,css,html,woff2}"],
        skipWaiting: true,
        // Navigations always go to the network; offline.html (precached once, from the default
        // globPatterns) is the only fallback. The shell is never served from cache, and nothing
        // under /api/ is cached: no authenticated response may outlive logout.
        navigateFallback: null,
        globIgnores: ["**/index.html"],
        directoryIndex: null,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === "navigate",
            handler: "NetworkOnly",
            options: { precacheFallback: { fallbackURL: "/offline.html" } },
          },
        ],
      },
    }),
  ],
  server: { proxy: apiProxy("http://localhost:8000") },
  // The e2e backend listens on 8001; `localhost` (not 127.0.0.1) keeps Host equal to Origin.
  preview: { proxy: apiProxy("http://localhost:8001") },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
