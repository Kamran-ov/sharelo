import { parseAmount } from "./money";
import { otherOf, toApiPreset, type Who } from "./presets";
import type { Schedule } from "./recurrence";

/** Everything the rule sheet holds; pure data so the request body is testable without a DOM. */
export interface RuleValues {
  amountText: string;
  description: string;
  category: number;
  payerId: number;
  /** null = the stored split (exact/shares) cannot be shown here and is kept unless touched. */
  who: Who | null;
  percent: number;
  frequency: "monthly" | "yearly";
  day: number;
  month: number;
  startDate: string;
  endDate: string;
}

export interface RuleLike extends Schedule {
  id: number;
  description: string;
  amount_cents: number;
  payer: number;
  split_type: string;
  split_params: Record<string, unknown>;
  category: number;
  start_date: string;
  next_date: string;
  end_date: string | null;
  paused: boolean;
}

export const scheduleOf = (v: RuleValues): Schedule => ({
  frequency: v.frequency,
  day_of_month: v.day,
  month: v.frequency === "yearly" ? v.month : null,
});

/** The form's choice → the rule's split_type + split_params (the service form, not the expense presets). */
export function ruleSplit(who: Who, payerId: number, ids: number[], percent: number) {
  const preset = toApiPreset(who, payerId, ids, percent);
  if (who === "half") return { split_type: "equal", split_params: {} };
  if (who === "custom") {
    const other = otherOf(payerId, ids);
    return { split_type: "percentage", split_params: { basis_points: { [payerId]: percent * 100, [other]: (100 - percent) * 100 } } };
  }
  return { split_type: preset.preset, split_params: preset.params ?? {} };
}

/** Read-side only: stored rule split → the sheet's choice, or null when the sheet cannot show it. */
export function whoOfRule(rule: Pick<RuleLike, "split_type" | "split_params" | "payer">, memberCount: number): { who: Who; percent: number } | null {
  if (rule.split_type === "equal") return { who: memberCount === 2 ? "half" : "equal", percent: 50 };
  if (rule.split_type === "personal") return { who: "personal", percent: 100 };
  if (rule.split_type === "full_for_other" && memberCount === 2) return { who: "all_other", percent: 0 };
  const bp = (rule.split_params.basis_points as Record<string, number> | undefined)?.[String(rule.payer)];
  if (rule.split_type === "percentage" && memberCount === 2 && typeof bp === "number" && bp % 500 === 0) return { who: "custom", percent: bp / 100 };
  return null;
}

export function splitText(rule: Pick<RuleLike, "split_type" | "split_params" | "payer">, memberCount: number): string {
  const w = whoOfRule(rule, memberCount);
  switch (w?.who) {
    case "half":
      return "50/50";
    case "equal":
      return "equal";
    case "personal":
      return "personal";
    case "all_other":
      return "all for the other";
    case "custom":
      return `${w.percent}% / ${100 - w.percent}%`;
    default:
      return "custom split";
  }
}

export function ruleBody(v: RuleValues, ids: number[]): Record<string, unknown> {
  const sched = scheduleOf(v);
  return {
    description: v.description.trim(),
    amount_cents: parseAmount(v.amountText) ?? 0,
    payer: v.payerId,
    category: v.category,
    ...(v.who === null ? {} : ruleSplit(v.who, v.payerId, ids, v.percent)),
    frequency: sched.frequency,
    day_of_month: sched.day_of_month,
    month: sched.month,
    start_date: v.startDate,
    end_date: v.endDate === "" ? null : v.endDate,
  };
}

/** PATCH body: only what changed, so an amount edit cannot reschedule the rule. A payer change restates the split. */
export function rulePatchBody(v: RuleValues, initial: RuleValues, ids: number[]): Record<string, unknown> {
  const full = ruleBody(v, ids);
  const before = ruleBody(initial, ids);
  const splitTouched = v.who !== initial.who || v.percent !== initial.percent || v.payerId !== initial.payerId;
  const body: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(full)) {
    if (key === "split_type" || key === "split_params") {
      if (splitTouched && v.who !== null) body[key] = value;
    } else if (JSON.stringify(value) !== JSON.stringify(before[key])) body[key] = value;
  }
  return body;
}

/** The generated API type is loose about optional fields; the page works with this normalised shape. */
export function toRuleLike(r: {
  id: number;
  description: string;
  amount_cents: number;
  payer: number;
  split_type: string;
  split_params?: unknown;
  category: number;
  frequency: "monthly" | "yearly";
  day_of_month: number;
  month?: number | null;
  start_date: string;
  next_date: string;
  end_date?: string | null;
  paused?: boolean;
}): RuleLike {
  return {
    ...r,
    split_params: (r.split_params ?? {}) as Record<string, unknown>,
    month: r.month ?? null,
    end_date: r.end_date ?? null,
    paused: r.paused ?? false,
  };
}
