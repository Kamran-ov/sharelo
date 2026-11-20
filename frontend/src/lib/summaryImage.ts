import { tokenValue } from "./tokens";

const WIDTH = 720;
const PAD = 32;
const LINE = 28;
const SCALE = 2;
const INDENT = 16;

/** Breaks one line at spaces to fit `max`; a word wider than `max` is cut. Nothing is ellipsised. */
function wrap(ctx: CanvasRenderingContext2D, text: string, max: number): string[] {
  if (text === "" || ctx.measureText(text).width <= max) return [text];
  const out: string[] = [];
  let current = "";
  const push = (word: string) => {
    let rest = word;
    while (ctx.measureText(rest).width > max) {
      let cut = rest.length - 1;
      while (cut > 1 && ctx.measureText(rest.slice(0, cut)).width > max) cut -= 1;
      out.push(rest.slice(0, cut));
      rest = rest.slice(cut);
    }
    current = rest;
  };
  for (const word of text.split(" ")) {
    const next = current === "" ? word : `${current} ${word}`;
    if (ctx.measureText(next).width <= max) current = next;
    else {
      if (current !== "") out.push(current);
      push(word);
    }
  }
  if (current !== "") out.push(current);
  return out;
}

/** Draws the summary lines on a card in the token colours of the viewer's current mode; the first
 *  line is the heading. With no tokens loaded the canvas keeps its own defaults (no fallback literal). */
export function renderSummaryPng(lines: string[]): Promise<Blob> {
  const FONT = `16px ${tokenValue("--font-body")}`;
  const BOLD = `600 20px ${tokenValue("--font-heading")}`;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return Promise.reject(new Error("no canvas"));
  const max = WIDTH - 2 * PAD;
  const rows: { text: string; font: string; x: number }[] = [];
  lines.forEach((line, i) => {
    const font = i === 0 ? BOLD : FONT;
    ctx.font = font;
    wrap(ctx, line, max - INDENT).forEach((part, j) => rows.push({ text: part, font, x: PAD + (j > 0 ? INDENT : 0) }));
  });
  const height = 2 * PAD + rows.length * LINE;
  canvas.width = WIDTH * SCALE;
  canvas.height = height * SCALE;
  ctx.scale(SCALE, SCALE);
  ctx.fillStyle = tokenValue("--surface-card");
  ctx.fillRect(0, 0, WIDTH, height);
  ctx.fillStyle = tokenValue("--text");
  ctx.textBaseline = "top";
  rows.forEach((row, i) => {
    ctx.font = row.font;
    ctx.fillText(row.text, row.x, PAD + i * LINE);
  });
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no png"))), "image/png"));
}
