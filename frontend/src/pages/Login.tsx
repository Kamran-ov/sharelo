import { useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";

import { hasAccess, meKey, useMe } from "../auth";
import AuthForm from "../components/AuthForm";

export default function Login() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  if (me && hasAccess(me)) return <Navigate to="/groups" replace />;
  return (
    <main className="p-4">
      <AuthForm
        googleEnabled={me?.google_enabled ?? false}
        onSignedIn={(next) => {
          qc.setQueryData(meKey, next);
          navigate("/groups", { replace: true });
        }}
      />
    </main>
  );
}
