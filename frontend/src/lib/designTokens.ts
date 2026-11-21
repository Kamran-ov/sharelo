// Pure readers of tokens.css text. Shared by vite.config.ts (manifest colours), the brand-asset
// script (node strips the types) and the design tests, so there is one parser.

/** Custom properties of a CSS block: `--name: value;` pairs, comments removed. */
function declarations(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  const clean = block.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of clean.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

/** Light values (`:root` before the dark media query) and dark values (light overridden). */
export function parseTokens(css: string): { light: Record<string, string>; dark: Record<string, string> } {
  const at = css.indexOf("@media (prefers-color-scheme: dark)");
  const lightPart = at === -1 ? css : css.slice(0, at);
  const light = declarations(lightPart);
  const dark = at === -1 ? { ...light } : { ...light, ...declarations(css.slice(at)) };
  return { light, dark };
}

export function lightToken(css: string, name: string): string {
  const v = parseTokens(css).light[name];
  if (v === undefined) throw new Error(`token ${name} missing from tokens.css`);
  return v;
}

export type BrandStamp = { logo_sha256: string; brand_primary: string; tokens_sha256: string };

/** What the committed icons/offline.css were generated from; compared by design.test.ts. */
export function brandStamp(tokensCss: string, logoSvg: string, sha256: (s: string) => string): BrandStamp {
  return { logo_sha256: sha256(logoSvg), brand_primary: lightToken(tokensCss, "--brand-primary"), tokens_sha256: sha256(tokensCss) };
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const [r, g, b] = [m[1], m[2], m[3]].map((x) => channel(parseInt(x, 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2 contrast ratio of two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
