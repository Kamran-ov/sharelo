import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError, type GroupSummary } from "../api";
import { meKey, useMe } from "../auth";

// EUR first (the default for this household), then common ECB-published currencies.
export const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "TRY", "JPY", "CAD", "AUD"];

const badge = "rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700";

export function NewGroupSheet({ hasMainGroup, onClose }: { hasMainGroup: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [asMain, setAsMain] = useState(!hasMainGroup);
  const create = useMutation({
    mutationFn: () =>
      api("POST", "/groups/", hasMainGroup ? { name, currency } : { name, currency, as_main: asMain }),
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ["groups"] }), qc.invalidateQueries({ queryKey: meKey })]);
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  const error = create.error instanceof ApiError ? create.error.detail || create.error.code : null;
  return (
    <div className="fixed inset-0 z-10 flex items-end justify-center bg-black/40">
      <form
        role="dialog"
        aria-label="New group"
        onSubmit={submit}
        className="w-full max-w-[480px] space-y-3 rounded-t-2xl bg-white p-4"
      >
        <h2 className="text-lg font-semibold">New group</h2>
        <label className="block">
          <span className="text-sm">Name</span>
          <input className="min-h-11 w-full rounded-lg border border-slate-300 px-3" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-sm">Currency</span>
          <select className="min-h-11 w-full rounded-lg border border-slate-300 px-3" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-3">
          <input type="checkbox" className="size-5" checked={asMain} disabled={hasMainGroup} onChange={(e) => setAsMain(e.target.checked)} />
          <span>Make this my main group</span>
        </label>
        {error && (
          <p role="alert" className="break-words text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex gap-3">
          <button type="button" className="min-h-11 flex-1 rounded-lg border border-slate-300" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="min-h-11 flex-1 rounded-lg bg-emerald-600 font-medium text-white" disabled={create.isPending}>
            Create group
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Groups() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [sheet, setSheet] = useState(false);
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api<GroupSummary[]>("GET", "/groups/") });
  const logout = useMutation({
    mutationFn: () => api("POST", "/auth/logout"),
    onSuccess: () => {
      qc.clear();
      navigate("/login", { replace: true });
    },
  });
  const signedIn = me?.authenticated ?? false;
  return (
    <main className="space-y-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Groups</h1>
        <button className="min-h-11 px-2 text-sm text-slate-600 underline" onClick={() => logout.mutate()}>
          Sign out
        </button>
      </header>
      {groups.isPending && <p className="text-slate-500">Loading…</p>}
      <ul className="space-y-2">
        {groups.data?.map((g) => (
          <li key={g.id}>
            <Link to={`/g/${g.id}/expenses`} className="flex min-h-11 items-center justify-between gap-2 rounded-lg border border-slate-200 p-3">
              <span className="min-w-0 break-words font-medium">{g.name}</span>
              <span className="flex shrink-0 flex-wrap items-center justify-end gap-1">
                <span className={badge}>{g.currency}</span>
                {g.is_main && <span className={badge}>main</span>}
                {g.link_active === true && <span className={badge}>linked to Home</span>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {signedIn && (
        <button className="min-h-11 w-full rounded-lg bg-emerald-600 font-medium text-white" onClick={() => setSheet(true)}>
          New group
        </button>
      )}
      {sheet && <NewGroupSheet hasMainGroup={me?.profile?.main_group_id != null} onClose={() => setSheet(false)} />}
    </main>
  );
}
