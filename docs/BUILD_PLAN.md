# Build Plan — LinkedIn Job Outreach Assistant

Source of truth for scope: `docs/prd.html`. This file is the feature breakdown; it does not change often.
For **current status**, read `docs/PROGRESS.md` instead — that's the file a new session should read first.
Feature 12 below has its own deep-dive exploration doc, written before it was scoped into the PRD:
`docs/FORM_AUTOFILL_EXTENSION.md`. Read it before starting that feature — this table only summarizes
it. (A related but not-yet-scoped exploration, `docs/OPPORTUNITY_SOURCES_EXTENSION.md` — sourcing
opportunities from company career pages rather than filling a form the user already found — is not
in this table yet; it hasn't been added to the PRD or planned as a feature.)

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
| 10 | Extension→SPA link, Archiving, Invite/Admin lifecycle | 7, 8 | "Open web app" link in the extension panel; application archive/unarchive (extension History tab + Web SPA tracker); invite codes gain expiry + manual revoke + used-by tracking; admin can revoke a user's access, extend their 30-day-default access window (date picker), and attach notes. |
| 11 | Duplicate-contact warning at extraction time | 6, 7 | Right after a post is parsed, the extension warns if the poster or recipient email was already contacted from a different application — shown before any drafting happens, with an in-panel popup showing that record without leaving the current extraction result, and a "Don't save this" option to discard the redundant new record before any drafting begins. |
| 12 | *(v2)* Application form autofill | 1, 2, 3 | PRD §14. Two-step form fill on **any site**, not just LinkedIn: (1) known fields (name/email/phone/employer) autofilled from the active profile via `autocomplete` attribute → label-heuristic matching → small LLM-classifier fallback, written in via native-setter + dispatched events (React/Vue-controlled-input compatibility); (2) open-ended questions drafted by new agent A5 (Form Answer Drafter), grounded in profile/resume/JD context, reused/edited via a new `form_answers` table. Never auto-submits, never auto-advances a multi-step form, never attempts to solve/bypass a CAPTCHA. **Before starting:** an explicit host-permission model decision is needed (per-site allowlist vs. `activeTab`) — see `docs/FORM_AUTOFILL_EXTENSION.md` §5. |
| 13 | *(v2)* Gmail Follow-Up Manager | 6, 7 | PRD §11. New "Manage Gmail" extension panel view over the user's **whole Sent mailbox**, navigated by **pagination newest-first** (page size 10/20/50/100, user-selectable) with an **optional date-range filter** on top — not a required batch load (corrected mid-design from an earlier date-range-required draft; see PRD §11's Open Question). Each paged-through message is cached into a new `gmail_sent_messages` table and flagged `Platform` or `External` by matching `gmail_message_id` against `applications` (new `applications.gmail_message_id`/`gmail_thread_id` columns, not persisted today despite `gmail_service.send_message` already returning the id). Mailbox-summary metrics (sent via platform / follow-ups sent / replies detected / response rate / awaiting response / avg. days-to-reply) computed over what's been paged through so far, plus Gmail's own approximate `resultSizeEstimate` as a headline "~N sent" count — not a whole-mailbox aggregate, a deliberate trade-off of the pagination model, surfaced in the UI. Sortable/filterable Sent Mail table (source badge, recipient, subject, sent date, last follow-up date, reply status) — filters apply within the current page only. "Follow up" drafts a reply via new agent A6 (Follow-Up Drafter) — grounded in the full original email for Platform rows, subject-only for External rows (no body was ever read) — editable, sent in-thread (`threadId` + `In-Reply-To`/`References` headers) via a new `mail_followups` table. "Archive" sets `gmail_sent_messages.is_archived` (independent of the tracker's own `applications.is_archived`) to stop further follow-up suggestions on that row. **Requires widening the Gmail OAuth scope** from `gmail.send`-only to `gmail.send` + `gmail.metadata` (headers/labels only, never bodies, and not limited to platform-sent threads — Google enforces the body restriction server-side) — every already-connected user must reconnect once to re-consent before follow-up features work for them. |

## Backlog (cross-cutting, not tied to one feature)

- ~~Fix N+1-style round-trip cost on nested-aggregate reads.~~ — **fixed** (backlog cleanup session
  after Feature 9). `profile_service.get_profile`/`create_profile`/`update_profile`/`clone_profile`/
  `set_default_profile` all now call a new single-round-trip `_fetch_profile_response` (hand-written
  SQL via `sqlalchemy.text()`, correlated `json_agg` subqueries per child collection, including the
  nested `experience_projects`-under-`experiences` case) instead of the 7-`selectinload` ORM fetch.
  Verified: a full-detail `GET /profiles/{id}` dropped from the documented ~15-25s to ~1.7s on the
  same dev cluster. Write logic (`_apply_children`, `_demote_other_defaults`) was left untouched —
  only the trailing "re-fetch fully-hydrated and return" step every mutator already did changed.
  See `docs/PROGRESS.md`'s backlog-cleanup log for the full design (including the
  `personal_info`-is-now-a-Pydantic-model-not-a-dict ripple fix in `application_service.py`).
  Still open: the same pattern hasn't yet been applied to `applications` (Feature 7's tracker reads
  are flat, no nested child tables today, so there's no N+1 there to fix yet — revisit if that
  changes). Out of scope, unchanged: reducing DB round-trip latency itself (region choice, connection
  pooling like PgBouncer) — that's infra, not query design.
