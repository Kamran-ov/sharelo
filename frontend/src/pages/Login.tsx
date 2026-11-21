import { useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";

import { hasAccess, meKey, useMe } from "../auth";
import AuthForm from "../components/AuthForm";
import Logo from "../components/Logo";
import { Card } from "../components/ui";

export default function Login() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  if (me && hasAccess(me)) return <Navigate to="/groups" replace />;
  return (
    <main className="space-y-8 px-5 pb-8 pt-10">
      <div className="flex justify-center">
        <Logo size={48} wordmark />
      </div>
      <Card className="p-5">
        <AuthForm
          googleEnabled={me?.google_enabled ?? false}
          onSignedIn={(next) => {
            qc.setQueryData(meKey, next);
            navigate("/groups", { replace: true });
          }}
        />
      </Card>
    </main>
  );
}
