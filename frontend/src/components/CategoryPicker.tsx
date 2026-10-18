import { useState } from "react";

import type { CategoryNode } from "../api";
import { orderByUse } from "../lib/presets";

/** Two-level picker: parents as tabs (most used first), children as a grid (most used first). */
export default function CategoryPicker({
  tree,
  counts,
  current,
  onPick,
}: {
  tree: CategoryNode[];
  counts: Map<number, number>;
  current: number;
  onPick: (id: number) => void;
}) {
  const used = (c: CategoryNode) => c.children.reduce((n, k) => n + (counts.get(k.id) ?? 0), 0);
  const parents = orderByUse(
    tree.map((c) => ({ ...c, id: c.id })),
    new Map(tree.map((c) => [c.id, used(c)])),
  );
  const currentParent = tree.find((p) => p.children.some((k) => k.id === current))?.id ?? parents[0]?.id;
  const [tab, setTab] = useState(currentParent);
  const open = tree.find((p) => p.id === tab);
  return (
    <div className="space-y-3">
      <div role="tablist" className="flex flex-wrap gap-2">
        {parents.map((p) => (
          <button
            key={p.id}
            role="tab"
            type="button"
            aria-selected={p.id === tab}
            className={`min-h-11 rounded-full border px-3 text-sm ${p.id === tab ? "border-emerald-600 bg-emerald-50 font-semibold" : "border-slate-300"}`}
            onClick={() => setTab(p.id)}
          >
            {p.name}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2" role="listbox" aria-label="Sub-categories">
        {open && orderByUse(open.children, counts).map((k) => (
          <button
            key={k.id}
            type="button"
            role="option"
            aria-selected={k.id === current}
            className={`min-h-11 break-words rounded-lg border px-2 text-sm ${k.id === current ? "border-emerald-600 bg-emerald-50 font-semibold" : "border-slate-300"}`}
            onClick={() => onPick(k.id)}
          >
            {k.name}
          </button>
        ))}
      </div>
    </div>
  );
}
