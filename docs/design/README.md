# Sharelo design

Approved by Kamran on 2026-11-20. This folder is the source of truth for the look of the app.

## Files

| File | What it is |
|---|---|
| `tokens.css` | Every colour, font, size, radius and spacing value, light and dark. The only place these values live. |
| `logo-mark.svg` | App mark (two halves of one coin). Use for header, favicon, PWA icons. |
| `logo-mark-dark.svg` | Mark for dark backgrounds / dark mode. |
| `screens/Main.dc.html` | Brand board: logo lockups, colours, type. |
| `screens/Expenses.dc.html` | Expenses list (390 px phone). |
| `screens/AddExpense.dc.html` | Add-expense bottom sheet. |
| `screens/Balances.dc.html` | Balances, suggested payments, Move to Home, Share. |

The `screens/*.dc.html` files are design references written as HTML with inline styles: read the
markup for exact layout, sizes and values. They are not app code and are not served.

## Brand rules

- Wordmark: "sharelo", lower case, Space Grotesk 600, letter-spacing about -2% of size, next to
  the mark. Rendered as text in the app, never as an image.
- Headings and amounts: Space Grotesk 600. Everything else: Inter 400/500/600.
- Money colours carry meaning: `--money-owed` (teal) = you are owed / you lent;
  `--money-owe` (amber) = you owe; `--money-neutral` = personal or settled. Always pair the
  colour with the words ("you lent", "you owe"), never colour alone.
- Cards: white surface, 1 px `--border`, `--radius-lg`. Page ground `--surface-ground`.
- Segmented controls ("Who paid", "Who it's for"): sunken track, selected item is a white pill
  with `--shadow-segment`.
- Primary button and FAB: `--brand-primary`, white text, min height 56 px (button) / 60 px (FAB).
- Bottom nav: 4 items, active item in `--brand-primary` and weight 600.
- Icons: simple 2 px stroke line icons, round caps; no emoji.
- Touch targets ≥ `--tap-min`.

## How to change the look

After **every** edit of `tokens.css` or `logo-mark.svg` here, run both steps:

```
cp docs/design/tokens.css frontend/src/styles/tokens.css
make icons
```

`make icons` (`frontend/scripts/brand-assets.mjs`) regenerates the PNG icons, `favicon.svg`,
`offline.css`, the self-hosted fonts and `public/icons/brand-stamp.json`. Two vitests in
`frontend/guard/design.test.tsx` stay red until both steps are done:
`test_app_tokens_are_identical_to_design_tokens` (the copy) and
`test_generated_brand_assets_are_current` (the stamp: logo sha256, `--brand-primary`, tokens sha256).

The app reads these values through `frontend/src/styles/theme.css` (Tailwind names such as
`bg-primary`, `text-owe`, `rounded-card`, `font-heading`); the manifest and `<meta theme-color>` read
them from the same file at build time. No colour, font family or palette class may be written
anywhere else in `frontend/src` (guard tests). `--danger` / `--danger-soft` were added by ticket 023
for errors and destructive actions (not money).
