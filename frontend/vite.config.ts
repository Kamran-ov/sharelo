/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// changeOrigin stays false so Host matches the browser Origin and Django's CSRF check passes.
const apiProxy = (target: string) => ({ "/api": { target, changeOrigin: false } });

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Sharelo",
        short_name: "Sharelo",
        description: "Shared expenses, simply",
        start_url: "/",
        scope: "/",
        display: "standalone",
        theme_color: "#059669",
        background_color: "#ffffff",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        clientsClaim: true,
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
