// Rasterises frontend/public/icons/*.svg to the PNGs the manifest lists. Run by hand
// (`cd frontend && node scripts/make-icons.mjs`); the PNGs are committed, nothing is generated at build time.
import { readFileSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const dir = path.resolve(process.cwd(), "public/icons");
const jobs = [
  ["icon.svg", "icon-192.png", 192],
  ["icon.svg", "icon-512.png", 512],
  ["icon-maskable.svg", "icon-maskable-512.png", 512],
];
const browser = await chromium.launch();
for (const [svg, png, size] of jobs) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  const body = readFileSync(path.join(dir, svg), "utf8");
  await page.setContent(`<style>html,body{margin:0}svg{width:${size}px;height:${size}px;display:block}</style>${body}`);
  await page.screenshot({ path: path.join(dir, png), omitBackground: false });
  await page.close();
}
await browser.close();
