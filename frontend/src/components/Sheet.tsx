import { useEffect, useRef, type ReactNode } from "react";

/** Full-height bottom sheet; the body scrolls inside it so nothing forces horizontal scroll. */
export default function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="flex h-dvh w-full max-w-[480px] flex-col bg-white outline-none"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" aria-label="Close" className="flex size-11 items-center justify-center text-xl" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}
