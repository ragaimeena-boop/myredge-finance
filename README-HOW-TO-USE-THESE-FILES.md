# How these files fit together in Antigravity

Antigravity reads a few different kinds of Markdown files, and it's easy to
mix them up (this is probably why the YouTube videos felt confusing — most
of them only cover one piece).

| File | Scope | Purpose | Where it lives |
|---|---|---|---|
| `AGENTS.md` | Behavior | *How* the agent should act — role, hard rules, what to do when stuck. Portable across tools (Claude Code, Cursor, Antigravity all read this convention). | Repo root |
| `GEMINI.md` | Project facts | *What is true* about this specific project — stack, SimpleFIN handling rules, constraints. Antigravity-specific. | Repo root |
| `branddesign.md` | Design | Visual/UX rules for anything the agent generates in the UI. Not a special Antigravity filename — just a doc the agent should be told to read (see below). | Repo root or `/docs` |
| Global `~/.gemini/GEMINI.md` | You, not this project | Rules that apply to *every* project you open in Antigravity (e.g., "always explain destructive commands before running them"). Set via Antigravity → Settings → Customizations → "+ Global." | Your home directory, not the repo |
| Workspace rules `.agents/rules/*.md` | Project, split by topic | Optional — if GEMINI.md gets long, split it into topic files here (e.g., `security.md`, `testing.md`). | `<repo>/.agents/rules/` |

**Important nuance from how Antigravity is built right now:** the Antigravity
IDE's own "Global Rules" panel and the separate `gemini-cli` tool both want
to write to the same `~/.gemini/GEMINI.md` path, which can cause the two to
overwrite each other's global settings. That only matters for your *global*
rules (the ones that apply to every project) — it doesn't affect the
project-level files above. If you use both Antigravity and the Gemini CLI
day-to-day, keep your global rules short and check that file occasionally
rather than assuming it's untouched.

## Because `branddesign.md` isn't a filename Antigravity auto-loads

Unlike `AGENTS.md`/`GEMINI.md`, there's no special auto-read convention for
a design file. Two ways to make sure the agent actually uses it:

1. Reference it explicitly from `GEMINI.md`: add a line like
   `See branddesign.md for all UI/visual decisions.` — since GEMINI.md is
   auto-loaded, the agent will follow the pointer.
2. Or paste its content into a Skill (Antigravity supports project
   `SKILL.md` files that only get loaded when relevant — good if you don't
   want design rules loaded into every single task, only UI ones).

## Suggested build order (so you're not staring at a blank repo)

1. **Data layer first, no UI.** Get one script that calls SimpleFIN's
   Access URL, saves the raw JSON, and stores transactions in the database.
   Verify the numbers against your actual bank statement by hand once.
2. **Categorization.** Simple rule-based categorization (merchant name
   contains X → category Y) before anything fancy. You can always add
   smarter categorization later.
3. **The daily job.** Wrap step 1 in a scheduler so it runs once a day and
   upserts (see GEMINI.md's note on idempotent upserts).
4. **One dashboard screen.** Just the headline numbers + one trend chart.
   Resist adding more until this feels solid.
5. **Everything else** (transaction list, category drill-down, budgets)
   comes after you trust steps 1-4.

Give Antigravity one of these steps at a time as a task — not "build the
whole app" — so you can review and course-correct as you go.
