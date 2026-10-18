import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, ApiError, type CategoryDefaults, type CategoryNode, type ExpensePage, type ExpenseRow, type GroupDetail } from "../api";
import Toast from "../components/Toast";
import { monthKey, monthLabel } from "../lib/dates";
import type { FormValues } from "../lib/expenseBody";
import { formatCents, parseAmount } from "../lib/money";
import { shareFor } from "../lib/presets";
import ExpenseSheet, { type SheetSubmit } from "./ExpenseSheet";

interface Pending {
  tempId: number;
  description: string;
  date: string;
  category: number;
  cents: number | null;
  currency: string;
  preview: number | null;
}

type SheetState = { kind: "add"; draft?: FormValues; error?: string | null } | { kind: "edit"; row: ExpenseRow } | null;

const errorText = (e: unknown) => (e instanceof ApiError ? e.detail || e.code : "Something went wrong");

export function shareText(row: ExpenseRow, me: number | null): string {
  if (me === null) return "";
  const share = shareFor(me, row.payers, row.splits, row.split_type);
  switch (share.kind) {
    case "owe":
      return `you owe ${formatCents(share.cents)}`;
    case "lent":
      return `you lent ${formatCents(share.cents)}`;
    case "personal":
      return "personal";
    case "settled":
      return "settled";
    case "not_involved":
      return "not involved";
  }
}

