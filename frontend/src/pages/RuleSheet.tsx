import { useMemo, useState } from "react";

import type { CategoryNode, GroupDetail } from "../api";
import CategoryPicker from "../components/CategoryPicker";
import Sheet from "../components/Sheet";
import { Button, ErrorText, INPUT, SEG_TRACK, SEG_TRACK_WRAP, segItem } from "../components/ui";
import { localToday } from "../lib/dates";
import { formatCents, parseAmount } from "../lib/money";
import { otherOf, type Who } from "../lib/presets";
import { MONTH_NAMES, nextOccurrences } from "../lib/recurrence";
import { ruleBody, rulePatchBody, scheduleOf, whoOfRule, type RuleLike, type RuleValues } from "../lib/ruleBody";

const input = INPUT;
const seg = segItem;

export function initialRuleValues(group: GroupDetail, tree: CategoryNode[], editing?: RuleLike): RuleValues {
  const ids = group.members.map((m) => m.id);
  if (editing) {
    const split = whoOfRule(editing, ids.length);
    return {
      amountText: formatCents(editing.amount_cents),
      description: editing.description,
      category: editing.category,
      payerId: editing.payer,
      who: split?.who ?? null,
      percent: split?.percent ?? 50,
      frequency: editing.frequency,
      day: editing.day_of_month,
      month: editing.month ?? 1,
      startDate: editing.start_date,
      endDate: editing.end_date ?? "",
    };
  }
  const general = tree.flatMap((p) => p.children).find((k) => k.name === "General")?.id;
  const today = localToday();
  return {
    amountText: "",
    description: "",
    category: general ?? tree[0]?.children[0]?.id ?? 0,
    payerId: group.my_member_id ?? ids[0],
    who: ids.length === 2 ? "half" : "equal",
    percent: 50,
    frequency: "monthly",
    day: Number(today.slice(8, 10)),
    month: Number(today.slice(5, 7)),
    startDate: today,
    endDate: "",
  };
}

interface Props {
  group: GroupDetail;
  tree: CategoryNode[];
  editing?: RuleLike;
  error?: string | null;
  busy?: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
  onClose: () => void;
}

