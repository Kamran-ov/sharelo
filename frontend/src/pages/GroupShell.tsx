import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api, ApiError, type GroupDetail } from "../api";
import { useMe } from "../auth";
import AccountSheet from "./AccountSheet";
import GuestSignOutSheet from "./GuestSignOutSheet";

export const groupKey = (id: string | undefined) => ["group", id] as const;

export function useGroup(id: string | undefined) {
  return useQuery({
    queryKey: groupKey(id),
    queryFn: () => api<GroupDetail>("GET", `/groups/${id}/`),
    retry: false,
  });
}

const TABS = [
  ["expenses", "Expenses"],
  ["balances", "Balances"],
  ["recurring", "Recurring"],
  ["settings", "Settings"],
] as const;

function GuestBanner({ googleEnabled }: { googleEnabled: boolean }) {
  const [sheet, setSheet] = useState<"account" | "signout" | null>(null);
  return (
    <div className="space-y-2 border-b border-amber-200 bg-amber-50 p-4" role="region" aria-label="Guest">
      <p className="break-words text-sm">You're a guest. Create an account to keep access on any device.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="min-h-11 rounded-lg bg-emerald-600 px-4 font-medium text-white" onClick={() => setSheet("account")}>
          Create account
        </button>
        <button type="button" className="min-h-11 px-2 text-sm text-slate-600 underline" onClick={() => setSheet("signout")}>
          Sign out
        </button>
      </div>
      {sheet === "account" && <AccountSheet googleEnabled={googleEnabled} onClose={() => setSheet(null)} />}
      {sheet === "signout" && <GuestSignOutSheet onClose={() => setSheet(null)} />}
    </div>
  );
}

export default function GroupShell() {
  const { id } = useParams();
  const group = useGroup(id);
  const { data: me } = useMe();
  if (group.isPending) return <p className="p-4 text-slate-500">Loading…</p>;
  if (group.isError) {
    const missing = group.error instanceof ApiError && group.error.status === 404;
    return (
      <main className="space-y-3 p-4">
        <h1 className="text-2xl font-semibold">{missing ? "Group not found" : "Something went wrong"}</h1>
        <Link to="/groups" className="inline-flex min-h-11 items-center text-emerald-700 underline">
          Back to groups
        </Link>
      </main>
    );
  }
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-slate-200 p-4">
        <Link to="/groups" className="text-sm text-slate-600 underline">
          Groups
        </Link>
        <h1 className="break-words text-xl font-semibold">{group.data.name}</h1>
      </header>
      {me && !me.authenticated && <GuestBanner googleEnabled={me.google_enabled} />}
      <div className="flex-1">
        <Outlet context={group.data} />
      </div>
      <nav className="sticky bottom-0 grid grid-cols-4 border-t border-slate-200 bg-white" aria-label="Group">
        {TABS.map(([path, label]) => (
          <NavLink
            key={path}
            to={`/g/${id}/${path}`}
            className={({ isActive }) =>
              `flex min-h-14 items-center justify-center text-sm ${isActive ? "font-semibold text-emerald-700" : "text-slate-600"}`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
