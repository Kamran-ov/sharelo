import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api, ApiError, type BankUploadResult, type CategoryNode, type GroupDetail, type ReviewList, type ReviewRow } from "../api";
import { formatCents } from "../lib/money";
import { resolveBody, resultLine, rowChoice, splitLabel, type Decision, type Params } from "../lib/bankImport";

interface Done {
  row: ReviewRow;
  line: string;
}

const errorText = (e: unknown) => (e instanceof ApiError ? e.detail || e.code : "Something went wrong");

export const bankRowsKey = (groupId: number) => ["bank-rows", groupId];

export default function BankImport() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const me = group.my_member_id ?? 0;
  const memberIds = group.members.map((m) => m.id);
  const tree = useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryNode[]>("GET", "/categories/") });
  const list = useQuery({ queryKey: bankRowsKey(group.id), queryFn: () => api<ReviewList>("GET", `/groups/${group.id}/bank-rows/`) });
  const [upload, setUpload] = useState<{ busy: boolean; line?: string; error?: string }>({ busy: false });
  const [chosen, setChosen] = useState<Record<number, number>>({});
  const [remember, setRemember] = useState<Record<number, boolean>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [done, setDone] = useState<Record<number, Done>>({});
  const [busy, setBusy] = useState<number | null>(null);

  const names = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of tree.data ?? []) for (const k of p.children) m.set(k.id, k.name);
    return m;
  }, [tree.data]);

  const rows = useMemo(() => {
    const byId = new Map<number, ReviewRow>();
    for (const r of list.data?.rows ?? []) byId.set(r.id, r);
    for (const d of Object.values(done)) byId.set(d.row.id, d.row);
    return [...byId.values()].sort((a, b) => (a.date === b.date ? a.id - b.id : a.date < b.date ? -1 : 1));
  }, [list.data, done]);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setUpload({ busy: true });
    try {
      const res = await api<BankUploadResult>("POST", `/groups/${group.id}/bank-imports/`, form);
      const b = res.batch;
      setUpload({ busy: false, line: `${b.rows_created} new, ${b.rows_skipped} already imported, ${res.ignored} not money out` });
      await qc.invalidateQueries({ queryKey: bankRowsKey(group.id) });
    } catch (e) {
      setUpload({ busy: false, error: errorText(e) });
    }
  };

  const decide = async (row: ReviewRow, decision: Decision) => {
    const triple = rowChoice(row.suggestion, list.data?.category_splits ?? {}, chosen[row.id]);
    if (!triple) return;
    const label = splitLabel(triple.preset, triple.params, me, memberIds);
    setBusy(row.id);
    setErrors((e) => ({ ...e, [row.id]: "" }));
    try {
      await api("POST", `/groups/${group.id}/bank-rows/${row.id}/resolve`, resolveBody(decision, triple, decision !== "skip" && !!remember[row.id]));
      setDone((d) => ({ ...d, [row.id]: { row, line: resultLine(decision, names.get(triple.category) ?? "", label) } }));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["expenses", group.id] }),
        qc.invalidateQueries({ queryKey: ["balances", group.id] }),
        qc.invalidateQueries({ queryKey: ["shop-rules", group.id] }),
      ]);
    } catch (e) {
      setErrors((x) => ({ ...x, [row.id]: errorText(e) }));
    } finally {
      setBusy(null);
    }
  };

  const undo = async (row: ReviewRow) => {
    setBusy(row.id);
    try {
      await api("POST", `/groups/${group.id}/bank-rows/${row.id}/undo`);
      await Promise.all([
        qc.invalidateQueries({ queryKey: bankRowsKey(group.id) }),
        qc.invalidateQueries({ queryKey: ["expenses", group.id] }),
        qc.invalidateQueries({ queryKey: ["balances", group.id] }),
      ]);
      setDone((d) => {
        const next = { ...d };
        delete next[row.id];
        return next;
      });
    } catch (e) {
      setErrors((x) => ({ ...x, [row.id]: errorText(e) }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="space-y-4 px-5 pb-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-semibold">Import bank file</h2>
        <Link to={`/g/${group.id}/expenses`} className="min-h-11 content-center text-sm text-primary">
          Back to expenses
        </Link>
      </div>
      <label className="block space-y-1">
        <span className="text-sm text-muted">Revolut or Wise statement (CSV)</span>
        <input type="file" accept=".csv,text/csv" disabled={upload.busy} className="block w-full text-sm" onChange={(e) => onFile(e.target.files?.[0])} />
      </label>
      {upload.line && <p data-testid="upload-result" className="text-sm text-muted">{upload.line}</p>}
      {upload.error && (
        <p role="alert" className="break-words text-sm text-danger">
          {upload.error}
        </p>
      )}
      {list.isSuccess && rows.length === 0 && <p className="text-muted">Nothing to review.</p>}
      <ul className="space-y-3">
        {rows.map((row) => {
          const finished = done[row.id];
          const s = row.suggestion;
          const triple = rowChoice(s, list.data?.category_splits ?? {}, chosen[row.id]);
          const label = triple ? splitLabel(triple.preset, triple.params as Params, me, memberIds) : "";
          const shop = row.merchant || row.description;
          return (
            <li key={row.id} data-testid="bank-row" className="rounded-card border border-line bg-card p-3">
              <div className="flex justify-between gap-2">
                <span className="break-words font-medium">{shop}</span>
                <span className="shrink-0">
                  {formatCents(row.amount_cents)} {row.currency}
                </span>
              </div>
              <div className="text-sm text-muted">{row.date}</div>
              {finished ? (
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span data-testid="result-line" className="text-sm">
                    {finished.line}
                  </span>
                  <button type="button" className="min-h-11 px-3 text-primary" disabled={busy === row.id} onClick={() => undo(row)}>
                    Undo
                  </button>
                </div>
              ) : (
                <div className="mt-2 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      aria-label={`Category for ${shop}`}
                      className="min-h-11 max-w-full rounded-pill border border-line px-3 text-sm"
                      value={triple?.category ?? s.category}
                      onChange={(e) => setChosen((c) => ({ ...c, [row.id]: Number(e.target.value) }))}
                    >
                      {(tree.data ?? []).map((p) => (
                        <optgroup key={p.id} label={p.name}>
                          {p.children.map((k) => (
                            <option key={k.id} value={k.id}>
                              {k.name}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <span data-testid="split-label" className="text-sm text-muted">
                      {label}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {(["shared", "personal", "skip"] as const).map((d) => (
                      <button
                        key={d}
                        type="button"
                        disabled={busy !== null || !triple}
                        className={`min-h-12 rounded-md border text-md capitalize ${d === s.decision ? "border-highlight bg-highlight-soft font-semibold" : "border-line bg-card"}`}
                        onClick={() => decide(row, d)}
                      >
                        {d === "skip" ? "Skip" : d === "shared" ? "Shared" : "Personal"}
                      </button>
                    ))}
                  </div>
                  <label className="flex min-h-11 items-center gap-3 text-sm">
                    <input
                      type="checkbox"
                      className="size-5"
                      checked={!!remember[row.id]}
                      onChange={(e) => setRemember((r) => ({ ...r, [row.id]: e.target.checked }))}
                    />
                    <span>Remember for this shop</span>
                  </label>
                  {errors[row.id] && (
                    <p role="alert" className="break-words text-sm text-danger">
                      {errors[row.id]}
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
