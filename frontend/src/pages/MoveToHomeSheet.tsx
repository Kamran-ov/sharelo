import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError, type GroupDetail, type Transfer } from "../api";
import Sheet from "../components/Sheet";
import { localToday } from "../lib/dates";
import { moveToHomeLines } from "../lib/balances";
import { formatCents, parseAmount } from "../lib/money";

export default function MoveToHomeSheet({ group, transfer, onClose, onDone }: { group: GroupDetail; transfer: Transfer; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState(formatCents(transfer.amount_cents));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cents = parseAmount(amount);
  const name = (id: number) => group.members.find((m) => m.id === id)?.display_name ?? "?";
  const lines = moveToHomeLines(group.name, name(transfer.from_member), name(transfer.to_member), cents ?? transfer.amount_cents);

  const confirm = async () => {
    if (cents === null || transfer.to_profile === null) return;
    setBusy(true);
    setError(null);
    try {
      await api("POST", `/groups/${group.id}/move-to-home`, { to_profile: transfer.to_profile, amount_cents: cents, date: localToday() });
      // Home's balances live under another group id: drop every cached group's numbers.
      await Promise.all([qc.invalidateQueries({ queryKey: ["balances"] }), qc.invalidateQueries({ queryKey: ["settlements"] })]);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail || e.code : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title="Move to Home" onClose={onClose}>
      <div className="space-y-4">
        <label className="block">
          <span className="text-sm text-slate-600">Amount ({group.currency})</span>
          <input className="mt-1 block min-h-11 w-full rounded border border-slate-300 px-2" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <ul className="space-y-1 break-words">
          <li>{lines.trip}</li>
          <li>{lines.home}</li>
        </ul>
        {error && (
          <p role="alert" className="break-words text-red-700">
            {error}
          </p>
        )}
        <button type="button" disabled={cents === null || busy} onClick={confirm} className="min-h-12 w-full rounded bg-emerald-700 font-semibold text-white disabled:opacity-50">
          Move to Home
        </button>
      </div>
    </Sheet>
  );
}
