/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// changeOrigin stays false so Host matches the browser Origin and Django's CSRF check passes.
const apiProxy = (target: string) => ({ "/api": { target, changeOrigin: false } });

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
