import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, type JoinPreview, type JoinResult } from "../api";
import Logo from "../components/Logo";
import { INPUT } from "../components/ui";
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
  const entered = async (res: JoinResult) => {
    await Promise.all([qc.invalidateQueries({ queryKey: meKey }), qc.invalidateQueries({ queryKey: ["groups"] })]);
    navigate(`/g/${res.group_id}/expenses`);
  };
  const claim = useMutation({
    mutationFn: (memberId: number) =>
      api<JoinResult>("POST", `/join/${encodeURIComponent(token)}/claim`, { member_id: memberId }),
    onSuccess: entered,
    // Someone else may have taken the name meanwhile: show the server's reason and a fresh list.
    onError: () => qc.invalidateQueries({ queryKey: ["join", token] }),
  });
  const join = useMutation({
    mutationFn: () => api<JoinResult>("POST", `/join/${encodeURIComponent(token)}/`, {
        display_name: me?.authenticated ? (me.profile?.display_name ?? name) : name,
      }),
    onSuccess: entered,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    join.mutate();
  };
  if (preview.isPending) return <p className="p-5 text-muted">Loading…</p>;
  if (preview.isError) {
    return (
      <main className="space-y-3 px-5 py-5">
        <h1 className="font-heading text-xl font-semibold">Link not found</h1>
        <p>This invitation link is not valid.</p>
        <Link to="/groups" className="inline-flex min-h-11 items-center text-primary underline">
          Go to your groups
        </Link>
      </main>
    );
  }
  const signedIn = me?.authenticated ?? false;
  const error = join.error instanceof ApiError ? join.error.detail || join.error.code : null;
  const claimError = claim.error instanceof ApiError ? claim.error.detail || claim.error.code : null;
  const unclaimed = preview.data.unclaimed_members;
  return (
    <main className="space-y-4 px-5 pb-8 pt-5">
      <Logo size={32} wordmark />
      <h1 className="font-heading break-words text-xl font-semibold">Join {preview.data.group_name}</h1>
      <p className="text-sm text-muted">
        {preview.data.currency} · {preview.data.member_names.join(", ")}
      </p>
      {unclaimed.length > 0 && (
        <section className="space-y-2" aria-labelledby="claim-heading">
          <h2 id="claim-heading" className="font-heading text-lg font-semibold">
            Are you one of these?
          </h2>
          <ul className="overflow-hidden rounded-card border border-line bg-card [&>li+li]:border-t [&>li+li]:border-line-subtle">
            {unclaimed.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  className="min-h-14 w-full break-words px-4 text-left font-semibold"
                  disabled={claim.isPending}
                  onClick={() => claim.mutate(m.id)}
                >
                  {m.display_name}
                </button>
              </li>
            ))}
          </ul>
          {claimError && (
            <p role="alert" className="break-words text-sm text-danger">
              {claimError}
            </p>
          )}
          <h2 className="font-heading pt-2 text-lg font-semibold">I'm new</h2>
        </section>
      )}
      <form onSubmit={submit} className="space-y-3">
        {!signedIn && (
          <label className="block">
            <span className="text-sm text-muted">Your name</span>
            <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        {error && (
          <p role="alert" className="break-words text-sm text-danger">
            {error}
          </p>
        )}
        <button type="submit" className="min-h-14 w-full rounded-md bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50" disabled={join.isPending}>
          Join
        </button>
      </form>
    </main>
  );
}
