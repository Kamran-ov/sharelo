import { useEffect, useState } from "react";

const DISMISSED_KEY = "sharelo.installHint.dismissed";

type InstallPrompt = Event & { prompt: () => Promise<unknown> };

export function isIosSafari(userAgent: string): boolean {
  return /iphone|ipad|ipod/i.test(userAgent) && !/crios|fxios|edgios/i.test(userAgent);
}

function isStandalone(): boolean {
  const iosFlag = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return iosFlag || (window.matchMedia?.("(display-mode: standalone)").matches ?? false);
}

function wasDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

/** Shown until dismissed once, and never inside the installed app. Both inputs are injectable for tests. */
export default function InstallHint({
  userAgent = navigator.userAgent,
  standalone = isStandalone(),
}: {
  userAgent?: string;
  standalone?: boolean;
}) {
  const [dismissed, setDismissed] = useState(wasDismissed);
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  const ios = isIosSafari(userAgent);
  if (dismissed || standalone || (!ios && !prompt)) return null;

  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      /* blocked storage: the banner simply returns next visit */
    }
  };

  return (
    <div role="region" aria-label="Install Sharelo" className="flex items-center justify-between gap-2 bg-emerald-50 px-4 py-2 text-sm text-emerald-900">
      {prompt ? (
        <button
          type="button"
          className="min-h-11 font-semibold underline"
          onClick={() => {
            void prompt.prompt();
            dismiss();
          }}
        >
          Install Sharelo
        </button>
      ) : (
        <span>Install Sharelo: tap Share, then Add to Home Screen.</span>
      )}
      <button type="button" className="min-h-11 px-2 font-semibold" onClick={dismiss}>
        Dismiss
      </button>
    </div>
  );
}
