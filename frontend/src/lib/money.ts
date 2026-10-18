const MAX_WHOLE_DIGITS = 9;

/** "12,50" / "12.50" / "12" / ".50" → cents. Integer maths on the digits; null for anything else. */
export function parseAmount(text: string): number | null {
  const match = /^(\d*)(?:[.,](\d{1,2}))?$/.exec(text.trim());
  if (!match) return null;
  const [, whole, frac = ""] = match;
  if ((whole === "" && frac === "") || whole.length > MAX_WHOLE_DIGITS) return null;
  const cents = Number(whole || "0") * 100 + Number(frac.padEnd(2, "0") || "0");
  return cents > 0 ? cents : null;
}

/** Display only: "4210" → "42.10". Locale-free, no grouping, built from integer division. */
export function formatCents(cents: number): string {
  const abs = Math.abs(cents);
  const sign = cents < 0 ? "-" : "";
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}
