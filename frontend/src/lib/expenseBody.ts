import { parseAmount } from "./money";
import { otherOf, toApiPreset, type Who } from "./presets";

export type AdvancedMode = "none" | "exact" | "shares" | "subset";

/** Everything the add/edit form holds; pure data so the request body is testable without a DOM. */
export interface FormValues {
  amountText: string;
  currency: string;
  manualRate: string;
  description: string;
  category: number;
  date: string;
  payerId: number;
  /** null = the stored split could not be mapped to a preset and has not been touched. */
  who: Who | null;
  percent: number;
  mode: AdvancedMode;
  exactTexts: Record<number, string>;
  sharesTexts: Record<number, string>;
  subset: number[];
}

export interface GroupLike {
  currency: string;
  members: { id: number }[];
}

export function parseRate(text: string): string | null {
  const t = text.trim().replace(",", ".");
  return /^\d+(\.\d{1,8})?$/.test(t) && Number(t) > 0 ? t : null;
}

function splitPart(v: FormValues, group: GroupLike): { preset: string; params?: Record<string, unknown> } | null {
  const ids = group.members.map((m) => m.id);
  if (v.mode === "exact") {
    const cents: Record<number, number> = {};
    for (const id of ids) cents[id] = parseAmount(v.exactTexts[id] ?? "") ?? 0;
    return { preset: "exact", params: { cents } };
  }
  if (v.mode === "shares") {
    const shares: Record<number, number> = {};
    for (const id of ids) shares[id] = Number.parseInt(v.sharesTexts[id] ?? "0", 10) || 0;
    return { preset: "shares", params: { shares } };
  }
  if (v.mode === "subset") {
    return { preset: "shares", params: { shares: Object.fromEntries(v.subset.map((id) => [id, 1])) } };
  }
  if (v.who === null) return null;
  return toApiPreset(v.who, v.payerId, ids, v.percent);
}

/** Stable text of the split inputs, to tell whether the user touched them. */
export function splitKey(v: FormValues): string {
  return JSON.stringify([v.who, v.percent, v.mode, v.exactTexts, v.sharesTexts, v.subset]);
}

export function buildCreateBody(v: FormValues, group: GroupLike, rate: string | null): Record<string, unknown> {
  const cents = parseAmount(v.amountText) ?? 0;
  const foreign = v.currency !== group.currency;
  return {
    description: v.description.trim(),
    date: v.date,
    category: v.category,
    payer_member: v.payerId,
    ...(foreign
      ? { original_currency: v.currency, original_amount_cents: cents, ...(rate ? { rate_used: rate } : {}) }
      : { amount_cents: cents }),
    ...splitPart(v, group),
  };
}

/** PATCH body: only what changed, except that a changed amount or payer needs the split restated. */
export function buildPatchBody(v: FormValues, initial: FormValues, group: GroupLike): Record<string, unknown> {
  const foreign = v.currency !== group.currency;
  const cents = parseAmount(v.amountText) ?? 0;
  const amountChanged = v.amountText !== initial.amountText;
  const payerChanged = v.payerId !== initial.payerId;
  const body: Record<string, unknown> = {
    description: v.description.trim(),
    date: v.date,
    category: v.category,
  };
  if (amountChanged) {
    Object.assign(body, foreign ? { original_currency: v.currency, original_amount_cents: cents } : { amount_cents: cents });
  }
  if (payerChanged) body.payer_member = v.payerId;
  if (amountChanged || payerChanged || splitKey(v) !== splitKey(initial)) {
    Object.assign(body, splitPart(v, group));
  }
  return body;
}

export function exactSum(v: FormValues, group: GroupLike): number {
  return group.members.reduce((sum, m) => sum + (parseAmount(v.exactTexts[m.id] ?? "") ?? 0), 0);
}

export { otherOf };
