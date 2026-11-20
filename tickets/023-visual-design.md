---
id: 023
title: Apply the Sharelo visual design from one token file
status: ready
risk: normal
depends_on: [017]
pr:
---

## Goal
Every page looks like the approved design in `docs/design/`, and the whole look is controlled
from ONE file: changing a colour, font or radius there changes every page, with no page-by-page
edits.

## Scope
- Single source: `frontend/src/styles/tokens.css` is a copy of `docs/design/tokens.css` (CSS
  custom properties, light + dark). A test asserts the two files are identical, so the design
  folder and the app never drift.
- `frontend/src/styles/theme.css` imports `tokens.css` and maps the variables into Tailwind v4's
  `@theme` (colours `primary`, `highlight`, `owed`, `owe`, `ground`, `card`, `ink`, `muted`, …;
  fonts `heading`, `body`; radii). Components use only these names (`bg-primary`,
  `text-owe`, `rounded-card`, `font-heading`) or `var(--…)`.
- Guard test: no hex/rgb colour literal and no font-family name in any `frontend/src/**/*.{ts,tsx,css}`
  except `tokens.css` (grep test, with a red proof).
- Fonts: Inter and Space Grotesk self-hosted under `frontend/public/fonts` (woff2,
  `font-display: swap`) so the app does not depend on Google at runtime.
- Logo: one `<Logo />` component rendering `docs/design/logo-mark.svg` inline (dark variant
  under dark mode) plus the "sharelo" wordmark as text. Used in the header and the login page.
  Favicon and PWA icons (192, 512, maskable) generated from `logo-mark.svg` by a committed script
  (`make icons`), replacing the placeholder icons from 015.
- Restyle every existing page to match `docs/design/screens/*.dc.html`: login, groups, join,
  group shell with bottom nav, expenses list (hero balance card, month header with total,
  row with category icon tile and coloured share), add/edit sheet (big amount, chips,
  segmented controls, Advanced, Save), balances (member list, suggested payments, Settle,
  Move to Home, Share), recurring, settings. Pages without a reference screen use the same
  components.
- Shared UI components (`Card`, `Button`, `Segmented`, `Chip`, `ListRow`, `Sheet`, `BottomNav`,
  `Amount`) so the look lives in components, not repeated per page.
- Dark mode via `prefers-color-scheme` from the tokens only.

## Out of scope
- New features or copy changes beyond what the design shows. Analytics charts.

## Acceptance
- Changing `--brand-primary` in `tokens.css` alone changes the primary colour on every page
  (KEY test: e2e sets an override value, screenshots the expenses list and balances, asserts the
  FAB and Settle button computed colour equals the new value; red when any of them uses a
  literal).
- Guard test finds zero colour/font literals outside `tokens.css`; red proof by adding one.
- `tokens.css` copy test passes; red proof by editing one value.
- e2e screenshots (390×844, light and dark) of: login, groups, expenses list, add sheet,
  balances, recurring, settings, join page. REPORT puts each next to the matching
  `docs/design/screens/` board name and lists visible differences.
- All existing e2e and unit tests still green; no horizontal scroll at 390 px.
- Contrast: text tokens on their surfaces ≥ 4.5:1 (a unit test computes it from `tokens.css`).

## Notes
- Reviewer may open the committed PNGs and compare them with the board descriptions in
  `docs/design/README.md`.
- Decision (Kamran): one place for all brand values; per-page styling is not acceptable.
