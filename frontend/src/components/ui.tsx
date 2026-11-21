// The look lives here, not in pages. Every value comes from tokens.css through the theme names
// (bg-primary, rounded-card, …); pages compose these components.
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

import Icon, { type IconName } from "./Icon";

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Card({ children, variant = "plain", className, ...rest }: { children: ReactNode; variant?: "plain" | "hero" | "soft"; className?: string } & Omit<HTMLAttributes<HTMLDivElement>, "className">) {
  const look = {
    plain: "rounded-card border border-line bg-card",
    hero: "rounded-hero bg-primary text-on-primary",
    soft: "rounded-card border border-highlight bg-highlight-soft",
  }[variant];
  return (
    <div className={cx(look, "p-4", className)} {...rest}>
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
const BUTTON: Record<ButtonVariant, string> = {
  primary: "min-h-14 rounded-md bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50",
  secondary: "min-h-11 rounded-md border border-line bg-card px-4 font-medium text-ink disabled:opacity-50",
  ghost: "min-h-11 rounded-md px-3 font-medium text-primary underline-offset-2 hover:underline disabled:opacity-50",
  danger: "min-h-11 rounded-md border border-danger bg-card px-4 font-medium text-danger disabled:opacity-50",
};

export function Button({ variant = "secondary", className, type = "button", ...rest }: { variant?: ButtonVariant } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={cx("inline-flex items-center justify-center gap-2 text-md", BUTTON[variant], className)} {...rest} />;
}

export function Fab({ label, ...rest }: { label: string } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children">) {
  return (
    <button type="button" aria-label={label} className="pointer-events-auto flex size-[60px] items-center justify-center rounded-hero bg-primary text-on-primary shadow-fab disabled:opacity-50" {...rest}>
      <Icon name="plus" size={26} strokeWidth={2.5} />
    </button>
  );
}

/** Sunken track and its items, for groups of aria-pressed buttons that render their own items. */
export const SEG_TRACK = "grid auto-cols-fr grid-flow-col gap-1 rounded-md bg-sunken p-1";
export const SEG_TRACK_WRAP = "grid grid-cols-2 gap-1 rounded-md bg-sunken p-1";
export const segItem = (on: boolean) =>
  cx("min-h-11 min-w-0 break-words rounded-sm px-2 text-sm disabled:opacity-40", on ? "bg-card font-semibold text-ink shadow-segment" : "text-muted");

/** "Who paid" / "Who it's for": a labelled group of aria-pressed buttons on a sunken track. */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  columns,
}: {
  label: string;
  options: { value: T; label: ReactNode; disabled?: boolean }[];
  value: T | null;
  onChange: (v: T) => void;
  columns?: number;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="grid gap-1 rounded-md bg-sunken p-1"
      style={{ gridTemplateColumns: `repeat(${columns ?? Math.min(options.length, 4)}, minmax(0, 1fr))` }}
    >
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          aria-pressed={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={segItem(value === o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Selected chips use ink text: brand-primary on highlight-soft is 4.43:1 in dark mode (spec 023 Q2). */
export function Chip({ selected, className, ...rest }: { selected?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cx(
        "inline-flex min-h-10 items-center gap-1.5 rounded-pill border px-3.5 text-sm",
        selected ? "border-highlight bg-highlight-soft font-semibold text-ink" : "border-line bg-card text-ink",
        className,
      )}
      {...rest}
    />
  );
}

export function List({ children, className, ...rest }: { children: ReactNode; className?: string } & Omit<HTMLAttributes<HTMLUListElement>, "className">) {
  return (
    <ul className={cx("overflow-hidden rounded-card border border-line bg-card [&>li+li]:border-t [&>li+li]:border-line-subtle", className)} {...rest}>
      {children}
    </ul>
  );
}

export function IconTile({ name }: { name: IconName }) {
  return (
    <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-highlight-soft text-primary">
      <Icon name={name} />
    </span>
  );
}

/** One list row: optional icon tile, title + meta on the left, a right column. */
export function ListRow({ icon, title, meta, right }: { icon?: IconName; title: ReactNode; meta?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-3 px-4 py-3.5">
      {icon && <IconTile name={icon} />}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="break-words text-md font-semibold">{title}</span>
        {meta && <span className="break-words text-xs text-muted">{meta}</span>}
      </div>
      {right && <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">{right}</div>}
    </div>
  );
}

export type Tone = "owed" | "owe" | "neutral";
const TONE: Record<Tone, string> = { owed: "text-owed", owe: "text-owe", neutral: "text-neutral" };

/** Money with its meaning in words: never colour alone. `label` and `figure` share one text flow
 *  with a real space, so the text reads exactly like the plain string ("you lent 21.05"). */
export function Amount({ tone, label, figure, className, ...rest }: { tone: Tone; label: string; figure?: string; className?: string } & Omit<HTMLAttributes<HTMLSpanElement>, "className">) {
  return (
    <span className={cx("font-semibold", TONE[tone], className)} data-tone={tone} {...rest}>
      {label}
      {figure !== undefined && (
        <>
          {" "}
          <span className="font-heading">{figure}</span>
        </>
      )}
    </span>
  );
}

export function Field({ label, hint, className, ...rest }: { label: ReactNode; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={cx("flex flex-col gap-1.5", className)}>
      <span className="text-sm text-muted">{label}</span>
      <input className="h-[50px] min-w-0 rounded-md border border-line bg-card px-4 text-md text-ink" {...rest} />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** Classes for inputs/selects/textareas that are not wrapped in Field. */
export const INPUT = "min-h-11 w-full min-w-0 rounded-md border border-line bg-card px-3 text-md text-ink";

export function ErrorText({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p role="alert" className={cx("break-words text-sm text-danger", className)}>
      {children}
    </p>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 px-1 pb-2 pt-5">
      <h2 className="font-heading text-md font-semibold">{children}</h2>
      {right}
    </div>
  );
}
