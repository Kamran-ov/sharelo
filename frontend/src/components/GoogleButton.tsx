import { useEffect, useRef } from "react";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; callback: (r: { credential: string }) => void }) => void;
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
        };
      };
    };
  }
}

const GIS_SRC = "https://accounts.google.com/gsi/client";

/**
 * Rendered only when /api/me says Google is enabled. /api/me carries no client id, so the id
 * comes from the build (VITE_GOOGLE_CLIENT_ID); wiring real credentials is release-step work.
 */
export default function GoogleButton({
  enabled,
  onCredential,
}: {
  enabled: boolean;
  onCredential: (idToken: string) => void;
}) {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  const slot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!enabled || !clientId) return;
    const render = () => {
      if (!slot.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (r) => onCredential(r.credential),
      });
      window.google.accounts.id.renderButton(slot.current, { theme: "outline", size: "large" });
    };
    if (window.google) return render();
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.onload = render;
    document.head.appendChild(script);
  }, [enabled, clientId, onCredential]);
  if (!enabled) return null;
  return (
    <div data-testid="google-button" className="flex min-h-11 flex-col items-center">
      <span className="sr-only">Sign in with Google</span>
      <div ref={slot} />
      {!clientId && <p className="text-sm text-slate-500">Google sign-in is not set up in this build.</p>}
    </div>
  );
}
