import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError, type Me } from "../api";
import GoogleButton from "./GoogleButton";

const input = "min-h-11 w-full rounded-lg border border-slate-300 px-3 text-base";
const primary = "min-h-11 w-full rounded-lg bg-emerald-600 px-4 font-medium text-white";

/** Sign-in / create-account form shared by the login page and the guest account sheet. */
export default function AuthForm({
  googleEnabled,
  startCreating = false,
  onSignedIn,
}: {
  googleEnabled: boolean;
  startCreating?: boolean;
  onSignedIn: (me: Me) => void;
}) {
  const [creating, setCreating] = useState(startCreating);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  const signIn = useMutation({
    mutationFn: (req: { path: string; body: unknown }) => api<Me>("POST", req.path, req.body),
    onSuccess: onSignedIn,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    signIn.mutate(
      creating
        ? { path: "/auth/register", body: { email, password, display_name: displayName } }
        : { path: "/auth/login", body: { email, password } },
    );
  };
  const error = signIn.error instanceof ApiError ? signIn.error.detail || signIn.error.code : null;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{creating ? "Create account" : "Sign in"}</h1>
      <form onSubmit={submit} className="space-y-3">
        {creating && (
          <label className="block">
            <span className="text-sm">Your name</span>
            <input className={input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
        )}
        <label className="block">
          <span className="text-sm">Email</span>
          <input className={input} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-sm">Password</span>
          <input
            className={input}
            type="password"
            autoComplete={creating ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="break-words text-sm text-red-700">
            {error}
          </p>
        )}
        <button type="submit" className={primary} disabled={signIn.isPending}>
          {creating ? "Create account" : "Sign in"}
        </button>
      </form>
      <GoogleButton enabled={googleEnabled} onCredential={(id_token) => signIn.mutate({ path: "/auth/google", body: { id_token } })} />
      <button
        type="button"
        className="min-h-11 w-full text-emerald-700 underline"
        onClick={() => {
          setCreating(!creating);
          signIn.reset();
        }}
      >
        {creating ? "I already have an account" : "Create account"}
      </button>
    </div>
  );
}
