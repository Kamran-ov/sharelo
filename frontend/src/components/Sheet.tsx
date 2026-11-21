import { useEffect, useRef, type ReactNode } from "react";

import Icon from "./Icon";

/** Bottom sheet over the overlay scrim; the body scrolls inside it so nothing forces horizontal scroll. */
export default function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-overlay/60" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="flex h-[calc(100dvh-24px)] w-full max-w-[480px] flex-col rounded-t-sheet bg-ground text-ink outline-none"
      >
        <div className="mx-auto mt-3 h-[5px] w-10 shrink-0 rounded-pill bg-line" aria-hidden="true" />
        <div className="flex items-center justify-between gap-2 px-5 pt-1">
          <h2 className="min-w-0 break-words font-heading text-lg font-semibold">{title}</h2>
          <button type="button" aria-label="Close" className="flex size-11 shrink-0 items-center justify-center rounded-md text-muted" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-7 pt-3">{children}</div>
      </div>
    </div>
  );
}
