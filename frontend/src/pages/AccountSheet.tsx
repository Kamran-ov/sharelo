import { useQueries, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type GroupDetail, type Me } from "../api";
import { meKey } from "../auth";
import AuthForm from "../components/AuthForm";
import Sheet from "../components/Sheet";

/** Guest → account without leaving the group; the server attaches the claimed member. */
export default function AccountSheet({ googleEnabled, onClose }: { googleEnabled: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [refused, setRefused] = useState<Me["guest_refused"]>([]);
  const signedIn = async (me: Me) => {
    qc.setQueryData(meKey, me);
    await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
    if (me.guest_refused.length > 0) setRefused(me.guest_refused);
    else onClose();
  };
  return (
    <Sheet title="Create account" onClose={onClose}>
      {refused.length > 0 ? (
        <div className="space-y-3" role="status">
          <RefusedNotice refused={refused} />
          <button type="button" className="min-h-11 w-full rounded-md border border-line bg-card font-medium" onClick={onClose}>
            OK
          </button>
        </div>
      ) : (
        <AuthForm googleEnabled={googleEnabled} startCreating onSignedIn={signedIn} />
      )}
    </Sheet>
  );
}

function RefusedNotice({ refused }: { refused: Me["guest_refused"] }) {
  const groups = useQueries({
    queries: refused.map((r) => ({
      queryKey: ["group", String(r.group_id)],
      queryFn: () => api<GroupDetail>("GET", `/groups/${r.group_id}/`),
    })),
  });
  return (
    <>
      {refused.map((r, i) => (
        <p key={r.member_id} className="break-words">
          You already belong to {groups[i]?.data?.name ?? "this group"} with this account; the guest name stays on this device only.
        </p>
      ))}
    </>
  );
}
