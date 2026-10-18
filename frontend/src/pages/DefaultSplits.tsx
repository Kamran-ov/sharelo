import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError, type CategoryDefaults, type CategoryNode, type GroupDetail } from "../api";
import { storedPercent } from "../lib/presets";

type Choice = "none" | "half" | "personal" | "all_other" | "custom" | "kept";

const LABELS: [Choice, string][] = [
  ["none", "No default"],
  ["half", "50/50"],
  ["personal", "Only me"],
  ["all_other", "All the other"],
  ["custom", "Custom %"],
];

function choiceOf(d: CategoryDefaults[string] | undefined): Choice {
  if (!d) return "none";
  if (d.preset === "equal" || d.preset === "half") return "half";
  if (d.preset === "personal") return "personal";
  if (d.preset === "full_for_other") return "all_other";
  if (d.preset === "percentage") return "custom";
  return "kept";
}

export default function DefaultSplits({ group }: { group: GroupDetail }) {
  const qc = useQueryClient();
  const tree = useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryNode[]>("GET", "/categories/") });
  const defaults = useQuery({ queryKey: ["defaults", group.id], queryFn: () => api<CategoryDefaults>("GET", `/groups/${group.id}/category-defaults/`) });
  const [saved, setSaved] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const me = group.my_member_id;
  if (!tree.data || !defaults.data || me === null) return null;

  const save = async (category: number, choice: Choice, percent: number) => {
    const next: Record<string, unknown> = { ...defaults.data };
    delete next[String(category)];
    if (choice === "half") next[category] = { preset: "equal", params: {} };
    if (choice === "personal") next[category] = { preset: "personal", params: {} };
    if (choice === "all_other") next[category] = { preset: "full_for_other", params: {} };
    if (choice === "custom") next[category] = { preset: "percentage", params: { percent_payer: percent } };
    try {
      setError(null);
      await api("PUT", `/groups/${group.id}/category-defaults/`, next);
      await qc.invalidateQueries({ queryKey: ["defaults", group.id] });
      setSaved(category);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail || e.code : "Could not save");
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Default split per category</h2>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {tree.data.map((parent) => (
        <div key={parent.id}>
          <h3 className="text-sm font-semibold text-slate-600">{parent.name}</h3>
          {parent.children.map((k) => {
            const current = defaults.data[String(k.id)];
            const choice = choiceOf(current);
            const percent = storedPercent(current?.params, me) ?? 50;
            const twoOnly = group.members.length !== 2;
            return (
              <div key={k.id} className="flex flex-wrap items-center gap-2 py-1" data-testid={`default-${k.id}`}>
                <span className="min-w-0 flex-1 break-words">{k.name}</span>
                <select
                  aria-label={`Default split for ${parent.name} › ${k.name}`}
                  className="min-h-11 rounded-lg border border-slate-300 px-2"
                  value={choice}
                  onChange={(e) => save(k.id, e.target.value as Choice, percent)}
                >
                  {LABELS.filter(([c]) => !(twoOnly && (c === "all_other" || c === "custom"))).map(([c, label]) => (
                    <option key={c} value={c}>
                      {label}
                    </option>
                  ))}
                  {choice === "kept" && <option value="kept">Other (kept)</option>}
                </select>
                {choice === "custom" && (
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={5}
                    aria-label={`Payer's percent for ${k.name}`}
                    className="min-h-11 w-20 rounded-lg border border-slate-300 px-2"
                    defaultValue={percent}
                    onBlur={(e) => save(k.id, "custom", Number(e.target.value))}
                  />
                )}
                {saved === k.id && <span className="text-xs text-emerald-700">Saved</span>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
