import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError, type CategoryNode, type GroupDetail, type ShopRule } from "../api";
import { splitLabel, type Params } from "../lib/bankImport";
import { storedPercent } from "../lib/presets";

type Who = "half" | "personal" | "all_other" | "custom" | "kept";

function whoOf(rule: ShopRule): Who {
  if (rule.preset === "equal") return "half";
  if (rule.preset === "personal") return "personal";
  if (rule.preset === "full_for_other") return "all_other";
  if (rule.preset === "percentage") return "custom";
  return "kept";
}

/** Same choices as the default-split selector; `kept` leaves a split the form cannot express unchanged. */
function presetBody(who: Who, percent: number, rule: ShopRule): { preset: string; params: Params } {
  if (who === "half") return { preset: "equal", params: {} };
  if (who === "personal") return { preset: "personal", params: {} };
  if (who === "all_other") return { preset: "full_for_other", params: {} };
  if (who === "custom") return { preset: "percentage", params: { percent_payer: percent } };
  return { preset: rule.preset, params: rule.params as Params };
}

function RuleEditor({ group, rule, tree, onClose }: { group: GroupDetail; rule: ShopRule; tree: CategoryNode[]; onClose: () => void }) {
  const qc = useQueryClient();
  const me = group.my_member_id ?? 0;
  const two = group.members.length === 2;
  const [text, setText] = useState(rule.match_text);
  const [category, setCategory] = useState(rule.category);
  const [who, setWho] = useState<Who>(whoOf(rule));
  const [percent, setPercent] = useState(storedPercent(rule.params as Params, me) ?? 50);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      await api("PATCH", `/groups/${group.id}/shop-rules/${rule.id}/`, { match_text: text, category, ...presetBody(who, percent, rule) });
      await qc.invalidateQueries({ queryKey: ["shop-rules", group.id] });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail || e.code : "Could not save");
    }
  };
  return (
    <form
      className="space-y-2 rounded-lg bg-slate-50 p-3"
      aria-label={`Edit rule ${rule.match_text}`}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label className="block">
        <span className="text-sm">Shop text</span>
        <input className="min-h-11 w-full rounded-lg border border-slate-300 px-3" value={text} onChange={(e) => setText(e.target.value)} required />
      </label>
      <select aria-label="Rule category" className="min-h-11 w-full rounded-lg border border-slate-300 px-2" value={category} onChange={(e) => setCategory(Number(e.target.value))}>
        {tree.map((p) => (
          <optgroup key={p.id} label={p.name}>
            {p.children.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <select aria-label="Rule split" className="min-h-11 w-full rounded-lg border border-slate-300 px-2" value={who} onChange={(e) => setWho(e.target.value as Who)}>
        <option value="half">{two ? "50/50" : "Equal"}</option>
        <option value="personal">Only me</option>
        {two && <option value="all_other">All the other</option>}
        {two && <option value="custom">Custom %</option>}
        {who === "kept" && <option value="kept">Other (kept)</option>}
      </select>
      {who === "custom" && (
        <input
          type="number"
          min={0}
          max={100}
          step={5}
          aria-label="Payer's percent"
          className="min-h-11 w-24 rounded-lg border border-slate-300 px-2"
          value={percent}
          onChange={(e) => setPercent(Number(e.target.value))}
        />
      )}
      {error && (
        <p role="alert" className="break-words text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <button type="button" className="min-h-11 rounded-lg border border-slate-300" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="min-h-11 rounded-lg bg-emerald-600 text-white">
          Save
        </button>
      </div>
    </form>
  );
}

export default function ShopRules({ group }: { group: GroupDetail }) {
  const qc = useQueryClient();
  const tree = useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryNode[]>("GET", "/categories/") });
  const rules = useQuery({ queryKey: ["shop-rules", group.id], queryFn: () => api<ShopRule[]>("GET", `/groups/${group.id}/shop-rules/`) });
  const [editing, setEditing] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);
  if (!rules.data || !tree.data) return null;
  const memberIds = group.members.map((m) => m.id);
  const remove = async (id: number) => {
    await api("DELETE", `/groups/${group.id}/shop-rules/${id}/`);
    setConfirm(null);
    await qc.invalidateQueries({ queryKey: ["shop-rules", group.id] });
  };
  return (
    <div className="space-y-2">
      <h2 className="text-lg font-semibold">Shop rules</h2>
      {rules.data.length === 0 && <p className="text-sm text-slate-600">None yet. Tick "Remember for this shop" when you review a bank file.</p>}
      <ul className="space-y-2">
        {rules.data.map((r) => (
          <li key={r.id} data-testid="shop-rule" className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 break-words">
                <span className="font-medium">{r.match_text}</span> → {r.category_name} · {splitLabel(r.preset, r.params as Params, group.my_member_id ?? 0, memberIds)}
                {r.last_used_at && <span className="block text-xs text-slate-500">last used {r.last_used_at.slice(0, 10)}</span>}
              </span>
              <button type="button" className="min-h-11 px-2 text-emerald-700" onClick={() => setEditing(r.id)}>
                Edit
              </button>
              <button type="button" className="min-h-11 px-2 text-red-700" onClick={() => setConfirm(r.id)}>
                Delete
              </button>
            </div>
            {confirm === r.id && (
              <div role="alertdialog" aria-label="Confirm delete" className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-2 text-sm">
                <span>Delete the rule for {r.match_text}?</span>
                <span className="flex gap-2">
                  <button type="button" className="min-h-11 px-2" onClick={() => setConfirm(null)}>
                    Keep
                  </button>
                  <button type="button" className="min-h-11 px-2 font-semibold text-red-700" onClick={() => void remove(r.id)}>
                    Delete it
                  </button>
                </span>
              </div>
            )}
            {editing === r.id && <RuleEditor group={group} rule={r} tree={tree.data} onClose={() => setEditing(null)} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
