export type Who = "half" | "equal" | "personal" | "all_other" | "custom";

export interface ApiPreset {
  preset: string;
  params?: Record<string, number>;
}

interface Split {
  member: number;
  owed_cents: number;
}

/** The form's two choices → the API body. Rounding and splitting stay on the server. */
export function toApiPreset(who: Who, payerId: number, memberIds: number[], percent: number): ApiPreset {
  switch (who) {
    case "half":
      return { preset: "half" };
    case "equal":
      return { preset: "equal" };
    case "personal":
      return { preset: "personal" };
    case "all_other":
      return { preset: "full_for_other", params: { other_id: otherOf(payerId, memberIds) } };
    case "custom":
      return { preset: "percentage", params: { percent_payer: percent } };
  }
}

export function otherOf(payerId: number, memberIds: number[]): number {
  return memberIds.find((m) => m !== payerId) ?? payerId;
}

export interface Detected {
  who: Who;
  percent: number;
}

/**
 * Read-side derivation for prefilling the edit sheet only: the API keeps a split's cents, not the
 * preset that made them. The server still computes every split from the preset a PATCH sends.
 * Leftover cents go to the lowest member ids, so "equal" tolerates +1 on those.
 */
export function detectPreset(total: number, payerId: number, memberIds: number[], splits: Split[]): Detected | null {
  const owed = (id: number) => splits.find((s) => s.member === id)?.owed_cents ?? 0;
  const ids = [...memberIds].sort((a, b) => a - b);
  const n = ids.length;
  if (total <= 0 || n < 2) return null;
  const payerShare = owed(payerId);
  if (payerShare === total) return { who: "personal", percent: 100 };
  if (n === 2 && payerShare === 0 && owed(otherOf(payerId, ids)) === total) return { who: "all_other", percent: 0 };
  const base = Math.floor(total / n);
  const extra = total - base * n;
  if (ids.every((id, i) => owed(id) === base + (i < extra ? 1 : 0))) {
    return { who: n === 2 ? "half" : "equal", percent: 50 };
  }
  if (n === 2) {
    const percent = Math.round((payerShare * 100) / total);
    const floor = Math.floor((total * percent) / 100);
    const rest = owed(otherOf(payerId, ids));
    if (percent % 5 === 0 && payerShare + rest === total && (payerShare === floor || payerShare === floor + 1)) {
      return { who: "custom", percent };
    }
  }
  return null;
}

/** The payer's percent in a stored `percentage` default: absolute basis points per member id. */
export function storedPercent(params: Record<string, unknown> | undefined, payerId: number): number | null {
  const bp = (params?.basis_points as Record<string, number> | undefined)?.[String(payerId)];
  if (typeof bp === "number") return Math.round(bp / 100);
  const direct = params?.percent_payer;
  return typeof direct === "number" ? direct : null;
}

/** Category default (as the API returns it) → the sheet's choice; falls back where the sheet cannot honour it. */
export function whoFromDefault(
  d: { preset: string; params?: Record<string, unknown> } | undefined,
  memberCount: number,
  payerId: number,
): { who: Who; percent: number } {
  const fallback: Who = memberCount === 2 ? "half" : "equal";
  if (!d) return { who: fallback, percent: 50 };
  if (d.preset === "personal") return { who: "personal", percent: 100 };
  if (memberCount === 2 && d.preset === "full_for_other") return { who: "all_other", percent: 0 };
  const percent = storedPercent(d.params, payerId);
  if (memberCount === 2 && d.preset === "percentage" && percent !== null) return { who: "custom", percent };
  return { who: fallback, percent: 50 };
}

export type Share =
  | { kind: "owe" | "lent"; cents: number }
  | { kind: "personal" | "settled" | "not_involved" };

export function shareFor(
  me: number,
  payers: { member: number; paid_cents: number }[],
  splits: Split[],
  splitType: string,
): Share {
  const paid = payers.find((p) => p.member === me)?.paid_cents;
  const owed = splits.find((s) => s.member === me)?.owed_cents;
  if (paid === undefined && owed === undefined) return { kind: "not_involved" };
  const delta = (owed ?? 0) - (paid ?? 0);
  if (delta > 0) return { kind: "owe", cents: delta };
  if (delta < 0) return { kind: "lent", cents: -delta };
  return { kind: splitType === "personal" ? "personal" : "settled" };
}

/** Distinct latest descriptions (case-insensitive), newest first, each with its own category. */
export function descriptionSuggestions<T extends { description: string; category: number }>(rows: T[], max = 20) {
  const seen = new Set<string>();
  const out: { description: string; category: number }[] = [];
  for (const r of rows) {
    const key = r.description.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ description: r.description, category: r.category });
    if (out.length === max) break;
  }
  return out;
}

/** child category ids ordered by use count (desc), ties and unused by seed order (the input order). */
export function orderByUse<T extends { id: number }>(children: T[], counts: Map<number, number>): T[] {
  return children
    .map((c, i) => ({ c, i }))
    .sort((a, b) => (counts.get(b.c.id) ?? 0) - (counts.get(a.c.id) ?? 0) || a.i - b.i)
    .map((x) => x.c);
}
