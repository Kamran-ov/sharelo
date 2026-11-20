import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type GroupDetail, type GroupSummary } from "../api";
import Sheet from "../components/Sheet";

/** A guest's session is their only key; say so before throwing it away. */
export default function GuestSignOutSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [copied, setCopied] = useState<number | null>(null);
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api<GroupSummary[]>("GET", "/groups/") });
  const details = useQueries({
    queries: (groups.data ?? []).map((g) => ({
      queryKey: ["group", String(g.id)],
      queryFn: () => api<GroupDetail>("GET", `/groups/${g.id}/`),
    })),
  });
  const logout = useMutation({
    mutationFn: () => api("POST", "/auth/logout"),
    onSuccess: () => {
      qc.clear();
      navigate("/login", { replace: true });
    },
  });
  const copy = async (g: GroupDetail) => {
    await navigator.clipboard.writeText(`${window.location.origin}/join/${g.share_token}`);
    setCopied(g.id);
  };
  return (
    <Sheet title="Sign out" onClose={onClose}>
      <div className="space-y-4">
        <p className="break-words font-medium">
          You will lose access on this device. Save the group link or create an account first.
        </p>
        <ul className="space-y-2">
          {details.map((d) =>
            d.data ? (
              <li key={d.data.id} className="flex items-center justify-between gap-2">
                <span className="min-w-0 break-words">{d.data.name}</span>
                <button type="button" className="min-h-11 shrink-0 rounded-lg border border-slate-300 px-3" onClick={() => copy(d.data)}>
                  {copied === d.data.id ? "Copied" : "Copy link"}
                </button>
              </li>
            ) : null,
          )}
        </ul>
        <button type="button" className="min-h-11 w-full rounded-lg bg-red-700 font-medium text-white" onClick={() => logout.mutate()} disabled={logout.isPending}>
          Sign out anyway
        </button>
        <button type="button" className="min-h-11 w-full rounded-lg border border-slate-300" onClick={onClose}>
          Cancel
        </button>
      </div>
    </Sheet>
  );
}
