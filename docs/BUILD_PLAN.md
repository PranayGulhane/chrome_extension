# Build Plan — LinkedIn Job Outreach Assistant

Source of truth for scope: `docs/prd.html`. This file is the feature breakdown; it does not change often.
For **current status**, read `docs/PROGRESS.md` instead — that's the file a new session should read first.

## Structure: vertical feature slices, not backend-first phases

Originally this was planned as backend-first phases (all backend modules, then the extension, then the web
SPA). That was restructured on 2026-07-01: instead, we build one **feature** at a time, and a feature isn't
done until it's usable end-to-end — backend *and* whichever frontend (extension panel or web SPA) actually
exposes it. The old phase-based backend work (Auth, Profiles) is kept exactly as built; it just now serves as
the backend half of Features 1 and 2 below rather than being phases in their own right. See
`docs/PROGRESS.md`'s "Backend module log" section for that history — it wasn't redone, just reframed.

## Features

| # | Feature | Depends on | Delivers |
|---|---------|-----------|----------|
| 1 | Extension shell + Login | — | Installable MV3 extension, Alt+J opens the floating panel, login/logout against the existing auth API, JWT in `chrome.storage.local`. Foundational for every other extension feature. Backend (auth) already done. |
| 2 | Profile management (Web SPA) | — | Real UI over the existing profile backend: create/edit/list/clone/set-default/delete. Backend already done. |
| 3 | Resume upload & parsing | 2 | Cloudflare R2 storage, pdfplumber/pypdf extraction, Resume Parser agent (A3), upload+review UI in the Web SPA. |
| 4 | Post extraction + JD parsing | 1 | Content script (post detection incl. "see more" expansion), JD Parser agent (A1), extracted-JD display in the panel. |
| 5 | Email drafting | 2, 4 | Email Drafter agent (A2) using parsed JD + selected profile, editable draft in the panel, `agent_usage_logs` token accounting. |
| 6 | Gmail connect + send | 3, 5 | Google OAuth2 PKCE (`gmail.send` scope only), encrypted token storage, send with active resume attached, token refresh. |
| 7 | Application tracker | 4 (min.), richer once 5/6 exist | `applications` table, extract→draft→send lifecycle, outreach-type branching (email/linkedin_dm/apply_via_link/reach_out_other), was_truncated flag, History tab in the extension, full tracker view in the Web SPA. |
| 8 | Metrics + Admin dashboard | 7 | Per-user usage metrics (extension/web), admin-only aggregate dashboard (Web SPA), invite-code generation UI. |
| 9 | *(v2)* Post Relevance Scorer | 4 | Agent A4 — match score + reasoning shown in the panel. |

## Backlog (cross-cutting, not tied to one feature)

- **Fix N+1-style round-trip cost on nested-aggregate reads.** `profile_service.get_profile`/`create_profile`/
  `update_profile`/`clone_profile` use `selectinload` for all 7 of `UserProfile`'s child relationships. That's
  correct — it avoids the cartesian-product row blowup `joinedload` would cause with multiple to-many
  relationships in one query — but each relationship is still a separate sequential round trip. Against this
  project's CockroachDB Cloud dev cluster (~1–3.5s/round-trip, see `docs/PROGRESS.md`), a single full-detail
  profile fetch costs ~7 round trips (~15-25s). Fine as a dev-cluster observation, not fine as a standing perf
  characteristic once this is user-facing latency. Same pattern will recur for `applications` (Feature 7) if it
  grows nested child tables.
  Candidate fix (favor this over just tolerating it): replace the ORM `selectinload` fetch with a single hand-
  written SQL query per aggregate, using correlated subqueries with `json_agg`/`COALESCE(..., '[]')` to build
  each child collection as a JSON array inline — one round trip total regardless of how many child tables, no
  row multiplication. Parse the resulting JSON directly into the Pydantic response models. Do this for
  `profiles` first, then reuse the pattern for `applications` when Feature 7 needs it.
  Out of scope for the fix: reducing DB round-trip latency itself (region choice, connection pooling like
  PgBouncer) — that's infra, not query design, and doesn't fix the round-trip *count* problem anyway.
- **Any future read-modify-write endpoint needs `with_serialization_retry`** (added in `core/database.py` during
  the Phase 1+2 gap-closing pass — see `docs/PROGRESS.md`). CockroachDB's SERIALIZABLE isolation can abort a
  transaction under write contention (SQLSTATE `40001`) and expects the client to retry; without this helper
  that surfaces as an unhandled 500. Gmail token refresh (Feature 6) and application status updates (Feature 7)
  are the next places this will matter.

## Conventions locked in by the PRD (don't re-derive these)

- DB: CockroachDB, PostgreSQL wire-compatible, accessed via SQLAlchemy (async, `postgresql+asyncpg` dialect).
- Migrations: Alembic only, no manual DDL.
- Agent orchestration: LangGraph (StateGraph/functional API) + Pydantic v2 structured outputs. Never LangChain's
  legacy `initialize_agent`/`LLMChain`/`AgentExecutor`.
- LLM provider: Groq API. Model IDs live in config, never hardcoded — re-check against
  `console.groq.com/docs/deprecations` before release.
- PDF parsing: pdfplumber primary, pypdf fallback. Never PyMuPDF (AGPL-3.0).
- File storage: Cloudflare R2 (S3-compatible via boto3), path convention `resumes/{user_id}/{profile_id}/{upload_id}.pdf`.
- Auth: JWT (15 min access / 7 day refresh). Invite-only signup — no public registration.
- Gmail scope: `gmail.send` only.
- Monorepo layout: `backend/<module>/{models,schemas,service/,routers/}.py` per module; `frontend/extension` +
  `frontend/web`.

## Workflow

1. Build one feature at a time, end-to-end (backend + the frontend that exposes it). Wait for explicit "build
   feature N" before starting the next.
2. At the end of each feature, update `docs/PROGRESS.md` with what was built, key file paths, decisions/gotchas,
   and how to verify it — before considering the feature done.
3. A fresh session should be able to read only `docs/PROGRESS.md` (not the full PRD) to know what exists and
   resume work.