export default function RuleSheet({ group, tree, editing, error, busy, onSubmit, onClose }: Props) {
  const initial = useMemo(() => initialRuleValues(group, tree, editing), [group, tree, editing]);
  const [v, setV] = useState<RuleValues>(initial);
  const [picking, setPicking] = useState(false);
  const set = (patch: Partial<RuleValues>) => setV((cur) => ({ ...cur, ...patch }));

  const ids = group.members.map((m) => m.id);
  const two = ids.length === 2;
  const nameOf = (id: number) => (id === group.my_member_id ? "Me" : (group.members.find((m) => m.id === id)?.display_name ?? "?"));
  const categoryName = tree.flatMap((p) => p.children.map((k) => ({ ...k, parent: p.name }))).find((k) => k.id === v.category);
  const counts = useMemo(() => new Map<number, number>(), []);

  const cents = parseAmount(v.amountText);
  const dayOk = Number.isInteger(v.day) && v.day >= 1 && v.day <= 31;
  const endOk = v.endDate === "" || v.endDate >= v.startDate;
  const valid = cents !== null && v.description.trim() !== "" && v.category > 0 && dayOk && v.startDate !== "" && endOk;

  // The server moves the cursor to the first occurrence on or after max(next_date, today) after a schedule
  // change, and leaves it alone otherwise; a new rule starts at its start date.
  const sched = scheduleOf(v);
  const scheduleChanged = editing
    ? JSON.stringify(sched) !== JSON.stringify(scheduleOf(initial)) || v.startDate !== initial.startDate
    : true;
  const from = !editing ? v.startDate : scheduleChanged ? (editing.next_date > localToday() ? editing.next_date : localToday()) : editing.next_date;
  const preview = dayOk && v.startDate !== "" ? nextOccurrences(sched, from, 3) : [];

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    onSubmit(editing ? rulePatchBody(v, initial, ids) : ruleBody(v, ids));
  };

  return (
    <Sheet title={editing ? "Edit recurring expense" : "New recurring expense"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-sm text-muted">Amount ({group.currency})</span>
          <input
            className={`${input} h-14 font-heading text-xl font-semibold`}
            inputMode="decimal"
            autoFocus
            value={v.amountText}
            onChange={(e) => set({ amountText: e.target.value })}
            aria-invalid={v.amountText !== "" && cents === null}
          />
        </label>
        <label className="block">
          <span className="text-sm text-muted">Description</span>
          <input className={input} value={v.description} onChange={(e) => set({ description: e.target.value })} />
        </label>
        <div>
          <span className="text-sm text-muted">Category</span>
          <button type="button" className={`${input} text-left`} onClick={() => setPicking((p) => !p)} aria-expanded={picking}>
            {categoryName ? `${categoryName.parent} › ${categoryName.name}` : "Choose…"}
          </button>
          {picking && (
            <CategoryPicker
              tree={tree}
              counts={counts}
              current={v.category}
              onPick={(category) => {
                set({ category });
                setPicking(false);
              }}
            />
          )}
        </div>

        <div>
          <span className="text-sm text-muted">Who paid</span>
          {two ? (
            <div className={SEG_TRACK} role="group" aria-label="Who paid">
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
          <span className="text-sm text-muted">Who it&apos;s for</span>
          <div className={SEG_TRACK} role="group" aria-label="Who it's for">
            {(two
              ? ([["half", "50/50"], ["personal", "Only me"], ["all_other", `All ${nameOf(otherOf(v.payerId, ids))}`], ["custom", "Custom %"]] as [Who, string][])
              : ([["equal", "Equal among everyone"], ["personal", "Only me"]] as [Who, string][])
            ).map(([who, label]) => (
              <button key={who} type="button" aria-pressed={v.who === who} className={seg(v.who === who)} onClick={() => set({ who })}>
                {label}
              </button>
            ))}
          </div>
          {v.who === null && <p className="mt-1 text-sm text-muted">Custom split — kept as it is</p>}
          {two && v.who === "custom" && (
            <label className="mt-2 block">
              <span className="text-sm text-muted">
                {nameOf(v.payerId)} {v.percent}% · {nameOf(otherOf(v.payerId, ids))} {100 - v.percent}%
              </span>
              <input type="range" className="w-full" min={5} max={95} step={5} value={v.percent} onChange={(e) => set({ percent: Number(e.target.value) })} aria-label="Payer's percent" />
            </label>
          )}
        </div>

        <div>
          <span className="text-sm text-muted">Frequency</span>
          <div className={SEG_TRACK} role="group" aria-label="Frequency">
            {(["monthly", "yearly"] as const).map((f) => (
              <button key={f} type="button" aria-pressed={v.frequency === f} className={seg(v.frequency === f)} onClick={() => set({ frequency: f })}>
                {f === "monthly" ? "Monthly" : "Yearly"}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          {v.frequency === "yearly" && (
            <label className="block flex-1">
              <span className="text-sm text-muted">Month</span>
              <select className={input} value={v.month} onChange={(e) => set({ month: Number(e.target.value) })}>
                {MONTH_NAMES.map((name, i) => (
                  <option key={name} value={i + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block flex-1">
            <span className="text-sm text-muted">Day of month</span>
            <input
              className={input}
              inputMode="numeric"
              value={Number.isNaN(v.day) ? "" : v.day}
              onChange={(e) => set({ day: Number.parseInt(e.target.value, 10) })}
              aria-invalid={!dayOk}
            />
          </label>
        </div>
        <label className="block">
          <span className="text-sm text-muted">Start date</span>
          <input type="date" className={input} value={v.startDate} onChange={(e) => set({ startDate: e.target.value })} />
        </label>
        <label className="block">
          <span className="text-sm text-muted">End date (optional)</span>
          <input type="date" className={input} value={v.endDate} onChange={(e) => set({ endDate: e.target.value })} aria-invalid={!endOk} />
        </label>
        {preview.length > 0 && (
          <p className="break-words rounded-card border border-line bg-card p-3 text-sm" data-testid="preview">
            Next: {preview.join(", ")}
          </p>
        )}

        {error && (
          <p role="alert" className="break-words text-sm text-danger">
            {error}
          </p>
        )}
        <button type="submit" disabled={!valid || busy} className="min-h-14 w-full rounded-md bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50">
          Save
        </button>
      </form>
    </Sheet>
  );
}
