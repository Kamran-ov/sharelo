import { useEffect } from "react";

export const UNDO_MS = 5000;

export default function Toast({ message, onUndo, onDone }: { message: string; onUndo: () => void; onDone: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDone, UNDO_MS);
    return () => clearTimeout(timer);
  }, [onDone]);
  return (
    <div
      role="status"
      className="fixed bottom-20 left-1/2 z-30 flex w-[calc(100%-2rem)] max-w-[448px] -translate-x-1/2 items-center justify-between rounded-lg bg-slate-900 px-4 text-white"
    >
      <span>{message}</span>
      <button type="button" className="min-h-11 px-2 font-semibold text-emerald-300" onClick={onUndo}>
        Undo
      </button>
    </div>
  );
}
