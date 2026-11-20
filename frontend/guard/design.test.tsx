// Ticket 023: the whole look comes from one token file. These tests keep it that way.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import Logo from "../src/components/Logo";
import { Amount, Segmented } from "../src/components/ui";
import { brandStamp, contrast, parseTokens } from "../src/lib/designTokens";
import { scanText, withoutFontFaces } from "./scan";

const FRONTEND = path.resolve(__dirname, "..");
const read = (rel: string) => readFileSync(path.resolve(FRONTEND, rel), "utf8");
const DESIGN_TOKENS = read("../docs/design/tokens.css");
const APP_TOKENS = read("src/styles/tokens.css");
const OFFLINE_CSS = read("public/offline.css");
const { light, dark } = parseTokens(DESIGN_TOKENS);
const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

/** Every file the guard scans, with the text it scans. */
function guardedSources(): { file: string; text: string }[] {
  const src = path.join(FRONTEND, "src");
  const files = walk(src)
    .filter((f) => /\.(ts|tsx|css)$/.test(f))
    .filter((f) => path.relative(src, f) !== path.join("styles", "tokens.css"));
  const out = files.map((f) => {
    const text = readFileSync(f, "utf8");
    const rel = path.relative(FRONTEND, f);
    return { file: rel, text: rel === path.join("src", "styles", "fonts.css") ? withoutFontFaces(text) : text };
  });
  // offline.css = tokens verbatim + layout; only the layout tail is guarded.
  out.push({ file: "public/offline.css (after tokens)", text: withoutFontFaces(OFFLINE_CSS.slice(DESIGN_TOKENS.length)) });
  return out;
}

const report = (findings: { file: string; line: number; rule: string; text: string }[]) =>
  findings.map((f) => `${f.file}:${f.line} [${f.rule}] ${f.text}`).join("\n");

describe("one token file", () => {
  test("test_app_tokens_are_identical_to_design_tokens", () => {
    expect(APP_TOKENS).toBe(DESIGN_TOKENS);
    expect(OFFLINE_CSS.startsWith(DESIGN_TOKENS)).toBe(true);
  });

  test("test_generated_brand_assets_are_current", () => {
    const committed = JSON.parse(read("public/icons/brand-stamp.json"));
    const current = brandStamp(DESIGN_TOKENS, read("../docs/design/logo-mark.svg"), sha256);
    expect(committed, "run `make icons` after editing docs/design/tokens.css or logo-mark.svg").toEqual(current);
  });

  test("test_icons_are_the_sizes_the_manifest_declares", () => {
    const size = (rel: string) => {
      const png = readFileSync(path.resolve(FRONTEND, rel));
      expect(png.subarray(1, 4).toString()).toBe("PNG");
      return [png.readUInt32BE(16), png.readUInt32BE(20)];
    };
    expect(size("public/icons/icon-192.png")).toEqual([192, 192]);
    expect(size("public/icons/icon-512.png")).toEqual([512, 512]);
    expect(size("public/icons/icon-maskable-512.png")).toEqual([512, 512]);
  });
});

describe("guard: no brand literal outside tokens.css", () => {
  test("test_no_colour_or_font_literal_outside_tokens", () => {
    const findings = guardedSources()
      .flatMap(({ file, text }) => scanText(file, text))
      .filter((f) => !["tailwind palette class", "dark: variant"].includes(f.rule));
    expect(report(findings)).toBe("");
  });

  test("test_no_tailwind_default_palette_or_dark_variant_classes", () => {
    const findings = guardedSources()
      .flatMap(({ file, text }) => scanText(file, text))
      .filter((f) => ["tailwind palette class", "dark: variant"].includes(f.rule));
    expect(report(findings)).toBe("");
  });

  // Each pattern: one fixture the scanner must flag, one it must pass.
  const CASES: [string, string, string][] = [
    ["hex", `const c = "#ff0000";`, `const c = "var(--brand-primary)";`],
    ["rgb", `color: rgb(1, 2, 3);`, `color: var(--text);`],
    ["font name", `font: 16px Arial;`, `font: 16px var(--font-body);`],
    ["font-family value", `body { font-family: "Comic Neue"; }`, `body { font-family: var(--font-body); }`],
    ["fontFamily value", `style={{ fontFamily: "Comic Neue" }}`, `style={{ fontFamily: "var(--font-heading)" }}`],
    ["palette class", `className="bg-emerald-600"`, `className="bg-primary"`],
    ["neutral shade", `className="text-neutral-500"`, `className="text-neutral bg-primary border-line ring-offset-ground"`],
    ["ring-offset", `className="ring-offset-white"`, `className="ring-offset-ground"`],
    ["dark variant", `className="dark:bg-card"`, `className="bg-card"`],
    ["named in brackets", `className="bg-[white]"`, `className="bg-[var(--surface-card)]"`],
    ["named in brackets 2", `className="text-[red]"`, `className="text-danger"`],
    ["style object", `style={{ color: "white" }}`, `style={{ color: "var(--text)" }}`],
    ["canvas", `ctx.fillStyle = "black";`, `ctx.fillStyle = tokenValue("--text");`],
    ["svg attribute", `<path fill="white" />`, `<path fill="currentColor" />`],
    ["css named", `p { color: navy; }`, `p { color: var(--text); }`],
    ["css keywords", `a { background: hotpink; }`, `a { background: transparent; color: inherit; border-color: currentColor; }`],
  ];
  test.each(CASES)("test_scanner_flags_%s_and_passes_the_token_form", (_name, bad, good) => {
    expect(scanText("fixture", bad).length).toBeGreaterThan(0);
    expect(report(scanText("fixture", good))).toBe("");
  });

  test("test_font_face_declarations_are_the_only_family_names_allowed_in_fonts_css", () => {
    const css = `@font-face {\n  font-family: "Inter";\n  src: url("/fonts/x.woff2");\n}\nbody { font-family: "Inter"; }\n`;
    expect(scanText("fonts.css", withoutFontFaces(css)).map((f) => f.line)).toEqual([5]);
  });
});