- **Any future read-modify-write endpoint needs `with_serialization_retry`** (added in `core/database.py` during
  the Phase 1+2 gap-closing pass — see `docs/PROGRESS.md`). CockroachDB's SERIALIZABLE isolation can abort a
  transaction under write contention (SQLSTATE `40001`) and expects the client to retry; without this helper
  that surfaces as an unhandled 500. Gmail token refresh (Feature 6) and application status updates (Feature 7)
  are the next places this will matter.
- ~~Retrofit `agent_usage_logs` instrumentation onto the JD Parser (Feature 4) and Resume Parser (Feature 3)
  agents.~~ — **fixed** (backlog cleanup session after Feature 9). Both agents now return
  `tuple[Output, AgentUsageInfo]` (same `include_raw=True` + timing pattern as Email Drafter/Relevance
  Scorer), and `application_service.py`/`resume_upload_service.py` log an `AgentUsageLog` row for each
  in the same commit as their real persist step. All four agents (`jd_parser`, `resume_parser`,
  `email_drafter`, `relevance_scorer`) now write to `agent_usage_logs` — PRD §08's "all LLM calls are
  logged" is now actually true. Verified via `GET /metrics/me` showing real token counts for all four
  agent names after a fresh extraction + resume upload. See `docs/PROGRESS.md`'s backlog-cleanup log
  for the Resume Parser's `_looks_empty`-retry-loop interaction (usage must track whichever attempt's
  result actually gets returned, not just the first one).
- ~~Fix a real regression in the Resume Parser agent, found while testing Feature 5~~ — **fixed within the same
  session** (`method="json_schema"` instead of the default `function_calling` for `resume_parser` and
  `email_drafter`; `jd_parser` deliberately stayed on `function_calling` after `json_schema` was found to
  silently corrupt its output — see `docs/PROGRESS.md`'s Feature 5 log for the full root-cause/A-B-test story).
- **Re-verify the Resume Parser's silent-incomplete-extraction mitigation once the Groq daily quota resets.**
  A `_looks_empty()` retry was added to `agents/resume_parser/agent.py` to catch the worst case (a parse that
  comes back with nothing at all), but the account's `openai/gpt-oss-20b` daily token quota (200k/day) ran out
  mid-investigation before this could be stress-tested against the real resume that originally surfaced the bug.
  Run `docs/Pranay_Gulhane_Resume.pdf` through the real upload endpoint several times once quota is available
  again and confirm the retry meaningfully improves reliability — see `docs/PROGRESS.md`'s Feature 5 log for
  the full finding (partial misses, e.g. 1 of 3 experiences captured, aren't caught by this mitigation at all
  and may need a different approach, e.g. a smaller/differently-structured schema or a paid Groq tier).

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
- Gmail scope: `gmail.send` only through Feature 8. Feature 13 adds `gmail.metadata` (headers/labels only,
  never message bodies) for follow-up reply detection — never widen further to `gmail.readonly` or broader
  without a real reason revisited at that time (see PRD §11's Open Question).
- Monorepo layout: `backend/<module>/{models,schemas,service/,routers/}.py` per module; `frontend/extension` +
  `frontend/web`.

## Workflow

1. Build one feature at a time, end-to-end (backend + the frontend that exposes it). Wait for explicit "build
   feature N" before starting the next.
2. At the end of each feature, update `docs/PROGRESS.md` with what was built, key file paths, decisions/gotchas,
   and how to verify it — before considering the feature done.
3. A fresh session should be able to read only `docs/PROGRESS.md` (not the full PRD) to know what exists and
   resume work.
