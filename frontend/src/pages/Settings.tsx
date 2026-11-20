import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, ApiError, type GroupDetail, type RecurringStatus } from "../api";
import DefaultSplits from "./DefaultSplits";
import ShopRules from "./ShopRules";
import { groupKey } from "./GroupShell";

const STATUS_LABEL: Record<GroupDetail["members"][number]["status"], string> = {
  joined: "joined",
  guest: "guest",
  unclaimed: "not joined yet",
};

function AddPerson({ groupId }: { groupId: number }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: () => api("POST", `/groups/${groupId}/members/`, { display_name: name }),
    onSuccess: async () => {
      setName("");
      await qc.invalidateQueries({ queryKey: groupKey(String(groupId)) });
    },
  });
  const error = add.error instanceof ApiError ? add.error.detail || add.error.code : null;
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <label className="block">
        <span className="text-sm">Add person</span>
        <input className="min-h-11 w-full rounded-lg border border-slate-300 px-3" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      {error && (
        <p role="alert" className="break-words text-sm text-red-700">
          {error}
        </p>
      )}
      <button type="submit" className="min-h-11 w-full rounded-lg border border-slate-300" disabled={add.isPending}>
        Add
      </button>
    </form>
  );
}

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
            <li key={m.id} className="break-words" data-testid={`member-${m.id}`}>
              {m.display_name}
              {m.id === group.my_member_id && <span className="text-slate-500"> (you)</span>}
              <span className="text-slate-500"> · {STATUS_LABEL[m.status]}</span>
            </li>
          ))}
        </ul>
        <AddPerson groupId={group.id} />
      </div>
      <DefaultSplits group={group} />
      <ShopRules group={group} />
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