describe("contrast from tokens.css", () => {
  const USED: [string, string][] = [
    ["--text", "--surface-ground"],
    ["--text", "--surface-card"],
    ["--text-muted", "--surface-ground"],
    ["--text-muted", "--surface-card"],
    ["--text-muted", "--surface-sunken"],
    ["--text", "--surface-sunken"],
    ["--text-on-primary", "--brand-primary"],
    ["--money-owed", "--surface-card"],
    ["--money-owe", "--surface-card"],
    ["--money-neutral", "--surface-card"],
    ["--money-owed", "--surface-ground"],
    ["--money-owe", "--surface-ground"],
    ["--brand-primary", "--surface-card"],
    ["--brand-primary", "--surface-ground"],
    ["--text", "--brand-highlight-soft"],
    ["--text", "--money-owe-soft"],
    ["--danger", "--surface-card"],
    ["--danger", "--surface-ground"],
    ["--danger", "--danger-soft"],
    ["--text-on-primary", "--danger"],
    ["--text", "--danger-soft"],
    ["--surface-ground", "--text"],
  ];
  test.each(["light", "dark"] as const)("test_text_tokens_meet_4_5_contrast_on_their_surfaces (%s)", (mode) => {
    const t = mode === "light" ? light : dark;
    const failing = USED.map(([fg, bg]) => [fg, bg, contrast(t[fg], t[bg])] as const).filter(([, , r]) => r < 4.5);
    expect(failing).toEqual([]);
  });

  test("test_pairs_the_app_avoids_are_still_below_4_5", () => {
    // If one of these rises above 4.5 the workaround in spec 023 Q2 can go.
    expect(contrast(light["--money-owe"], light["--money-owe-soft"])).toBeLessThan(4.5);
    expect(contrast(dark["--brand-primary"], dark["--brand-highlight-soft"])).toBeLessThan(4.5);
    expect(contrast(dark["--brand-highlight"], dark["--brand-primary"])).toBeLessThan(4.5);
  });

  test("test_contrast_threshold_is_applied", () => {
    expect(contrast("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
    expect(contrast("#777777", "#FFFFFF")).toBeLessThan(4.5);
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
  });
});

describe("logo", () => {
  function svgParts(svg: string) {
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
    return [...doc.querySelectorAll("rect, path")].map((el) => ({
      tag: el.tagName,
      geometry: el.getAttribute("d") ?? `rx=${el.getAttribute("rx")}`,
      paint: el.getAttribute("fill") ?? el.getAttribute("stroke"),
    }));
  }

  test("test_logo_component_matches_both_logo_files", () => {
    const { container } = render(<Logo />);
    const mine = svgParts(container.querySelector("svg")!.outerHTML);
    const files = { light: svgParts(read("../docs/design/logo-mark.svg")), dark: svgParts(read("../docs/design/logo-mark-dark.svg")) };
    for (const [mode, file] of Object.entries(files)) {
      const tokens = mode === "light" ? light : dark;
      expect(mine.map((p) => [p.tag, p.geometry])).toEqual(file.map((p) => [p.tag, p.geometry]));
      const resolved = mine.map((p) => tokens[/^var\((--[\w-]+)\)$/.exec(p.paint ?? "")![1]].toUpperCase());
      expect(resolved, mode).toEqual(file.map((p) => p.paint!.toUpperCase()));
    }
  });

  test("test_logo_wordmark_is_text_lower_case", () => {
    render(<Logo wordmark />);
    const word = screen.getByText("sharelo");
    expect(word.tagName).not.toBe("IMG");
    expect(word.textContent).toBe("sharelo");
  });
});

describe("components", () => {
  test("test_amount_always_renders_its_words", () => {
    const { rerender } = render(<Amount tone="owe" label="you owe" figure="12.00" data-testid="a" />);
    expect(screen.getByTestId("a").textContent).toBe("you owe 12.00");
    rerender(<Amount tone="owed" label="you lent" figure="21.05" data-testid="a" />);
    expect(screen.getByTestId("a").textContent).toBe("you lent 21.05");
    expect(screen.getByTestId("a")).toHaveAttribute("data-tone", "owed");
  });

  test("test_segmented_marks_selected_with_aria", () => {
    function Harness() {
      const [v, setV] = useState("you");
      return <Segmented label="Who paid" value={v} onChange={setV} options={[{ value: "you", label: "You" }, { value: "bea", label: "Bea" }]} />;
    }
    render(<Harness />);
    const group = screen.getByRole("group", { name: "Who paid" });
    const [you, bea] = [screen.getByRole("button", { name: "You" }), screen.getByRole("button", { name: "Bea" })];
    expect(group).toContainElement(you);
    expect(you).toHaveAttribute("aria-pressed", "true");
    expect(bea).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(bea);
    expect(you).toHaveAttribute("aria-pressed", "false");
    expect(bea).toHaveAttribute("aria-pressed", "true");
  });
});
