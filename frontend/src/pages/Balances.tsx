import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, type Balances as BalancesData, type GroupDetail, type SettlementRow, type Transfer } from "../api";
import Icon from "../components/Icon";
import Toast from "../components/Toast";
import { Amount, Button, List, SectionTitle, type Tone } from "../components/ui";
import { moveBadge, topCardText } from "../lib/balances";
import { formatCents } from "../lib/money";
import MoveToHomeSheet from "./MoveToHomeSheet";
import SettleSheet, { type SettleDefaults } from "./SettleSheet";
import ShareSheet from "./ShareSheet";

const TONE: Record<"owed" | "owe" | "settled", Tone> = { owed: "owed", owe: "owe", settled: "neutral" };

export default function Balances() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const base = `/groups/${group.id}`;
  const [settle, setSettle] = useState<SettleDefaults | null>(null);
  const [move, setMove] = useState<Transfer | null>(null);
  const [toast, setToast] = useState<{ id: number } | null>(null);
  const [sharing, setSharing] = useState(false);

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
  const closeShare = useCallback(() => setSharing(false), []);

  if (bal.isPending) return <p className="p-5 text-muted">Loading…</p>;
  if (bal.isError) return <p role="alert" className="p-5">Could not load balances.</p>;
  const mine = bal.data.members.find((m) => m.member_id === group.my_member_id);
  const card = topCardText(mine?.net ?? 0);

  return (
    <section className="space-y-1 px-5 pb-4">
      <List>
        <li className="flex items-start justify-between gap-2 px-4 py-4">
          <Amount tone={TONE[card.tone]} label={card.text} className="min-w-0 break-words font-heading text-xl" data-testid="top-card" />
          <Button className="shrink-0" onClick={() => setSharing(true)}>
            <Icon name="share" size={18} />
            Share
          </Button>
        </li>
        {bal.data.members.map((m) => (
          <li key={m.member_id} className="flex items-center gap-3 px-4 py-3" data-testid="member-row">
            <span
              aria-hidden="true"
              className={`flex size-9 shrink-0 items-center justify-center rounded-pill font-semibold text-ink ${m.net > 0 ? "bg-highlight-soft" : m.net < 0 ? "bg-owe-soft" : "bg-sunken"}`}
            >
              {name(m.member_id).slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1 break-words font-medium">{name(m.member_id)}</span>
            <Amount
              tone={m.net > 0 ? "owed" : m.net < 0 ? "owe" : "neutral"}
              label={m.net > 0 ? "is owed" : m.net < 0 ? "owes" : "settled"}
              figure={m.net !== 0 ? formatCents(Math.abs(m.net)) : undefined}
              className="shrink-0 text-sm"
            />
          </li>
        ))}
      </List>

      <SectionTitle>Suggested payments</SectionTitle>
      {bal.data.transfers.length === 0 && <p className="px-1 text-muted">Nothing to pay.</p>}
      {bal.data.transfers.length > 0 && (
        <List>
          {bal.data.transfers.map((t) => (
            <li key={`${t.from_member}-${t.to_member}`} className="space-y-2 px-4 py-3" data-testid="transfer">
              <p className="break-words">
                {name(t.from_member)} pays {name(t.to_member)} <span className="font-heading font-semibold">{formatCents(t.amount_cents)}</span> {bal.data.currency}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" className="min-h-11" onClick={() => setSettle({ from: t.from_member, to: t.to_member, cents: t.amount_cents })}>
                  Settle
                </Button>
                {t.can_move_to_home && (
                  <Button onClick={() => setMove(t)}>
                    <Icon name="home" size={18} />
                    Move to Home
                  </Button>
                )}
              </div>
            </li>
          ))}
        </List>
      )}

      <details className="pt-4">
        <summary className="min-h-11 cursor-pointer px-1 font-heading font-semibold leading-[2.75rem]">History</summary>
        {hist.isSuccess && hist.data.length === 0 && <p className="px-1 text-muted">No settlements yet.</p>}
        <ul className="overflow-hidden rounded-card border border-line bg-card empty:hidden [&>li+li]:border-t [&>li+li]:border-line-subtle">
          {hist.data?.map((s) => {
            const badge = moveBadge(s, group.name);
            return (
              <li key={s.id} className="px-4 py-3" data-testid="history-row">
                <div className="flex justify-between gap-2">
                  <span className="break-words">
                    {s.date} · {name(s.from_member)} → {name(s.to_member)}
                  </span>
                  <span className="shrink-0">{formatCents(s.amount_cents)}</span>
                </div>
                {s.notes && !badge && <p className="break-words text-sm text-muted">{s.notes}</p>}
                {badge && (
                  <p className="text-sm text-muted" data-testid="move-badge">
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
      {sharing && <ShareSheet group={group} onClose={closeShare} />}
      {toast && <Toast message="Settled" onUndo={undo} onDone={closeToast} />}
    </section>
  );
}