export default function Expenses() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const [sheet, setSheet] = useState<SheetState>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [toast, setToast] = useState<{ id: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const counter = useRef(0);
  const base = `/groups/${group.id}`;

  const list = useInfiniteQuery({
    queryKey: ["expenses", group.id],
    queryFn: ({ pageParam }) => api<ExpensePage>("GET", `${base}/expenses/?page=${pageParam}`),
    initialPageParam: 1,
    getNextPageParam: (last, all) => (all.reduce((n, p) => n + p.results.length, 0) < last.count ? all.length + 1 : undefined),
  });
  const tree = useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryNode[]>("GET", "/categories/") });
  const defaults = useQuery({ queryKey: ["defaults", group.id], queryFn: () => api<CategoryDefaults>("GET", `${base}/category-defaults/`) });

  const categoryName = useMemo(() => {
    const names = new Map<number, string>();
    for (const p of tree.data ?? []) for (const k of p.children) names.set(k.id, k.name);
    return names;
  }, [tree.data]);
  const memberName = (id: number) => group.members.find((m) => m.id === id)?.display_name ?? "?";

  const pages = list.data?.pages ?? [];
  const rows = useMemo(() => pages.flatMap((p) => p.results), [pages]);
  const firstPage = pages[0]?.results;
  const totals = useMemo(() => Object.assign({}, ...pages.map((p) => p.month_totals)) as Record<string, number>, [pages]);

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ["expenses", group.id] }), qc.invalidateQueries({ queryKey: ["balances", group.id] })]);

  const add = async (s: SheetSubmit) => {
    const tempId = -++counter.current;
    const { values } = s;
    setPending((p) => [
      { tempId, description: values.description.trim(), date: values.date, category: values.category, cents: parseAmount(values.amountText), currency: values.currency, preview: s.foreignPreview },
      ...p,
    ]);
    setSheet(null);
    try {
      const row = await api<ExpenseRow>("POST", `${base}/expenses/`, s.body);
      setToast({ id: row.id });
      await refresh();
    } catch (e) {
      setSheet({ kind: "add", draft: values, error: errorText(e) });
    } finally {
      setPending((p) => p.filter((x) => x.tempId !== tempId));
    }
  };

  const edit = async (row: ExpenseRow, s: SheetSubmit) => {
    setBusy(true);
    setEditError(null);
    try {
      await api("PATCH", `${base}/expenses/${row.id}/`, s.body);
      await refresh();
      setSheet(null);
    } catch (e) {
      setEditError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: ExpenseRow) => {
    setBusy(true);
    try {
      await api("DELETE", `${base}/expenses/${row.id}/`);
      await refresh();
      setSheet(null);
    } catch (e) {
      setEditError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!toast) return;
    const { id } = toast;
    setToast(null);
    await api("DELETE", `${base}/expenses/${id}/`);
    await refresh();
  };
  const closeToast = useCallback(() => setToast(null), []);

  type Item = { pending: Pending } | { row: ExpenseRow };
  const items: (Item & { date: string })[] = [
    ...pending.map((p) => ({ pending: p, date: p.date })),
    ...rows.map((r) => ({ row: r, date: r.date })),
  ].sort((a, b) => b.date.localeCompare(a.date));
  const months = [...new Set(items.map((i) => monthKey(i.date)))];

  const open = (row: ExpenseRow) => {
    setEditError(null);
    setSheet({ kind: "edit", row });
  };

  return (
    <section className="p-4">
      {list.isPending && <p className="text-slate-500">Loading…</p>}
      {list.isError && <p role="alert">Could not load expenses.</p>}
      {list.isSuccess && items.length === 0 && <p className="text-slate-600">No expenses yet.</p>}
      {months.map((m) => (
        <div key={m} className="mb-4">
          <h2 className="flex items-baseline justify-between border-b border-slate-200 pb-1 font-semibold" data-testid={`month-${m}`}>
            <span>{monthLabel(m)}</span>
            <span className="text-sm text-slate-600" data-testid={`month-total-${m}`}>
              {m in totals ? `${formatCents(totals[m])} ${group.currency}` : ""}
            </span>
          </h2>
          <ul>
            {items
              .filter((i) => monthKey(i.date) === m)
              .map((item) =>
                "pending" in item ? (
                  <li key={item.pending.tempId} aria-busy="true" className="border-b border-slate-100 py-2 text-slate-500">
                    <div className="flex justify-between gap-2">
                      <span className="break-words">{item.pending.description}</span>
                      <span>
                        {item.pending.preview !== null
                          ? `≈ ${formatCents(item.pending.preview)} ${group.currency}`
                          : `${formatCents(item.pending.cents ?? 0)} ${item.pending.currency}`}
                      </span>
                    </div>
                    <div className="text-sm">saving…</div>
                  </li>
                ) : (
                  <li key={item.row.id} data-testid="expense-row" className="border-b border-slate-100">
                    <button type="button" className="w-full min-h-14 py-2 text-left" onClick={() => open(item.row)}>
                      <div className="flex justify-between gap-2">
                        <span className="break-words font-medium">{item.row.description}</span>
                        <span className="shrink-0">{formatCents(item.row.amount_cents)}</span>
                      </div>
                      <div className="flex justify-between gap-2 text-sm text-slate-600">
                        <span className="break-words">
                          {categoryName.get(item.row.category) ?? ""} · {item.row.date}
                        </span>
                        {item.row.original_currency && item.row.original_currency !== group.currency && item.row.original_amount_cents != null && (
                          <span className="shrink-0 text-xs">
                            {formatCents(item.row.original_amount_cents)} {item.row.original_currency}
                          </span>
                        )}
                      </div>
                      <div className="flex justify-between gap-2 text-sm">
                        <span>{item.row.payers.length > 1 ? "multiple payers" : item.row.payers[0]?.member === group.my_member_id ? "you paid" : `${memberName(item.row.payers[0]?.member)} paid`}</span>
                        <span className="text-slate-700">{shareText(item.row, group.my_member_id)}</span>
                      </div>
                    </button>
                  </li>
                ),
              )}
          </ul>
        </div>
      ))}
      {list.hasNextPage && (
        <button type="button" className="min-h-11 w-full rounded-lg border border-slate-300" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
          Load more
        </button>
      )}
      <div className="pointer-events-none sticky bottom-20 flex justify-end pt-4">
        <button
          type="button"
          aria-label="Add expense"
          className="pointer-events-auto flex size-14 items-center justify-center rounded-full bg-emerald-600 text-3xl text-white shadow-lg"
          disabled={!tree.data || !defaults.data}
          onClick={() => setSheet({ kind: "add" })}
        >
          +
        </button>
      </div>

      {sheet && tree.data && defaults.data && (
        <ExpenseSheet
          key={sheet.kind === "edit" ? sheet.row.id : "add"}
          group={group}
          recent={firstPage ?? []}
          tree={tree.data}
          defaults={defaults.data}
          editing={sheet.kind === "edit" ? sheet.row : undefined}
          draft={sheet.kind === "add" ? sheet.draft : undefined}
          error={sheet.kind === "add" ? sheet.error : editError}
          busy={busy}
          onSubmit={(s) => (sheet.kind === "edit" ? edit(sheet.row, s) : add(s))}
          onDelete={sheet.kind === "edit" ? () => remove(sheet.row) : undefined}
          onClose={() => setSheet(null)}
        />
      )}
      {toast && <Toast message="Saved" onUndo={undo} onDone={closeToast} />}
    </section>
  );
}
