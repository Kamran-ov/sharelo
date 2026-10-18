/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // changeOrigin stays false so Host matches the browser Origin and Django's CSRF check passes.
  server: { proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"] },
});
