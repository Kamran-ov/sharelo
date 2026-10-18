import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError, type GroupDetail, type SettlementRow } from "../api";
import Sheet from "../components/Sheet";
import { localToday } from "../lib/dates";
import { formatCents, parseAmountForSubmit } from "../lib/money";

export interface SettleDefaults {
  from: number;
  to: number;
  cents: number;
}

export default function SettleSheet({
  group,
  defaults,
  onClose,
  onSaved,
}: {
  group: GroupDetail;
  defaults: SettleDefaults;
  onClose: () => void;
  onSaved: (row: SettlementRow) => void;
}) {
  const qc = useQueryClient();
  const [from, setFrom] = useState(defaults.from);
  const [to, setTo] = useState(defaults.to);
  const [amount, setAmount] = useState(formatCents(defaults.cents));
  const [date, setDate] = useState(localToday());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cents = parseAmountForSubmit(amount);

  const save = async () => {
    if (cents === null) return;
    setBusy(true);
    setError(null);
    try {
      const row = await api<SettlementRow>("POST", `/groups/${group.id}/settlements/`, { from_member: from, to_member: to, amount_cents: cents, date, notes });
      await Promise.all([qc.invalidateQueries({ queryKey: ["balances", group.id] }), qc.invalidateQueries({ queryKey: ["settlements", group.id] })]);
      onSaved(row);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail || e.code : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const members = (
    <>
      {group.members.map((m) => (
        <option key={m.id} value={m.id}>
          {m.display_name}
        </option>
      ))}
    </>
  );
  return (
    <Sheet title="Settle up" onClose={onClose}>
      <div className="space-y-4">
        <label className="block">
          <span className="text-sm text-slate-600">From</span>
          <select className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" value={from} onChange={(e) => setFrom(Number(e.target.value))}>
            {members}
          </select>
        </label>
        <label className="block">
          <span className="text-sm text-slate-600">To</span>
          <select className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" value={to} onChange={(e) => setTo(Number(e.target.value))}>
            {members}
          </select>
        </label>
        <label className="block">
          <span className="text-sm text-slate-600">Amount ({group.currency})</span>
          <input className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm text-slate-600">Date</span>
          <input type="date" className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm text-slate-600">Note</span>
          <input className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        {error && (
          <p role="alert" className="break-words text-red-700">
            {error}
          </p>
        )}
        <button type="button" disabled={cents === null || busy} onClick={save} className="min-h-12 w-full rounded bg-emerald-700 font-semibold text-white disabled:opacity-50">
          Settle
        </button>
      </div>
    </Sheet>
  );
}
