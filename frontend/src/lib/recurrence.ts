export interface Schedule {
  frequency: "monthly" | "yearly";
  day_of_month: number;
  /** 1-12 for yearly, null for monthly. */
  month: number | null;
}

const pad = (n: number) => String(n).padStart(2, "0");
const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function daysIn(year: number, month: number): number {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

/** The day is clamped to the month's length every time from the rule's own day, so Jan 31 → Feb 28 → Mar 31 never drifts. */
function occurrenceIn(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(Math.min(day, daysIn(year, month)))}`;
}

/**
 * Mirrors `ledger/services/recurring.py`: with `inclusive` it is `first_occurrence` (a rule whose day is
 * exactly `from` returns `from`), without it `next_occurrence` (strictly after). Dates stay plain
 * YYYY-MM-DD strings, which sort correctly as text and never pass through Date.
 */
export function nextOccurrences(rule: Schedule, from: string, count: number, inclusive = true): string[] {
  const out: string[] = [];
  let year = Number(from.slice(0, 4));
  let month = rule.frequency === "yearly" ? (rule.month ?? 1) : Number(from.slice(5, 7));
  while (out.length < count) {
    const candidate = occurrenceIn(year, month, rule.day_of_month);
    if (inclusive ? candidate >= from : candidate > from) out.push(candidate);
    if (rule.frequency === "yearly") year += 1;
    else [year, month] = month === 12 ? [year + 1, 1] : [year, month + 1];
  }
  return out;
}

const ordinal = (n: number) => {
  const tail = n % 100;
  if (tail >= 11 && tail <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
};

export function describeRule(rule: Schedule): string {
  if (rule.frequency === "yearly") return `yearly on ${rule.day_of_month} ${MONTH_ABBR[(rule.month ?? 1) - 1]}`;
  return `monthly on the ${ordinal(rule.day_of_month)}`;
}

export const MONTH_NAMES = MONTH_ABBR;
