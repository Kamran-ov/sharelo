import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { api, type Me } from "./api";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: () => api<Me>("GET", "/me") });
}

export function hasAccess(me: Me): boolean {
  return me.authenticated || me.guest_memberships.length > 0;
}

export function RequireAccess() {
  const { data: me, isPending, isError } = useMe();
  const location = useLocation();
  if (isPending) return <p className="p-4 text-slate-500">Loading…</p>;
  if (isError || !hasAccess(me)) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
