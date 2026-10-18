import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, type JoinPreview, type JoinResult } from "../api";
import { meKey, useMe } from "../auth";

export default function Join() {
  const { token = "" } = useParams();
  const { data: me } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const preview = useQuery({
    queryKey: ["join", token],
    queryFn: () => api<JoinPreview>("GET", `/join/${encodeURIComponent(token)}/`),
    retry: false,
  });
  const join = useMutation({
    mutationFn: () => api<JoinResult>("POST", `/join/${encodeURIComponent(token)}/`, {
        display_name: me?.authenticated ? (me.profile?.display_name ?? name) : name,
      }),
    onSuccess: async (res) => {
      await Promise.all([qc.invalidateQueries({ queryKey: meKey }), qc.invalidateQueries({ queryKey: ["groups"] })]);
      navigate(`/g/${res.group_id}/expenses`);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    join.mutate();
  };
  if (preview.isPending) return <p className="p-4 text-slate-500">Loading…</p>;
  if (preview.isError) {
    return (
      <main className="space-y-3 p-4">
        <h1 className="text-2xl font-semibold">Link not found</h1>
        <p>This invitation link is not valid.</p>
        <Link to="/groups" className="inline-flex min-h-11 items-center text-emerald-700 underline">
          Go to your groups
        </Link>
      </main>
    );
  }
  const signedIn = me?.authenticated ?? false;
  const error = join.error instanceof ApiError ? join.error.detail || join.error.code : null;
  return (
    <main className="space-y-4 p-4">
      <h1 className="break-words text-2xl font-semibold">Join {preview.data.group_name}</h1>
      <p className="text-sm text-slate-600">
        {preview.data.currency} · {preview.data.member_names.join(", ")}
      </p>
      <form onSubmit={submit} className="space-y-3">
        {!signedIn && (
          <label className="block">
            <span className="text-sm">Your name</span>
            <input className="min-h-11 w-full rounded-lg border border-slate-300 px-3" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        {error && (
          <p role="alert" className="break-words text-sm text-red-700">
            {error}
          </p>
        )}
        <button type="submit" className="min-h-11 w-full rounded-lg bg-emerald-600 font-medium text-white" disabled={join.isPending}>
          Join
        </button>
      </form>
    </main>
  );
}
