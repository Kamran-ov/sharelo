import type { ShareSummary } from "../api";
import { formatCents } from "./money";

// A fixed table, not toLocaleString: the message must read the same on every phone and in tests.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-02" → "2 Nov". The server sends calendar dates; no Date object, so no timezone shift. */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]}`;
}

/** The one source for both the shared text and the image card. Every number comes from the server. */
export function summaryLines(s: ShareSummary): string[] {
  const names = new Map(s.per_member.map((m) => [m.member_id, m.display_name]));
  const name = (id: number) => names.get(id) ?? "?";
  const lines = [`${s.group.name} — total ${formatCents(s.total_spent_cents)} ${s.currency}`, ""];
  if (s.transfers.length === 0) lines.push("All settled up.");
  for (const t of s.transfers) lines.push(`${name(t.from_member)} pays ${name(t.to_member)} ${formatCents(t.amount_cents)}`);
  if (s.recent_expenses.length > 0) {
    lines.push("", "Last expenses:");
    for (const e of s.recent_expenses) {
      lines.push(`${shortDate(e.date)} ${e.description} ${formatCents(e.amount_cents)} (${e.paid_by.map(name).join(", ")})`);
    }
  }
  return lines;
}

export function summaryText(s: ShareSummary): string {
  return summaryLines(s).join("\n");
}
