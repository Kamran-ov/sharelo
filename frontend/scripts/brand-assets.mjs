// Regenerates every committed brand asset from docs/design/: PNG icons, favicon, offline.css,
// the self-hosted fonts and brand-stamp.json. Run `make icons` after EVERY edit of
// docs/design/tokens.css or logo-mark.svg; src/design.test.ts stays red until you do.
// Nothing here runs at build time: the output is committed.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

import { brandStamp, lightToken } from "../src/lib/designTokens.ts";

const root = process.cwd();
const design = path.resolve(root, "../docs/design");
const pub = path.resolve(root, "public");
const icons = path.join(pub, "icons");
const fonts = path.join(pub, "fonts");
mkdirSync(icons, { recursive: true });
mkdirSync(fonts, { recursive: true });

const tokens = readFileSync(path.join(design, "tokens.css"), "utf8");
const logo = readFileSync(path.join(design, "logo-mark.svg"), "utf8");

// Fonts: latin subsets only, the weights the app uses.
const FONT_FILES = [
  ["inter", ["400", "500", "600"]],
  ["space-grotesk", ["500", "600", "700"]],
];
for (const [family, weights] of FONT_FILES) {
  const src = path.resolve(root, "node_modules/@fontsource", family);
  for (const w of weights) copyFileSync(path.join(src, "files", `${family}-latin-${w}-normal.woff2`), path.join(fonts, `${family}-latin-${w}-normal.woff2`));
  copyFileSync(path.join(src, "LICENSE"), path.join(fonts, `${family}-OFL.txt`));
}

writeFileSync(path.join(pub, "favicon.svg"), logo);

// offline.html cannot load the bundle, so it gets the tokens verbatim plus layout in var() only.
writeFileSync(
  path.join(pub, "offline.css"),
  `${tokens}
@font-face { font-family: "Inter"; font-weight: 400; font-display: swap; src: url("/fonts/inter-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: "Space Grotesk"; font-weight: 600; font-display: swap; src: url("/fonts/space-grotesk-latin-600-normal.woff2") format("woff2"); }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: var(--space-4); text-align: center; background: var(--surface-ground); color: var(--text); font-family: var(--font-body); }
h1 { font-family: var(--font-heading); font-size: var(--text-xl); }
p { color: var(--text-muted); font-size: var(--text-md); }
`,
);

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
async function rasterise(html, size, out) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(`<style>html,body{margin:0;width:${size}px;height:${size}px;overflow:hidden}</style>${html}`);
  await page.screenshot({ path: path.join(icons, out), omitBackground: true });
  await page.close();
}
const sized = (px) => logo.replace("<svg ", `<svg width="${px}" height="${px}" style="display:block" `);
await rasterise(sized(192), 192, "icon-192.png");
await rasterise(sized(512), 512, "icon-512.png");
// Maskable: full-bleed brand square, the mark inside the 80 % safe zone.
await rasterise(
  `<div style="width:512px;height:512px;background:${lightToken(tokens, "--brand-primary")};display:grid;place-items:center">${sized(410)}</div>`,
  512,
  "icon-maskable-512.png",
);
await browser.close();

writeFileSync(path.join(icons, "brand-stamp.json"), `${JSON.stringify(brandStamp(tokens, logo, (s) => createHash("sha256").update(s).digest("hex")), null, 2)}\n`);
console.log("brand assets written");
