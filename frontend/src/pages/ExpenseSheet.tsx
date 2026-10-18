import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api, ApiError, type CategoryDefaults, type CategoryNode, type ExpenseRow, type GroupDetail, type RateOut } from "../api";
import CategoryPicker from "../components/CategoryPicker";
import Sheet from "../components/Sheet";
import { buildCreateBody, buildPatchBody, exactSum, parseRate, type FormValues } from "../lib/expenseBody";
import { localToday } from "../lib/dates";
import { formatCents, parseAmount } from "../lib/money";
import { descriptionSuggestions, detectPreset, otherOf, whoFromDefault, type Who } from "../lib/presets";
import { CURRENCIES } from "./Groups";

const input = "min-h-11 w-full rounded-lg border border-slate-300 px-3";
const seg = (on: boolean) =>
  `min-h-11 flex-1 rounded-lg border px-2 text-sm ${on ? "border-emerald-600 bg-emerald-50 font-semibold" : "border-slate-300"}`;

export interface SheetSubmit {
  values: FormValues;
  body: Record<string, unknown>;
  /** Only for add: what the pending row shows before the server answers. */
  foreignPreview: number | null;
}

interface Props {
  group: GroupDetail;
  recent: ExpenseRow[];
  tree: CategoryNode[];
  defaults: CategoryDefaults;
  editing?: ExpenseRow;
  draft?: FormValues;
  error?: string | null;
  busy?: boolean;
  onSubmit: (s: SheetSubmit) => void;
  onDelete?: () => void;
  onClose: () => void;
}

function countsOf(rows: ExpenseRow[]) {
  const counts = new Map<number, number>();
  for (const r of rows) counts.set(r.category, (counts.get(r.category) ?? 0) + 1);
  return counts;
}

export function initialValues(
  group: GroupDetail,
  recent: ExpenseRow[],
  tree: CategoryNode[],
  defaults: CategoryDefaults,
  editing?: ExpenseRow,
): FormValues {
  const ids = group.members.map((m) => m.id);
  const blank = { exactTexts: {}, sharesTexts: {}, subset: ids, mode: "none" as const };
  if (editing) {
    const payerId = editing.payers[0]?.member ?? group.my_member_id ?? ids[0];
    const foreign = editing.original_currency != null && editing.original_currency !== group.currency && editing.original_amount_cents != null;
    const detected = detectPreset(editing.amount_cents, payerId, ids, editing.splits);
    const exactTexts = Object.fromEntries(
      ids.map((id) => [id, formatCents(editing.splits.find((s) => s.member === id)?.owed_cents ?? 0)]),
    );
    return {
      ...blank,
      amountText: formatCents(foreign ? (editing.original_amount_cents as number) : editing.amount_cents),
      currency: foreign ? (editing.original_currency as string) : group.currency,
      manualRate: "",
      description: editing.description,
      category: editing.category,
      date: editing.date,
      payerId,
      who: detected?.who ?? null,
      percent: detected?.percent ?? 50,
      mode: detected ? "none" : "exact",
      exactTexts,
    };
  }
  const general = tree.flatMap((p) => p.children).find((k) => k.name === "General")?.id;
  const category = recent[0]?.category ?? general ?? tree[0]?.children[0]?.id ?? 0;
  const { who, percent } = whoFromDefault(defaults[String(category)], ids.length, group.my_member_id ?? ids[0]);
  return {
    ...blank,
    amountText: "",
    currency: group.currency,
    manualRate: "",
    description: "",
    category,
    date: localToday(),
    payerId: group.my_member_id ?? ids[0],
    who,
    percent,
  };
}

