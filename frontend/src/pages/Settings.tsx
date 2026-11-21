import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, ApiError, type GroupDetail, type RecurringStatus } from "../api";
import { INPUT } from "../components/ui";
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
        <span className="text-sm text-muted">Add person</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      {error && (
        <p role="alert" className="break-words text-sm text-danger">
          {error}
        </p>
      )}
      <button type="submit" className="min-h-11 w-full rounded-md border border-line bg-card font-medium" disabled={add.isPending}>
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
    <section className="space-y-4 px-5 pb-6">
      <div className="space-y-2 rounded-card border border-line bg-card p-4">
        <h2 className="font-heading text-lg font-semibold">Share link</h2>
        <p className="break-all rounded-md bg-sunken p-3 text-sm" data-testid="share-url">
          {shareUrl}
        </p>
        <button className="min-h-11 w-full rounded-md border border-line bg-card font-medium" onClick={copy}>
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      <div className="space-y-2 rounded-card border border-line bg-card p-4">
        <h2 className="font-heading text-lg font-semibold">Members</h2>
        <ul className="space-y-1">
          {group.members.map((m) => (
            <li key={m.id} className="break-words" data-testid={`member-${m.id}`}>
              {m.display_name}
              {m.id === group.my_member_id && <span className="text-muted"> (you)</span>}
              <span className="text-muted"> · {STATUS_LABEL[m.status]}</span>
            </li>
          ))}
        </ul>
        <AddPerson groupId={group.id} />
      </div>
      <DefaultSplits group={group} />
      <ShopRules group={group} />
      <p className="px-1 text-sm text-muted" data-testid="recurring-status">
        Recurring expenses are created by the daily job; last run: {lastRun}
      </p>
      {group.link_active !== null && (
        <div className="space-y-2 rounded-card border border-line bg-card p-4">
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
            <p role="alert" className="break-words text-sm text-danger">
              {toggleError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
