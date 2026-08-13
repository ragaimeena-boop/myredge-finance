# GEMINI.md — Project Rules & Context

This file is read by the Antigravity agent before it works on this project.
Put it at the **root of the repo** (workspace-level). It should stay short and
factual — "what is true about this project" — not step-by-step instructions
(those go in AGENTS.md and workflow files).

---

## 1. What this project is

A personal finance dashboard that:
- Pulls transaction and balance data daily from **SimpleFIN** (read-only
  aggregation protocol — NOT Plaid, no OAuth flow, uses a long-lived
  "Access URL" with embedded credentials).
- Stores it locally in a database.
- Categorizes transactions and computes spending / income / net-worth
  analytics.
- Renders a dashboard the user checks daily/weekly.

Single-user, self-hosted. No multi-tenant concerns. Runs on the user's own
Unraid server as a Docker container, not on public cloud.

## 2. Tech stack

- Language / framework: Python 3.11+ / FastAPI
- Database: SQLite (integer cents storage, stored in persistent data volume)
- Frontend: Jinja2 templates + HTML5 / Vanilla CSS (dark mode default per branddesign.md)
- Scheduler for the daily pull: APScheduler (US Eastern timezone `America/New_York`)
- Deployment target: Docker container on Unraid (self-hosted web dashboard)

## 3. SimpleFIN specifics the agent must respect

- The SimpleFIN **Access URL** is a secret (it contains a username:password
  pair embedded in the URL). Treat it exactly like an API key.
- Never write the Access URL into source files, commit history, logs, or
  frontend code. It belongs in an environment variable (`.env`, git-ignored)
  or a secrets file outside the repo.
- SimpleFIN's data endpoint returns transactions for a date range — the
  agent should implement idempotent upserts (matching on the SimpleFIN
  transaction `id`), not blind inserts, since the daily job will re-fetch
  overlapping date ranges.
- Respect SimpleFIN's rate/considerate-polling guidance: one pull per day is
  the plan — do not add retry loops that hammer the endpoint.

## 4. Standards

- All API routes / functions that touch money values use a fixed-point or
  integer-cents representation — never raw floats for currency math.
- Every function that talks to SimpleFIN or the database has a docstring
  and a unit test with mocked responses (never hit the real SimpleFIN
  endpoint in tests).
- No hardcoded credentials anywhere, including test fixtures — use fixture
  factories with fake data.
- Timezone-aware dates only; the user is in the US Eastern time zone
  (Florida) — daily boundaries for "today's spending" should use that zone,
  not UTC.

## 5. Constraints

- Do not add a second database technology without asking.
- Do not add cloud services (hosted Postgres, cloud functions, etc.) — this
  stays self-hosted on Unraid.
- Do not commit `.env`, database files, or SimpleFIN credentials.
- Ask before adding a new major dependency (auth library, charting library,
  ORM) — list 1-2 lightweight options rather than picking silently.

## 6. Priority order

`AGENTS.md` (role/behavior rules) → `GEMINI.md` (this file, project facts) →
built-in defaults. If the two conflict, tell the user instead of guessing.
