import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api, ApiError, type GroupDetail } from "../api";

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

export default function GroupShell() {
  const { id } = useParams();
  const group = useGroup(id);
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
