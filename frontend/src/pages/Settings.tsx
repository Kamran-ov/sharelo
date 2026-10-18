import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, ApiError, type GroupDetail, type RecurringStatus } from "../api";
import DefaultSplits from "./DefaultSplits";
import { groupKey } from "./GroupShell";

export default function Settings() {
  const group = useOutletContext<GroupDetail>();
  const qc = useQueryClient();
  const [copied, setCopied] = useState(false);
  const shareUrl = `${window.location.origin}/join/${group.share_token}`;
  const toggle = useMutation({
    mutationFn: (active: boolean) => api("POST", `/groups/${group.id}/link`, { active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: groupKey(String(group.id)) }),
  });
  const status = useQuery({
    queryKey: ["recurring-status", group.id],
    queryFn: () => api<RecurringStatus>("GET", `/groups/${group.id}/recurring/status/`),
  });
  const lastRun = status.data ? (status.data.last_run_at ? status.data.last_run_at.slice(0, 10) : "never") : "…";
  const copy = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
  };
  const toggleError = toggle.error instanceof ApiError ? toggle.error.detail || toggle.error.code : null;
  return (
    <section className="space-y-6 p-4">
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Share link</h2>
        <p className="break-all rounded-lg bg-slate-100 p-3 text-sm" data-testid="share-url">
          {shareUrl}
        </p>
        <button className="min-h-11 w-full rounded-lg border border-slate-300" onClick={copy}>
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Members</h2>
        <ul className="space-y-1">
          {group.members.map((m) => (
            <li key={m.id} className="break-words">
              {m.display_name}
              {m.id === group.my_member_id && <span className="text-slate-500"> (you)</span>}
              {m.is_guest && <span className="text-slate-500"> · guest</span>}
            </li>
          ))}
        </ul>
      </div>
      <DefaultSplits group={group} />
      <p className="text-sm text-slate-600" data-testid="recurring-status">
        Recurring expenses are created by the daily job; last run: {lastRun}
      </p>
      {group.link_active !== null && (
        <div className="space-y-2">
          <label className="flex min-h-11 items-center gap-3">
            <input
              type="checkbox"
              className="size-5"
              checked={group.link_active}
              disabled={toggle.isPending}
              onChange={(e) => toggle.mutate(e.target.checked)}
            />
            <span>Linked to Home</span>
          </label>
          {toggleError && (
            <p role="alert" className="text-sm text-red-700">
              {toggleError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
