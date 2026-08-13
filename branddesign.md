# branddesign.md — Visual & UX Guidance for the Finance Dashboard

Read this before generating any UI. The goal is a dashboard you'll actually
open every day — calm, legible, and fast to scan, not a flashy demo.

## Design principles

1. **Numbers first.** This is a data product. Typography and spacing matter
   more than color or illustration. Every screen should answer "how am I
   doing" in under 3 seconds of scanning.
2. **Calm palette, not a "fintech" gradient.** Avoid the generic
   purple-to-blue gradient look. Use a neutral base (off-white / near-black
   in dark mode) with ONE accent color, plus a strict semantic pair for
   money direction.
3. **Dark mode is the default** — this gets checked at night/early morning.
   Light mode is a toggle, not the primary design target.

## Color system

- Background (dark): near-black, not pure `#000` — e.g. `#0F1115`
- Surface / card: one step lighter than background — e.g. `#171A21`
- Text primary: near-white, ~90% opacity — avoid pure `#FFF` (too harsh)
- Text secondary: ~60% opacity of text primary
- Accent (brand): pick ONE — a muted teal or blue reads as "finance" without
  being generic-fintech-purple. Use it sparingly: active nav item, primary
  buttons, key chart line.
- Semantic (money direction) — keep these consistent everywhere, no
  exceptions:
  - Income / positive: green
  - Spending / negative: warm red-orange (not pure red — pure red reads as
    "error/alert," which causes false alarm fatigue on a screen you check
    daily)
  - Transfers / neutral: gray, visually de-emphasized vs. real spending

## Typography

- One typeface family, two weights (regular + semibold) is enough.
- Numbers: use a font with **tabular figures** (numbers align in columns) —
  this matters a lot for scanning transaction lists and totals. Most system
  UI fonts (Inter, system-ui) support this via `font-variant-numeric:
  tabular-nums`.
- Large hero numbers (e.g., "This month: $X spent") get real size —
  32–48px — the rest of the UI stays modest (14–16px body).

## Layout

- Dashboard home = one screen, no scrolling on desktop if possible:
  - Top: this month's income vs. spending, at a glance (big numbers, not
    a chart, for the headline).
  - Middle: a trend chart (last 6–12 months) — one line or bar set,
    not a cluttered multi-series chart.
  - Bottom / side: category breakdown (top 5–8 categories, everything else
    collapsed into "other").
- Transaction list is a separate, secondary screen — dense, sortable,
  filterable, monospace-ish numbers, small row height (you're scanning,
  not admiring).
- No empty-state illustrations, no onboarding confetti — this is a tool
  you'll use for years, not a consumer app optimized for first impressions.

## Components

- Charts: keep to 2 chart types max (line for trends, horizontal bar for
  category breakdown). Don't let the agent reach for pie charts — they're
  hard to compare at a glance; horizontal bars read faster.
  Recommended library: keep it lightweight — `recharts` or `Chart.js` if
  the stack is JS; `plotly` if Python-based.
- Cards: flat, 1px border or subtle shadow — not heavy drop shadows.
  Rounded corners, modest (6–10px), not the "everything is a pill" look.
- Numbers use consistent sign/color conventions everywhere — never rely on
  color alone (add a `+`/`-` or an icon too, for accessibility).

## What to avoid

- Gamification (streaks, badges, confetti) — this is a serious daily tool.
- Stock "finance dashboard" template clichés: bright purple gradients,
  3D-ish card stacks, generic robot/AI mascot icons.
- Cramming every possible metric onto the home screen — resist scope creep;
  the home screen is for the 3-4 numbers that matter daily.
