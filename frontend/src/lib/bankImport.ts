/**
 * Review list helpers. No split rule lives here: the suggestion and the per-category Shared split
 * both come from the server; this file only picks between them and formats.
 */

export type Params = Record<string, unknown>;
export type Decision = "shared" | "personal" | "skip";

export interface Triple {
  category: number;
  preset: string;
  params: Params;
}

interface SuggestionLike {
  category: number;
  preset: string;
  params: Params;
}

/**
 * What a row shows and sends. The suggested category keeps the suggestion's own split (a rule's or
 * the last choice's); any other category takes `categorySplits[category]` from the same response.
 * Mirrors `resolve_row` step 3 on the server. `null` when the server sent no split for it.
 */
export function rowChoice(
  suggestion: SuggestionLike,
  categorySplits: Record<string, { preset: string; params: Params }>,
  chosen?: number,
): Triple | null {
  if (chosen === undefined || chosen === suggestion.category) {
    return { category: suggestion.category, preset: suggestion.preset, params: suggestion.params };
  }
  const split = categorySplits[String(chosen)];
  return split ? { category: chosen, preset: split.preset, params: split.params } : null;
}

/** Human label for a Shared split, seen from `me` (the payer). */
export function splitLabel(preset: string, params: Params, me: number, memberIds: number[]): string {
  const two = memberIds.length === 2;
  switch (preset) {
    case "equal":
      return two ? "50/50" : `Equal (${memberIds.length})`;
    case "personal":
      return "Only me";
    case "full_for_other":
      return "All the other";
    case "percentage": {
      const bp = (params.basis_points ?? {}) as Record<string, number>;
      const mine = bp[String(me)];
      if (two && typeof mine === "number" && mine % 100 === 0) return `${mine / 100}/${100 - mine / 100}`;
      return "Custom %";
    }
    default:
      return "Custom";
  }
}

export function resolveBody(decision: Decision, triple: Triple, remember: boolean): Record<string, unknown> {
  if (decision === "skip") return { decision };
  if (decision === "personal") return { decision, category: triple.category, remember };
  return { decision, category: triple.category, preset: triple.preset, params: triple.params, remember };
}

export function resultLine(decision: Decision, categoryName: string, label: string): string {
  if (decision === "skip") return "Skipped";
  if (decision === "personal") return `Personal · ${categoryName}`;
  return `Shared · ${categoryName} · ${label}`;
}
