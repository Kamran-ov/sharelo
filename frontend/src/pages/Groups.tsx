import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError, type GroupSummary } from "../api";
import { meKey, useMe } from "../auth";
import Logo from "../components/Logo";
import { Button, ErrorText, INPUT } from "../components/ui";
import GuestSignOutSheet from "./GuestSignOutSheet";

// EUR first (the default for this household), then common ECB-published currencies.
export const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "TRY", "JPY", "CAD", "AUD"];

const badge = "rounded-pill bg-sunken px-2 py-0.5 text-xs text-muted";

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
    <div className="fixed inset-0 z-10 flex items-end justify-center bg-overlay/60">
      <form
        role="dialog"
        aria-label="New group"
        onSubmit={submit}
        className="w-full max-w-[480px] space-y-4 rounded-t-sheet bg-ground px-5 pb-7 pt-5 text-ink"
      >
        <h2 className="font-heading text-lg font-semibold">New group</h2>
        <label className="block">
          <span className="text-sm text-muted">Name</span>
          <input className={`${INPUT} mt-1.5`} value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-sm text-muted">Currency</span>
          <select className={`${INPUT} mt-1.5`} value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-3">
          <input type="checkbox" className="size-5" checked={asMain} disabled={hasMainGroup} onChange={(e) => setAsMain(e.target.checked)} />
          <span>Make this my main group</span>
        </label>
        {error && <ErrorText>{error}</ErrorText>}
        <div className="flex gap-3">
          <Button className="min-h-14 flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" className="flex-1" disabled={create.isPending}>
            Create group
          </Button>
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
  const [guestSignOut, setGuestSignOut] = useState(false);
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
    <main className="space-y-4 px-5 pb-8 pt-5">
      <header className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2.5">
          <Logo size={32} />
          <h1 className="font-heading text-xl font-semibold">Groups</h1>
        </span>
        <button className="min-h-11 shrink-0 px-2 text-sm text-muted underline" onClick={() => (me && !me.authenticated ? setGuestSignOut(true) : logout.mutate())}>
          Sign out
        </button>
      </header>
      {groups.isPending && <p className="text-muted">Loading…</p>}
      <ul className="overflow-hidden rounded-card border border-line bg-card empty:hidden [&>li+li]:border-t [&>li+li]:border-line-subtle">
        {groups.data?.map((g) => (
          <li key={g.id}>
            <Link to={`/g/${g.id}/expenses`} className="flex min-h-14 items-center justify-between gap-2 px-4 py-3">
              <span className="min-w-0 break-words font-semibold">{g.name}</span>
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
        <Button variant="primary" className="w-full" onClick={() => setSheet(true)}>
          New group
        </Button>
      )}
      {guestSignOut && <GuestSignOutSheet onClose={() => setGuestSignOut(false)} />}
      {sheet && <NewGroupSheet hasMainGroup={me?.profile?.main_group_id != null} onClose={() => setSheet(false)} />}
    </main>
  );
}