export default function ExpenseSheet({ group, recent, tree, defaults, editing, draft, error, busy, onSubmit, onDelete, onClose }: Props) {
  const initial = useMemo(() => initialValues(group, recent, tree, defaults, editing), [group, recent, tree, defaults, editing]);
  const [v, setV] = useState<FormValues>(draft ?? initial);
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const set = (patch: Partial<FormValues>) => setV((cur) => ({ ...cur, ...patch }));

  const ids = group.members.map((m) => m.id);
  const two = ids.length === 2;
  const nameOf = (id: number) => (id === group.my_member_id ? "Me" : (group.members.find((m) => m.id === id)?.display_name ?? "?"));
  const otherName = nameOf(otherOf(v.payerId, ids));
  const counts = useMemo(() => countsOf(recent), [recent]);
  const suggestions = useMemo(() => descriptionSuggestions(recent), [recent]);
  const categoryName = tree.flatMap((p) => p.children.map((k) => ({ ...k, parent: p.name }))).find((k) => k.id === v.category);

  const foreign = v.currency !== group.currency;
  const cents = parseAmount(v.amountText);
  const rateQuery = useQuery({
    queryKey: ["rate", group.id, v.currency, v.date],
    queryFn: () => api<RateOut>("GET", `/groups/${group.id}/rate/?currency=${v.currency}&date=${v.date}`),
    enabled: foreign && !editing,
    retry: false,
  });
  const noRate = rateQuery.error instanceof ApiError && rateQuery.error.code === "no_rate";
  const manual = parseRate(v.manualRate);
  const rate = rateQuery.data ? rateQuery.data.rate : noRate ? manual : null;
  const preview = foreign && cents !== null && rate ? Math.round(cents * Number(rate)) : null;

  const pickCategory = (category: number) => {
    const next = whoFromDefault(defaults[String(category)], ids.length, v.payerId);
    set({ category, who: next.who, percent: next.percent, mode: "none" });
    setPicking(false);
  };

  const exactOk = v.mode !== "exact" || (cents !== null && exactSum(v, group) === cents);
  const subsetOk = v.mode !== "subset" || v.subset.length > 0;
  const rateOk = !foreign || editing !== undefined || rate !== null;
  const valid = cents !== null && v.description.trim() !== "" && exactOk && subsetOk && rateOk && v.category > 0;
  const multiPayer = (editing?.payers.length ?? 0) > 1;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    const body = editing ? buildPatchBody(v, initial, group) : buildCreateBody(v, group, noRate ? manual : null);
    onSubmit({ values: v, body, foreignPreview: preview });
  };

  if (multiPayer && editing) {
    return (
      <Sheet title="Edit expense" onClose={onClose}>
        <p className="mb-4">{editing.description}</p>
        <p role="note" className="mb-4 rounded-lg bg-slate-100 p-3 text-sm">
          multiple payers — edit not supported yet
        </p>
        <DeleteBlock confirm={confirmDelete} setConfirm={setConfirmDelete} onDelete={onDelete} />
      </Sheet>
    );
  }

  return (
    <Sheet title={editing ? "Edit expense" : "New expense"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-sm">Amount ({v.currency})</span>
          <input
            className={`${input} text-2xl`}
            inputMode="decimal"
            autoFocus
            value={v.amountText}
            onChange={(e) => set({ amountText: e.target.value })}
            aria-invalid={v.amountText !== "" && cents === null}
          />
        </label>
        {foreign && cents !== null && (
          <p className="text-sm text-slate-600" data-testid="converted">
            {preview !== null ? `≈ ${formatCents(preview)} ${group.currency}` : rateQuery.isPending && !editing ? "Looking up the rate…" : ""}
          </p>
        )}
        {foreign && noRate && !editing && (
          <label className="block">
            <p role="alert" className="text-sm text-red-700">
              No rate for {v.currency} on {v.date}. Enter one ({group.currency} per 1 {v.currency}).
            </p>
            <input className={input} inputMode="decimal" aria-label="Manual rate" value={v.manualRate} onChange={(e) => set({ manualRate: e.target.value })} />
          </label>
        )}

        <label className="block">
          <span className="text-sm">Description</span>
          <input className={input} value={v.description} onChange={(e) => set({ description: e.target.value })} />
        </label>
        {suggestions.length > 0 && !editing && v.description === "" && (
          <div className="flex flex-wrap gap-2" aria-label="Suggestions">
            {suggestions.slice(0, 6).map((s) => (
              <button
                key={s.description}
                type="button"
                className="min-h-11 rounded-full border border-slate-300 px-3 text-sm"
                onClick={() => {
                  const next = whoFromDefault(defaults[String(s.category)], ids.length, v.payerId);
                  set({ description: s.description, category: s.category, who: next.who, percent: next.percent, mode: "none" });
                }}
              >
                {s.description}
              </button>
            ))}
          </div>
        )}

        <div>
          <span className="text-sm">Category</span>
          <button type="button" className={`${input} text-left`} onClick={() => setPicking((p) => !p)} aria-expanded={picking}>
            {categoryName ? `${categoryName.parent} › ${categoryName.name}` : "Choose…"}
          </button>
          {picking && <CategoryPicker tree={tree} counts={counts} current={v.category} onPick={pickCategory} />}
        </div>

        <label className="block">
          <span className="text-sm">Date</span>
          <input type="date" className={input} value={v.date} onChange={(e) => set({ date: e.target.value })} />
        </label>

        <div>
          <span className="text-sm">Who paid</span>
          {two ? (
            <div className="flex gap-2" role="group" aria-label="Who paid">
              {ids.map((id) => (
                <button key={id} type="button" aria-pressed={v.payerId === id} className={seg(v.payerId === id)} onClick={() => set({ payerId: id })}>
                  {nameOf(id)}
                </button>
              ))}
            </div>
          ) : (
            <select className={input} value={v.payerId} onChange={(e) => set({ payerId: Number(e.target.value) })} aria-label="Who paid">
              {ids.map((id) => (
                <option key={id} value={id}>
                  {nameOf(id)}
                </option>
              ))}
            </select>
          )}
        </div>

        <div>
          <span className="text-sm">Who it&apos;s for</span>
          <div className="flex gap-2" role="group" aria-label="Who it's for">
            {(two
              ? ([["half", "50/50"], ["personal", "Only me"], ["all_other", `All ${otherName}`], ["custom", "Custom %"]] as [Who, string][])
              : ([["equal", "Equal among everyone"], ["personal", "Only me"]] as [Who, string][])
            ).map(([who, label]) => (
              <button key={who} type="button" aria-pressed={v.who === who && v.mode === "none"} className={seg(v.who === who && v.mode === "none")} onClick={() => set({ who, mode: "none" })}>
                {label}
              </button>
            ))}
          </div>
          {v.who === null && v.mode === "exact" && <p className="mt-1 text-sm text-slate-600">Custom split — edit in Advanced</p>}
          {two && v.who === "custom" && v.mode === "none" && (
            <label className="mt-2 block">
              <span className="text-sm">
                {nameOf(v.payerId)} {v.percent}% · {nameOf(otherOf(v.payerId, ids))} {100 - v.percent}%
              </span>
              <input type="range" className="w-full" min={0} max={100} step={5} value={v.percent} onChange={(e) => set({ percent: Number(e.target.value) })} aria-label="Payer's percent" />
            </label>
          )}
        </div>

        <details open={v.mode !== "none"} className="rounded-lg border border-slate-200 p-3">
          <summary className="min-h-11 cursor-pointer leading-[2.75rem]">Advanced</summary>
          <div className="space-y-3">
            <label className="block">
              <span className="text-sm">Currency</span>
              <select className={input} value={v.currency} disabled={!!editing} onChange={(e) => set({ currency: e.target.value, mode: v.mode === "exact" ? "none" : v.mode })}>
                {[group.currency, ...CURRENCIES.filter((c) => c !== group.currency)].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Split mode">
              {([["none", "Preset"], ["exact", "Exact amounts"], ["shares", "Shares"], ["subset", "Equal among some"]] as const).map(([mode, label]) => (
                <button key={mode} type="button" disabled={mode === "exact" && foreign} aria-pressed={v.mode === mode} className={seg(v.mode === mode)} onClick={() => set({ mode })}>
                  {label}
                </button>
              ))}
            </div>
            {v.mode === "exact" &&
              group.members.map((m) => (
                <label key={m.id} className="flex items-center gap-2">
                  <span className="w-24 break-words text-sm">{nameOf(m.id)}</span>
                  <input className={input} inputMode="decimal" aria-label={`Exact ${m.display_name}`} value={v.exactTexts[m.id] ?? ""} onChange={(e) => set({ exactTexts: { ...v.exactTexts, [m.id]: e.target.value } })} />
                </label>
              ))}
            {v.mode === "exact" && (
              <p className="text-sm text-slate-600">{cents === null ? "" : `Remaining ${formatCents(cents - exactSum(v, group))}`}</p>
            )}
            {v.mode === "shares" &&
              group.members.map((m) => (
                <label key={m.id} className="flex items-center gap-2">
                  <span className="w-24 break-words text-sm">{nameOf(m.id)}</span>
                  <input className={input} inputMode="numeric" aria-label={`Shares ${m.display_name}`} value={v.sharesTexts[m.id] ?? ""} onChange={(e) => set({ sharesTexts: { ...v.sharesTexts, [m.id]: e.target.value } })} />
                </label>
              ))}
            {v.mode === "subset" &&
              group.members.map((m) => (
                <label key={m.id} className="flex min-h-11 items-center gap-3">
                  <input type="checkbox" className="size-5" checked={v.subset.includes(m.id)} onChange={(e) => set({ subset: e.target.checked ? [...v.subset, m.id] : v.subset.filter((x) => x !== m.id) })} />
                  <span className="break-words">{nameOf(m.id)}</span>
                </label>
              ))}
          </div>
        </details>

        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <button type="submit" disabled={!valid || busy} className="min-h-12 w-full rounded-lg bg-emerald-600 font-medium text-white disabled:bg-slate-300">
          Save
        </button>
        {editing && <DeleteBlock confirm={confirmDelete} setConfirm={setConfirmDelete} onDelete={onDelete} />}
      </form>
    </Sheet>
  );
}

function DeleteBlock({ confirm, setConfirm, onDelete }: { confirm: boolean; setConfirm: (b: boolean) => void; onDelete?: () => void }) {
  if (!confirm) {
    return (
      <button type="button" className="min-h-11 w-full rounded-lg border border-red-300 text-red-700" onClick={() => setConfirm(true)}>
        Delete
      </button>
    );
  }
  return (
    <div role="alertdialog" aria-label="Confirm delete" className="space-y-2 rounded-lg border border-red-300 p-3">
      <p>Delete this expense?</p>
      <div className="flex gap-2">
        <button type="button" className="min-h-11 flex-1 rounded-lg border border-slate-300" onClick={() => setConfirm(false)}>
          Keep
        </button>
        <button type="button" className="min-h-11 flex-1 rounded-lg bg-red-600 text-white" onClick={onDelete}>
          Delete for good
        </button>
      </div>
    </div>
  );
}
