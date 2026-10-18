import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, type Balances as BalancesData, type GroupDetail, type SettlementRow, type Transfer } from "../api";
import Toast from "../components/Toast";
import { moveBadge, topCardText } from "../lib/balances";
import { formatCents } from "../lib/money";
import MoveToHomeSheet from "./MoveToHomeSheet";
import SettleSheet, { type SettleDefaults } from "./SettleSheet";

const TONE = { owed: "text-emerald-800", owe: "text-red-700", settled: "text-slate-700" } as const;

export default function Balances() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const base = `/groups/${group.id}`;
  const [settle, setSettle] = useState<SettleDefaults | null>(null);
  const [move, setMove] = useState<Transfer | null>(null);
  const [toast, setToast] = useState<{ id: number } | null>(null);

  const bal = useQuery({ queryKey: ["balances", group.id], queryFn: () => api<BalancesData>("GET", `${base}/balances/`) });
  const hist = useQuery({ queryKey: ["settlements", group.id], queryFn: () => api<SettlementRow[]>("GET", `${base}/settlements/`) });
  const name = (id: number) => group.members.find((m) => m.id === id)?.display_name ?? "?";

  const undo = async () => {
    if (!toast) return;
    const { id } = toast;
    setToast(null);
    await api("DELETE", `${base}/settlements/${id}/`);
    await Promise.all([qc.invalidateQueries({ queryKey: ["balances", group.id] }), qc.invalidateQueries({ queryKey: ["settlements", group.id] })]);
  };
  const closeToast = useCallback(() => setToast(null), []);

  if (bal.isPending) return <p className="p-4 text-slate-500">Loading…</p>;
  if (bal.isError) return <p role="alert" className="p-4">Could not load balances.</p>;
  const mine = bal.data.members.find((m) => m.member_id === group.my_member_id);
  const card = topCardText(mine?.net ?? 0);

  return (
    <section className="space-y-5 p-4">
      <div className="rounded-lg border border-slate-200 p-4" data-testid="top-card">
        <p className={`break-words text-xl font-semibold ${TONE[card.tone]}`}>{card.text}</p>
      </div>

      <div>
        <h2 className="mb-1 font-semibold">Members</h2>
        <ul>
          {bal.data.members.map((m) => (
            <li key={m.member_id} className="flex justify-between gap-2 border-b border-slate-100 py-2" data-testid="member-row">
              <span className="break-words">{name(m.member_id)}</span>
              <span className={`shrink-0 ${m.net > 0 ? TONE.owed : m.net < 0 ? TONE.owe : ""}`}>
                {m.net > 0 ? "is owed " : m.net < 0 ? "owes " : "settled "}
                {m.net !== 0 && formatCents(Math.abs(m.net))}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="mb-1 font-semibold">Suggested payments</h2>
        {bal.data.transfers.length === 0 && <p className="text-slate-600">Nothing to pay.</p>}
        <ul>
          {bal.data.transfers.map((t) => (
            <li key={`${t.from_member}-${t.to_member}`} className="border-b border-slate-100 py-2" data-testid="transfer">
              <p className="break-words">
                {name(t.from_member)} pays {name(t.to_member)} {formatCents(t.amount_cents)} {bal.data.currency}
              </p>
              <div className="mt-1 flex flex-wrap gap-2">
                <button type="button" className="min-h-11 rounded border border-emerald-700 px-3 text-emerald-800" onClick={() => setSettle({ from: t.from_member, to: t.to_member, cents: t.amount_cents })}>
                  Settle
                </button>
                {t.can_move_to_home && (
                  <button type="button" className="min-h-11 rounded border border-slate-400 px-3" onClick={() => setMove(t)}>
                    Move to Home
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>

      <details>
        <summary className="min-h-11 cursor-pointer font-semibold">History</summary>
        {hist.isSuccess && hist.data.length === 0 && <p className="text-slate-600">No settlements yet.</p>}
        <ul>
          {hist.data?.map((s) => {
            const badge = moveBadge(s, group.name);
            return (
              <li key={s.id} className="border-b border-slate-100 py-2" data-testid="history-row">
                <div className="flex justify-between gap-2">
                  <span className="break-words">
                    {s.date} · {name(s.from_member)} → {name(s.to_member)}
                  </span>
                  <span className="shrink-0">{formatCents(s.amount_cents)}</span>
                </div>
                {s.notes && !badge && <p className="break-words text-sm text-slate-600">{s.notes}</p>}
                {badge && (
                  <p className="text-sm text-slate-700" data-testid="move-badge">
                    {badge}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </details>

      {settle && (
        <SettleSheet
          group={group}
          defaults={settle}
          onClose={() => setSettle(null)}
          onSaved={(row) => {
            setSettle(null);
            setToast({ id: row.id });
          }}
        />
      )}
      {move && (
        <MoveToHomeSheet
          group={group}
          transfer={move}
          onClose={() => setMove(null)}
          onDone={() => setMove(null)}
        />
      )}
      {toast && <Toast message="Settled" onUndo={undo} onDone={closeToast} />}
    </section>
  );
}
