import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api, ApiError, type Balances, type CategoryDefaults, type CategoryNode, type ExpensePage, type ExpenseRow, type GroupDetail, type ReviewList } from "../api";
import Icon, { categoryIcon } from "../components/Icon";
import Toast from "../components/Toast";
import { Amount, Button, Card, Fab, List, ListRow, type Tone } from "../components/ui";
import { topCardParts } from "../lib/balances";
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

const SHARE_TONE: Record<string, Tone> = { owe: "owe", lent: "owed" };

/** The row's share in words and money colour; the text is exactly shareText(). */
function ShareAmount({ row, me }: { row: ExpenseRow; me: number | null }) {
  if (me === null) return null;
  const share = shareFor(me, row.payers, row.splits, row.split_type);
  if (share.kind === "owe" || share.kind === "lent")
    return <Amount tone={SHARE_TONE[share.kind]} label={share.kind === "owe" ? "you owe" : "you lent"} figure={formatCents(share.cents)} className="text-md" />;
  return <Amount tone="neutral" label={shareText(row, me)} className="text-sm font-medium" />;
}

const HERO_LINES = 3;

/** Overall balance (Balances' top-card words) and who owes whom, from GET balances/. */
function Hero({ data, me, name }: { data: Balances; me: number; name: (id: number) => string }) {
  const mine = data.members.find((m) => m.member_id === me);
  const card = topCardParts(mine?.net ?? 0);
  const lines = data.transfers
    .filter((t) => t.from_member === me || t.to_member === me)
    .map((t) => (t.to_member === me ? `${name(t.from_member)} owes you ${formatCents(t.amount_cents)}` : `you owe ${name(t.to_member)} ${formatCents(t.amount_cents)}`));
  return (
    <Card variant="hero" className="mt-1 flex flex-col gap-1 p-5" data-testid="hero">
      <span className="text-sm" data-testid="hero-label">
        Overall, {card.label}
      </span>
      {card.figure !== null && (
        <span className="break-words font-heading text-2xl font-semibold tracking-[-0.5px]" data-testid="hero-total">
          {card.figure} {data.currency}
        </span>
      )}
      {lines.slice(0, HERO_LINES).map((l) => (
        <span key={l} className="break-words text-sm" data-testid="hero-line">
          {l}
        </span>
      ))}
      {lines.length > HERO_LINES && <span className="text-sm">+{lines.length - HERO_LINES} more</span>}
    </Card>
  );
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
  const bankRows = useQuery({ queryKey: ["bank-rows", group.id], queryFn: () => api<ReviewList>("GET", `${base}/bank-rows/`) });
  const toReview = bankRows.data?.rows.length ?? 0;
  const defaults = useQuery({ queryKey: ["defaults", group.id], queryFn: () => api<CategoryDefaults>("GET", `${base}/category-defaults/`) });

  const categoryName = useMemo(() => {
    const names = new Map<number, string>();
    for (const p of tree.data ?? []) for (const k of p.children) names.set(k.id, k.name);
    return names;
  }, [tree.data]);
  const parentName = useMemo(() => {
    const names = new Map<number, string>();
    for (const p of tree.data ?? []) for (const k of p.children) names.set(k.id, p.name);
    return names;
  }, [tree.data]);
  const balances = useQuery({ queryKey: ["balances", group.id], queryFn: () => api<Balances>("GET", `${base}/balances/`), retry: false });
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
    setToast(null); // the toast would sit on top of the sheet's Save button
    setSheet({ kind: "edit", row });
  };

  return (
    <section className="px-5 pb-4">
      {balances.data && group.my_member_id !== null && <Hero data={balances.data} me={group.my_member_id} name={memberName} />}
      <Link to={`/g/${group.id}/bank-import`} className="mt-3 flex min-h-11 items-center justify-between gap-2 rounded-md border border-line bg-card px-4 text-sm font-medium">
        <span className="flex items-center gap-2">
          <Icon name="upload" size={18} />
          Import bank file
        </span>
        {toReview > 0 && (
          <span data-testid="to-review" className="rounded-pill bg-primary px-2.5 py-0.5 text-xs font-semibold text-on-primary">
            {toReview} to review
          </span>
        )}
      </Link>
      {list.isPending && <p className="pt-4 text-muted">Loading…</p>}
      {list.isError && <p role="alert" className="pt-4">Could not load expenses.</p>}
      {list.isSuccess && items.length === 0 && <p className="pt-4 text-muted">No expenses yet.</p>}
      {months.map((m) => (
        <div key={m}>
          <h2 className="flex items-baseline justify-between gap-2 px-1 pb-2 pt-5" data-testid={`month-${m}`}>
            <span className="font-heading text-md font-semibold">{monthLabel(m)}</span>
            <span className="text-sm font-normal text-muted" data-testid={`month-total-${m}`}>
              {m in totals ? `${formatCents(totals[m])} ${group.currency}` : ""}
            </span>
          </h2>
          <List>
            {items
              .filter((i) => monthKey(i.date) === m)
              .map((item) =>
                "pending" in item ? (
                  <li key={item.pending.tempId} aria-busy="true" className="text-muted">
                    <ListRow
                      icon={categoryIcon(parentName.get(item.pending.category))}
                      title={item.pending.description}
                      meta="saving…"
                      right={
                        <span className="text-sm">
                          {item.pending.preview !== null
                            ? `≈ ${formatCents(item.pending.preview)} ${group.currency}`
                            : `${formatCents(item.pending.cents ?? 0)} ${item.pending.currency}`}
                        </span>
                      }
                    />
                  </li>
                ) : (
                  <li key={item.row.id} data-testid="expense-row" className="relative">
                    {item.row.recurring_rule != null && (
                      <Link
                        to={`/g/${group.id}/recurring#rule-${item.row.recurring_rule}`}
                        aria-label="Created by a recurring rule"
                        className="absolute bottom-1 left-1 z-10 flex size-11 items-end justify-start p-1 text-primary"
                      >
                        <Icon name="repeat" size={14} />
                      </Link>
                    )}
                    <button type="button" className="w-full text-left" onClick={() => open(item.row)}>
                      <ListRow
                        icon={categoryIcon(parentName.get(item.row.category))}
                        title={item.row.description}
                        meta={
                          <>
                            {categoryName.get(item.row.category) ?? ""} · {item.row.date} ·{" "}
                            {item.row.payers.length > 1 ? "multiple payers" : item.row.payers[0]?.member === group.my_member_id ? "you paid" : `${memberName(item.row.payers[0]?.member)} paid`}
                            {item.row.original_currency && item.row.original_currency !== group.currency && item.row.original_amount_cents != null && (
                              <>
                                {" · "}
                                {formatCents(item.row.original_amount_cents)} {item.row.original_currency}
                              </>
                            )}
                          </>
                        }
                        right={
                          <>
                            <span className="text-xs text-muted">{formatCents(item.row.amount_cents)}</span>{" "}
                            <ShareAmount row={item.row} me={group.my_member_id} />
                          </>
                        }
                      />
                    </button>
                  </li>
                ),
              )}
          </List>
        </div>
      ))}
      {list.hasNextPage && (
        <Button className="mt-4 w-full" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
          Load more
        </Button>
      )}
      <div className="pointer-events-none sticky bottom-24 flex justify-end pt-4">
        <Fab
          label="Add expense"
          disabled={!tree.data || !defaults.data}
          onClick={() => {
            setToast(null);
            setSheet({ kind: "add" });
          }}
        />
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
