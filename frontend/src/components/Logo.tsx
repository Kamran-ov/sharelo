/** The mark from docs/design/logo-mark.svg, coloured by tokens. The dark tokens are exactly the
 *  colours of logo-mark-dark.svg, so this one component is both files (guard/design.test.ts). */
export default function Logo({ size = 32, wordmark = false }: { size?: number; wordmark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden={wordmark ? true : undefined} role={wordmark ? undefined : "img"} aria-label={wordmark ? undefined : "Sharelo"} data-testid="logo-mark">
        <rect width="48" height="48" rx="14" fill="var(--brand-primary)" />
        <path d="M24 8 A9 9 0 0 0 24 26 Z" fill="var(--text-on-primary)" />
        <path d="M24 22 A9 9 0 0 1 24 40 Z" fill="var(--brand-highlight)" />
        <path d="M24 8 L24 40" stroke="var(--brand-primary)" strokeWidth="2" />
      </svg>
      {wordmark && (
        <span className="font-heading font-semibold tracking-[-0.02em] text-ink" style={{ fontSize: size * 0.75 }}>
          sharelo
        </span>
      )}
    </span>
  );
}
