import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api, ApiError, type GroupDetail } from "../api";
import { useMe } from "../auth";
import Icon from "../components/Icon";
import Logo from "../components/Logo";
import { Button, Card } from "../components/ui";
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
  ["expenses", "Expenses", "list"],
  ["balances", "Balances", "scale"],
  ["recurring", "Recurring", "repeat"],
  ["settings", "Settings", "settings"],
] as const;

function BottomNav({ id }: { id: string | undefined }) {
  return (
    <nav className="sticky bottom-0 z-10 grid grid-cols-4 border-t border-line bg-card pb-[env(safe-area-inset-bottom)]" aria-label="Group">
      {TABS.map(([path, label, icon]) => (
        <NavLink
          key={path}
          to={`/g/${id}/${path}`}
          className={({ isActive }) => `flex min-h-16 flex-col items-center justify-center gap-1 text-xs ${isActive ? "font-semibold text-primary" : "text-muted"}`}
        >
          <Icon name={icon} size={22} />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function GuestBanner({ googleEnabled }: { googleEnabled: boolean }) {
  const [sheet, setSheet] = useState<"account" | "signout" | null>(null);
  return (
    <Card variant="soft" className="mx-5 mb-3 space-y-2" role="region" aria-label="Guest">
      <p className="break-words text-sm">You're a guest. Create an account to keep access on any device.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" className="min-h-11" onClick={() => setSheet("account")}>
          Create account
        </Button>
        <Button variant="ghost" className="text-sm" onClick={() => setSheet("signout")}>
          Sign out
        </Button>
      </div>
      {sheet === "account" && <AccountSheet googleEnabled={googleEnabled} onClose={() => setSheet(null)} />}
      {sheet === "signout" && <GuestSignOutSheet onClose={() => setSheet(null)} />}
    </Card>
  );
}

export default function GroupShell() {
  const { id } = useParams();
  const group = useGroup(id);
  const { data: me } = useMe();
  if (group.isPending) return <p className="p-5 text-muted">Loading…</p>;
  if (group.isError) {
    const missing = group.error instanceof ApiError && group.error.status === 404;
    return (
      <main className="space-y-3 p-5">
        <h1 className="font-heading text-xl font-semibold">{missing ? "Group not found" : "Something went wrong"}</h1>
        <Link to="/groups" className="inline-flex min-h-11 items-center font-medium text-primary underline">
          Back to groups
        </Link>
      </main>
    );
  }
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between gap-3 px-5 pb-3 pt-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <Logo size={32} />
          <h1 className="min-w-0 break-words font-heading text-xl font-semibold leading-tight">{group.data.name}</h1>
        </div>
        <Link to="/groups" className="flex min-h-11 shrink-0 items-center gap-1 rounded-md border border-line bg-card px-3 text-sm font-medium text-ink">
          Groups
          <Icon name="chevronDown" size={18} />
        </Link>
      </header>
      {me && !me.authenticated && <GuestBanner googleEnabled={me.google_enabled} />}
      <div className="flex-1">
        <Outlet context={group.data} />
      </div>
      <BottomNav id={id} />
    </div>
  );
}
