# Progress Tracker

Read this file first in any new session. It tells you what's built, where, and what's next.
Full feature list & scope: `docs/BUILD_PLAN.md`. Full product spec: `docs/prd.html`.

**Structure note (2026-07-01):** this project moved from backend-first phases to vertical feature slices — see
`docs/BUILD_PLAN.md` for why. The "Backend module log" below is unchanged history from before that switch; it's
not being redone, just reused as the backend half of Features 1 and 2.

## Status at a glance — features

| # | Feature | Status |
|---|---------|--------|
| 1 | Extension shell + Login | ✅ done — built and manually verified in Chrome |
| 2 | Profile management (Web SPA) | ✅ done — built and manually verified in browser |
| 3 | Resume upload & parsing | ✅ done — built and manually verified in browser with a real resume |
| 4 | Post extraction + JD parsing | ✅ done — built and manually verified end-to-end in Chrome against live LinkedIn |
| 5 | Email drafting | ✅ done — verified end-to-end (backend curl; extension pending user's Chrome pass). ⚠️ a related Resume Parser fix from this feature's testing is only partially re-verified — Groq daily quota ran out mid-verification, see Feature 5 log |
| 6 | Gmail connect + send | ✅ done — verified end-to-end by the user (Connect Gmail + Send with resume attachment both confirmed working in real Chrome) |
| 7 | Application tracker | ✅ done — verified end-to-end by the user (extension wizard/DM/History tab and Web SPA tracker all confirmed working in real Chrome) |
| 8 | Metrics + Admin dashboard | ✅ done — verified end-to-end by the user (extension Usage tab, Web SPA `/metrics` and `/admin` dashboard with invite-code generation all confirmed working in real Chrome) |
| 9 | *(v2)* Post Relevance Scorer | ✅ done — backend fully verified via curl (matching/mismatched/no-profile scenarios); extension/Web SPA built and type-check clean, live browser walkthrough pending user's pass |
| 10 | Extension→SPA link, Archiving, Invite/Admin lifecycle | ✅ done — backend fully verified via curl (archive/unarchive, invite expiry/revoke/used-by, 30-day default access, admin revoke/restore/access-update, real-time expiry enforcement); extension/Web SPA built and type-check clean, live browser walkthrough pending user's pass |
| 11 | Duplicate-contact warning at extraction time | ✅ done — backend fully verified via curl (poster_profile_url match, email match, self-exclusion, discard-when-extracted/409-when-not); extension built and type-check clean, live browser walkthrough pending user's pass |

## Environment notes (checked 2026-07-01)

- Only Python 3.14 is on the system PATH via the `py` launcher. `uv` is installed (via `py -m pip install --user uv`,
  binary at `%APPDATA%\Roaming\Python\Python314\Scripts\uv.exe`). Backend will pin its own Python via
  `uv python install` inside `backend/` rather than depending on system Python, to sidestep 3.14 wheel-availability
  risk for libraries like asyncpg.
- No Docker on this machine — user chose CockroachDB Cloud (free serverless) over local Docker/binary for dev DB.
  No docker-compose file was created. A live cluster (`zebra-serpent-28425`, AWS us-east-1) exists and the auth
  backend has been verified against it — see the log below for the connection-string gotchas.
- Node.js v23.11.1 / npm 10.9.2 are on system PATH — used as-is for `frontend/extension`, no version pinning
  needed (unlike Python, no wheel-availability risk with npm).

## Feature log

### Feature 1 — Extension shell + Login — ✅ done, built and manually verified in Chrome

**What was built** (all under `frontend/extension/`):
- `public/manifest.json` — MV3, `permissions: ["storage"]`, `host_permissions` for `linkedin.com` (content
  script matches) and `http://127.0.0.1:8123/*` (dev backend — **must add the real backend origin here once
  deployed, the localhost entry alone won't cover it**), `commands.toggle-panel` bound to Alt+J, a static
  `background.service_worker`, and an `action` (toolbar icon) with no popup — clicking it also toggles the panel
  rather than opening one.
- `src/background/service-worker.ts` — the only place that talks to the backend API (deliberate — see decisions
  below). Handles `chrome.commands.onCommand` and `chrome.action.onClicked` by relaying a `TOGGLE_PANEL` message
  to the active tab's content script; handles `LOGIN`/`LOGOUT`/`GET_AUTH_STATE` messages from the content script,
  each hitting the existing `/auth/*` endpoints and reading/writing `chrome.storage.local` directly.
  `GET_AUTH_STATE` calls `/auth/me`, and on a `401` tries `/auth/refresh` once before giving up and clearing
  storage — reactive refresh-on-expiry, not a proactive `chrome.alarms` schedule (deferred, see below).
- `src/content/main.tsx` — injects a single host `<div>` + shadow root into the LinkedIn page (guarded against
  double-injection), mounts the React app inside it, injects panel CSS as a `<style>` tag *inside the shadow
  root* (not `document.head` — see decisions below), listens for the background's `TOGGLE_PANEL` message and
  for `Escape` keydown to close.
- `src/content/panelStore.ts` — a ~15-line pub-sub (subscribe/getSnapshot/toggle/close) driving the panel's
  visibility via `useSyncExternalStore`, since the toggle can be triggered from outside React (message listener,
  keydown listener) as well as from inside it (the close button).
- `src/content/App.tsx`, `LoginView.tsx`, `LoggedInView.tsx` — panel shell. On becoming visible, sends
  `GET_AUTH_STATE` and shows `LoginView` or `LoggedInView` accordingly. `LoggedInView` currently just shows the
  signed-in email/role and a sign-out button, plus an honest note that post extraction/drafting/tracker are
  still to come — no fake placeholder tabs for Home/History/Profile were built, since those belong to Features
  4, 7, and 2 respectively and would just be thrown away UI otherwise.
- `src/content/styles.ts` — plain CSS-in-a-template-string injected into the shadow root. No `.css` file import
  was used deliberately (see decisions below).
- Build tooling: `vite.background.config.ts` + `vite.content.config.ts` (two separate single-entry Vite
  **library-mode** builds, both writing into `dist/`), `package.json` (`npm run build` runs both in sequence).

**Decisions/gotchas for future sessions:**
- **All backend API calls happen in the background service worker, never in the content script.** This matches
  the PRD's own architecture diagram (content script → background → FastAPI backend) and has a concrete payoff:
  `fetch` from a background service worker is governed by `host_permissions`, not by the web page's CORS/CSP —
  so logging in from a LinkedIn page never touches LinkedIn's CSP or the backend's CORS config at all. Keep
  routing new backend calls (post extraction, drafting, etc. in later features) through background the same way.
- **Vite cannot produce one multi-entry IIFE build for this.** First attempt used a single `vite.config.ts` with
  `rollupOptions.input: {background, content}` and `output.format: 'iife'` — Rollup hard-rejects this
  (`"UMD and IIFE output formats are not supported for code-splitting builds"`), even though background and
  content share zero imports and there's no actual chunk to split. IIFE format structurally disallows
  multi-entry builds in Rollup, full stop — not fixable via config. Fixed by splitting into two independent
  single-entry **library-mode** (`build.lib`) Vite configs, run sequentially via one npm script. Any new build
  entry (e.g. an options page) needs its own config the same way, or needs to switch approach entirely (e.g. a
  bundler that doesn't have this restriction, or accept ES-module content scripts if targeting Chrome versions
  that support `"type": "module"` — not done here since static MV3 `content_scripts` entries don't support it).
- **React shipped as a dev build until explicitly forced to production.** Vite's usual automatic
  `NODE_ENV=production` replacement didn't apply in library mode — first build was 477KB/147KB gzipped for
  `content.js`, and grepping the output for `"Warning:"` confirmed React's dev bundle (with all its runtime
  checks) was included. Fixed by adding `define: { "process.env.NODE_ENV": JSON.stringify("production") }` to
  `vite.content.config.ts` explicitly. Dropped to 147KB/47KB gzipped. **If a future frontend build (Web SPA,
  options page) uses Vite library mode, check for this same trap** — don't assume `vite build` alone guarantees
  a production React bundle.
- **CSS is injected as a `<style>` tag inside the shadow root, never as an imported `.css` file.** Vite's default
  behavior for CSS imports is to inject a `<style>`/`<link>` into `document.head` — the actual LinkedIn page's
  head, not our shadow root. That would both leak our styles onto LinkedIn and defeat the entire point of using
  a shadow root. `styles.ts` exports a plain string, appended manually to the shadow root in `main.tsx`. Don't
  swap this for a `.css` import without re-solving this problem.
- **No proactive token refresh scheduling.** `GET_AUTH_STATE` refreshes reactively (on a `401` from `/auth/me`),
  which is correct but means a 15-minute-idle panel briefly shows a loading state on reopen rather than being
  instantly ready. A `chrome.alarms`-based proactive refresh (refresh a minute or two before the access token's
  known expiry) would smooth this out — deliberately deferred as unnecessary complexity for a login-only
  feature; revisit if it's noticeably slow once real workflows (post extraction, drafting) sit behind it.
- **No drag-to-reposition.** The PRD mentions the panel should be draggable if it overlaps content; not built —
  out of scope for "shell + login," revisit when a feature actually needs to interact with content the panel
  might cover (Feature 4, post selection).

**Verified:**
- Static: `dist/manifest.json` is valid JSON; both `dist/background.js` and `dist/content.js` pass
  `node --check` (valid JS syntax); both files present after `npm run build`.
- Manual, in real Chrome (done by the user, not by me — no browser-automation tool is available in this
  environment): loaded unpacked from `dist/`, confirmed on an actual `linkedin.com` page that Alt+J opens the
  panel showing a login form; logging in as the existing `pranay@example.com` admin test account shows
  "Signed in as pranay@example.com" / `admin`; Esc closes the panel; reopening with Alt+J skips straight to the
  logged-in view (session persisted via `chrome.storage.local`, not re-prompting for login); Sign out returns to
  the login form. Confirmed working with no issues reported.

**How to build and load it locally:**
```bash
cd frontend/extension
npm install   # first time only
npm run build
```
Then in Chrome: `chrome://extensions` → enable Developer mode → Load unpacked → select `frontend/extension/dist`.
Needs the backend running at `http://127.0.0.1:8123` (`cd backend && uv run uvicorn main:app --reload --port 8123`)
and an existing account to log in with (invite-only signup — see the auth backend log below for bootstrapping).

### Feature 2 — Profile management (Web SPA) — ✅ done, built and manually verified in browser

**What was built:**

Backend addition (`backend/`) — cookie-based auth alongside the existing Bearer auth, additive and
non-breaking:
- `core/security.py` — `ACCESS_TOKEN_COOKIE`/`REFRESH_TOKEN_COOKIE` constants, `set_auth_cookies()`/
  `clear_auth_cookies()`. Cookies are `httponly`, `samesite="strict"`, `secure` in non-development
  environments only (off in dev so it still works over plain `http://localhost`).
- `core/dependencies.py` — `get_current_user` now accepts **either** the `Authorization: Bearer`
  header (extension) **or** the `access_token` cookie (web app) — whichever is present.
- `auth/routers/auth_router.py` — `/auth/login`, `/auth/signup`, `/auth/refresh` now additionally set
  these cookies on top of the unchanged JSON response (extension keeps working exactly as before,
  ignores the cookies). `/auth/refresh`'s body is now optional — if omitted, falls back to the
  `refresh_token` cookie (the web app's JS can't read an httpOnly cookie to put it in a JSON body).
  New `POST /auth/logout` (no auth required) clears both cookies — needed because JS cannot clear an
  httpOnly cookie itself; the extension has no equivalent need since it just clears
  `chrome.storage.local`.

Frontend (`frontend/web/`) — new Vite + React 19 + TypeScript SPA, standard build (not the
extension's library-mode/IIFE constraints):
- `src/api/` — `config.ts` (API base URL), `client.ts` (fetch wrapper, `credentials: 'include'`,
  transparent refresh-and-retry on 401 — see bugs below), `auth.ts`, `profiles.ts`, `types.ts`
  (mirrors backend Pydantic schemas).
- `src/hooks/useAuth.tsx` — React context; checks session via `/auth/me` on load (can't inspect the
  httpOnly cookie directly — that's the point of httpOnly).
- `src/components/` — `ProtectedLayout` (route guard + topbar), one component per profile
  sub-section (`PersonalInfoSection`, `SkillsSection`, `ExperienceSection`, `ProjectsSection`,
  `EducationSection`, `CertificationsSection`, `AchievementsSection`, `LanguagesSection`), plus
  `BulletListField` (shared list-editor for responsibilities/details/descriptions).
- `src/pages/` — `LoginPage`, `SignupPage` (invite code — not in the PRD's literal web-app page list,
  added anyway since there was otherwise no way for a real new user to ever get an account outside
  of me manually seeding one via SQL), `ProfilesPage` (list), `ProfileEditorPage` (create/edit, full
  nested form), `ProfileViewPage` (read-only — added mid-build at the user's request, not originally
  planned as separate from the editor).
- `src/index.css` — small design system reusing the PRD's color palette.

**Real bugs found and fixed (roughly in the order they surfaced):**

1. **`localhost` vs `127.0.0.1` are different sites for cookie purposes.** First browser test: login
   returned 200 and set cookies, but the very next `/auth/me` call 401'd, every single time. Root
   cause: the web app runs on `http://localhost:5173` (Vite's default) but was configured to call the
   API at `http://127.0.0.1:8123` — different hostnames means different "sites" under `SameSite`
   rules, so the browser withheld the `SameSite=Strict` cookie on that "cross-site" request. Fixed by
   pointing `frontend/web/src/api/config.ts` at `http://localhost:8123` instead. **Important testing
   gap this exposed**: my own curl-based cookie-jar verification (Phase 2/backend section) passed
   cleanly and did not catch this, because `curl` does not implement `SameSite` enforcement at all —
   it just resends whatever is in its cookie jar unconditionally. Curl cannot substitute for a real
   browser when verifying cookie-auth flows; only an actual browser test caught this. If backend
   cookie logic changes again, a real browser check is mandatory, not optional.
2. **Comma-separated `preferred_work_locations` field wouldn't accept commas.** The input's displayed
   value was derived directly from the parsed array (`value.join(", ")`) and re-parsed on every
   keystroke. Typing a trailing comma with nothing after it yet produced an empty last segment that
   `filter(Boolean)` immediately dropped, so the re-render snapped the comma right back out — it
   visually never "stuck." Fixed with the same local-draft-then-commit-on-blur pattern already used
   in `BulletListField` (buffer raw text in local state; only parse into the array `onBlur`).
   **Any future free-text field that displays a value derived from a parsed array/object needs this
   same pattern** — deriving the displayed value from re-serialized parsed state fights every
   keystroke that isn't already in canonical form.
3. **Skills UI repeated the section name on every skill row** instead of grouping skills under one
   section header, unlike the PRD's "Cloud → AWS, GCP" model. Redesigned `SkillsSection` to hold its
   own local `sections` state (seeded once from the flat `SkillItem[]` prop, flattened back out via
   `onChange` on every edit) rather than being fully prop-derived — deliberately keyed by a
   **local-only stable key**, not by the category text itself, so two sections don't visually merge
   the instant their names happen to match mid-edit (e.g. typing a new section name that transiently
   collides with an existing one).
4. **Bullet-list fields (responsibilities, project/achievement details) used a raw multi-line
   textarea**, which doesn't actually look like a bullet list. Rebuilt `BulletListField` as a real
   add/remove row list (one `<input>` per bullet, `•` marker, remove button) — also immune to the
   same class of bug as #2, since each row is already a single canonical value with nothing to
   parse.
5. **Graduation year is redundant once an end date is set** on an education entry — now hidden
   conditionally (`EducationSection`) when `end_date` is filled in.
6. **Saving a fully-filled-out profile form could throw "Could not validate credentials."** Root
   cause: the access token cookie only lasts 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`), and filling
   out the full nested form easily takes longer — the save request 401'd with no recovery. Fixed in
   `api/client.ts`: `apiRequest` now catches a 401, calls `/auth/refresh` (cookie-based, no body
   needed), and transparently retries the original request once before giving up. Concurrent 401s are
   deduped into a single in-flight refresh call. **Any future page that can be left open/idle for a
   while before submitting is exposed to this same failure mode if it doesn't go through
   `apiRequest`.**
7. **`.btn` never reset the browser's default anchor underline**, so the "View"/"Edit" buttons
   (rendered as react-router `<Link>` → `<a>`) were underlined while button-based actions (Set
   default/Clone/Delete, plain `<button>`) were not — `<button>` never had that problem in the first
   place, which is why only the link-based ones looked wrong. Added `text-decoration: none` (plus
   `display: inline-flex` for consistent vertical centering) to `.btn`.
8. **Key-facts fields in the read-only profile view looked randomly positioned, then overlapped
   after the first fix.** First issue: reused `.row`, whose `.row > * { flex: 1 }` rule breaks down
   when the number of visible children varies per row (`Field` returns `null` for empty values) —
   each row's items sized inconsistently against the row above it. Fixed with a dedicated CSS grid
   (`.field-grid`, `repeat(auto-fit, minmax(160px, 1fr))`). That surfaced a second, classic CSS Grid
   bug: grid items default to `min-width: auto`, which refuses to shrink below their content's
   unwrapped intrinsic width — a long unbroken string (a URL, no spaces to wrap at) forced its column
   wider than its track and spilled into the next column, i.e. visually overlapping text. Fixed with
   `min-width: 0; overflow-wrap: break-word` on `.field-grid`'s children. **Any future CSS Grid/Flex
   layout holding long unbroken strings (URLs, IDs) needs `min-width: 0` on the item, or this
   recurs.**

**Verified, in an actual browser (not just curl):** signup with invite code, login, logout, session
persists across a page reload (cookie-backed, not lost), full nested profile create (personal info +
grouped skills + experience with a nested per-role project + personal projects + education +
certifications + achievements + languages), edit an existing profile, clone, set-default, delete, and
the read-only view page — all confirmed working by the user after the fixes above.

**How to run it locally:**
```bash
cd frontend/web
npm install   # first time only
npm run dev   # http://localhost:5173
```
Needs the backend running at `http://localhost:8123` — **use `localhost`, not `127.0.0.1`**, per bug
#1 above (`cd backend && uv run uvicorn main:app --reload --port 8123`; default bind is `127.0.0.1`
but `localhost` resolves there too, so no extra flag is needed — just don't use the `127.0.0.1` form
in the frontend config). `backend/.env`'s `CORS_ORIGINS` must include `http://localhost:5173`
(already the default).

### Feature 3 — Resume upload & parsing — ✅ done, built and manually verified in browser

**Starting state for this session (2026-07-02):** the backend half was already built and committed
in a prior session, but untracked in this file (the status table above still said "not started").
Found while resuming: `backend/agents/resume_parser/` (agent.py, schemas.py, pdf_extractor.py),
`backend/core/storage.py` (R2 upload/download), `profiles/models.py`'s `ResumeUpload` table,
`profiles/schemas.py`'s `ResumeUploadResponse`, `profiles/service/resume_upload_service.py`, the
`/profiles/{id}/resume` POST/GET endpoints in `profile_router.py`, and migration `0003` — all
present and already applied to the live CockroachDB Cloud cluster. Only the Web SPA upload+review
UI was actually missing; that's what this session built, alongside two real backend bugs found
during manual testing (see below).

**What was built this session** (`frontend/web/`):
- `src/api/types.ts` — `ResumeUploadResponse`, `ResumeParsedData`, `ResumeUploadResult` (mirrors
  `agents/resume_parser/schemas.py`'s `ResumeUploadResult`).
- `src/api/client.ts` — new `apiUpload()`, parallel to `apiRequest()` but for `FormData` bodies.
  Deliberately does **not** set `Content-Type` — the browser must set its own `multipart/form-data`
  boundary, and `apiRequest` always forces `application/json`, which would have broken the upload.
  Reuses the same refresh-and-retry-on-401 logic as `apiRequest`.
- `src/api/resumes.ts` — `uploadResume()`, `getActiveResume()`.
- `src/components/ResumeUploadSection.tsx` — upload button + hidden file input + active-resume
  filename, matching the existing one-component-per-section pattern.
- `src/pages/ProfileEditorPage.tsx` — wired the upload in. Key design point: the backend's
  `/profiles/{id}/resume` endpoint requires an existing profile row (FK), but a brand-new profile
  has no id yet. Resolved by tracking a local `profileId` state separate from the URL param — the
  first resume upload on a new profile silently `POST`s the current draft to create the row, then
  targets that id for the upload and all subsequent saves (`PUT` instead of another `POST`). If the
  user abandons the page after this point without saving, a minimal orphan profile row is left
  behind — accepted as a minor known gap rather than adding complexity to prevent it.
  `mergeParsedIntoDraft()` merges the parser's output into the in-memory draft (never auto-saved):
  scalar fields only overwrite when the parser actually found a value (`stripEmpty`), list sections
  (skills/experience/etc.) are replaced wholesale rather than appended — re-uploading a resume is
  "start over from this file," not a merge of two resumes.

**Two real backend bugs found and fixed during manual testing** (not in the code found at session
start — both only surfaced against a real, detailed resume; a synthetic short test resume built
during verification didn't trigger either one):
1. **Errors were silently swallowed.** `resume_upload_service.upload_and_parse_resume` caught any
   parser exception and re-raised a generic `ResumeParsingError` with no logging anywhere, and
   `main.py` never configured Python logging at all — so the real cause never reached the console,
   only a generic "Resume Parser agent failed to process this resume." reached the client. Fixed:
   `logging.basicConfig(level=logging.INFO)` added to `main.py`; `resume_upload_service.py` now
   does `logger.exception(...)` before re-raising. **Any future agent (JD Parser, Email Drafter)
   wrapping an LLM call in a similar try/except-and-wrap-generic pattern should log the real
   exception the same way** — otherwise every failure looks identical from the outside.
2. **Groq `openai/gpt-oss-20b` truncated the structured-output tool call on a real (multi-section,
   detailed) resume**, because `agent.py`'s `ChatGroq(...)` never set `max_tokens` — Groq's default
   wasn't enough to finish emitting the JSON, so it cut off mid-string (400 "Failed to parse tool
   call arguments as JSON" / `tool_use_failed`). First fix attempt (`max_tokens=8192`) traded one
   failure for another: this account's tokens-per-minute limit for this model is only **8000**
   (`on_demand` tier), and Groq counts `prompt + max_tokens` against that limit up front — 8192
   alone exceeded it (413 `rate_limit_exceeded`) even as the very first request in a fresh minute.
   Settled on `max_tokens=4096`, which fit under the 8000 TPM budget alongside this resume's prompt
   and was enough to avoid truncation. **This is a hard ceiling, not fully solved**: an
   exceptionally long resume's prompt tokens alone could still approach 8000, or an exceptionally
   detailed one could still need more than 4096 output tokens — both are fundamentally in tension
   under an 8000 TPM cap. If either happens, the real fix is upgrading the Groq account off the
   `on_demand` free tier, not further tuning this constant.

**UI polish pass** (after the first successful real-resume parse, per user feedback in-session):
- `ProfileViewPage.tsx` — skill categories still stack one below another, but each category's
  skill names now wrap into responsive columns (`.skill-grid` in `index.css`, `repeat(auto-fill,
  minmax(140px, 1fr))`) instead of one skill per line, which left a lot of dead space on wide
  screens.
- `ProfilesPage.tsx` — the profile list's `professional_summary` preview (and `target_job_title`,
  defensively) now truncates to a single line with an ellipsis (`.truncate` in `index.css`) instead
  of wrapping across multiple lines and making the row look broken. Needed `flex: 1; min-width: 0`
  on the info wrapper too — `text-overflow: ellipsis` silently does nothing without a constrained
  width to overflow against, which a flex child doesn't have by default.
- `index.css`'s `.btn` gained `white-space: nowrap` — a crowded `.item-actions` row (View / Set
  default / Clone / Edit / Delete) could squeeze a button narrow enough to wrap its own label onto
  two lines; nowrap makes it overflow its own box instead, which reads better than a wrapped label.

**Verified, in an actual browser (not just curl):** uploaded the user's real resume against a
freshly-created profile — full pipeline (R2 storage, pdfplumber extraction, Groq structured parse,
date normalization) completed and correctly populated personal info, grouped skills, experience
(including an in-progress role's "Present" end date → `currently_working_here: true`), education,
and certifications into the still-editable form; saved successfully afterward. Also curl-verified
end-to-end (signup → login → create profile → upload synthetic resume → 201 with correct parsed
JSON → `GET` active resume → 200) before the real-resume UI pass, using a synthetic PDF generated
by hand (minimal valid PDF byte structure, no PDF-writing library was available in the environment)
at `agents/resume_parser/` test time — not kept in the repo, disposable.

**Known test data left in the live dev cluster:** a `resumetest@example.com` jobseeker account with
several profiles (some minimal/junk from mid-session failed-upload retries before the `max_tokens`
fix landed), one of which has the user's real resume as its active `resume_uploads` row (and the
corresponding PDF object in the R2 bucket under `resumes/{user_id}/{profile_id}/{upload_id}.pdf`).
Harmless, but a future session doing a clean-slate check should know it's not empty. `backend/.env`
CORS_ORIGINS also gained `http://localhost:5174` as a second allowed origin (added when a stray
process was occupying Vite's default 5173 mid-session) — harmless to leave, Vite is back on 5173.

**How to run/verify it locally:** same as Feature 2 (`cd backend && uv run uvicorn main:app --reload
--port 8123`, `cd frontend/web && npm run dev`). On the profile editor page, enter a target job
title, then use the new "Upload resume" card to pick a PDF — the form below should populate from
the parse and remain fully editable before saving.

### Feature 4 — Post extraction + JD parsing — ✅ done, built and manually verified end-to-end in Chrome

**Scope correction mid-session:** the original plan (mirroring `BUILD_PLAN.md`'s original wording)
deferred all DB persistence to Feature 7. The user corrected this: PRD §05 step 7 explicitly says
the application record is saved to the DB **at extraction time** (step 4), not later — "regardless
of whether the user clicks Send." So this feature creates the `applications` table now (full PRD
shape, most columns nullable/unused until Features 5-7 populate them) and writes an `extracted` row
on every successful extraction, rather than deferring persistence to Feature 7 as originally scoped.

**What was built:**

Backend:
- `backend/agents/jd_parser/` (`schemas.py`: `JDParserOutput` — job_title, company, email, skills,
  seniority, location, is_hiring; `agent.py`: `parse_job_post()`) — same LangGraph
  `@entrypoint`/`@task` + `ChatGroq(...).with_structured_output(...)` pattern as
  `agents/resume_parser/agent.py`, reusing `settings.groq_parsing_model`. Email extraction is
  "regex + LLM verification" per the PRD: a regex pre-pass finds candidate email-looking substrings
  and passes them into the prompt; the LLM's chosen `email` is re-validated against the same regex
  afterward and nulled out if it doesn't match a real email shape (defense against hallucination).
- `backend/applications/` — new module, home of the `applications` table going forward (Feature 7
  extends this same module rather than creating a new one):
  - `models.py` — `Application` (full PRD §10 shape + `poster_headline`/`post_url`/`post_timestamp`,
    a deliberate addition beyond PRD §10's abbreviated field table since they're required extraction
    fields per §07 and would otherwise be extracted-then-discarded), `OutreachTypeEnum`,
    `ApplicationStatusEnum` — both stored as plain varchar via `native_enum=False` +
    `values_callable`, same as every other enum column in this codebase (see Phase 1's enum-storage
    bug note below — **do not** use a native Postgres `ENUM` type here, first draft of the migration
    did and had to be corrected to match the ORM's `native_enum=False`).
  - `schemas.py` — `PostExtractionRequest`, `ApplicationResponse`, `PostExtractionResponse`
    (`is_hiring` rides alongside `ApplicationResponse` rather than inside it, since it's a property
    of one parse, not a DB column — `is_hiring=false` posts are still saved like any other
    extraction), `ApplicationUpdateRequest` (partial update — `parsed_email`/`post_url`, both
    optional). `POST_SNIPPET_LENGTH = 500` (raised from an initial 300 mid-session, per the user's
    request — see below).
  - `service/application_service.py` — `create_from_extraction` (runs the JD Parser agent, then
    `_persist_application` wrapped in `with_serialization_retry` — LLM call kept outside the retry
    boundary, same split as `resume_upload_service._persist_resume_record`) and
    `update_application` (partial update of `parsed_email`/`post_url`; ownership-by-404 via
    `ApplicationNotFoundError`, same convention as `profile_service`). Only the first
    `POST_SNIPPET_LENGTH` chars of the captured post are persisted (`post_snippet`) — the full text
    is sent to the agent in-request but never stored, per PRD §10.
  - `routers/application_router.py` — `POST /applications/extract`, `PATCH /applications/{id}`
    (sets `parsed_email` and/or `post_url` — this is what powers the PRD's "no email found, enter
    one manually" flow without needing Feature 7's full 4-way outreach-type wizard, which stays out
    of scope here; `post_url` exists so the user can paste in the post's real link — see below for
    why the auto-captured one usually isn't one).
  - `alembic/versions/0004_create_applications.py`, `0005_widen_post_snippet.py` — both applied to
    the live CockroachDB Cloud cluster.
- `main.py` / `alembic/env.py` — registered `application_router`; imported `applications.models`.

Extension (`frontend/extension/src/`):
- `content/postExtraction.ts` — post-card detection does **not** use fixed CSS selectors at all
  (see "LinkedIn's actual DOM" below for why). `startSelectionMode()`/`stopSelectionMode()` use
  event delegation on `document` (capture-phase `mouseover`/`mouseout`/`click`) — a post card is
  found by climbing from the event target up through ancestors, tracking distinct profile-link URLs
  (`a[href*="/in/"]`, deduped by normalized URL since a header commonly has two separate `<a>` tags
  to the same profile — avatar image + name text), keeping the largest ancestor that still has
  exactly one distinct profile URL and stopping as soon as a second one would be included. This
  needs no class names or attributes that LinkedIn could rename on its next deploy — it only relies
  on real `href`s. Post body text is found the same structural way: among all `[componentkey]`
  descendants with substantial text, exclude any that contain another candidate (so an outer
  wrapper spanning the whole card's text never wins just by being longer) and take the longest
  remaining one. "See more" is matched by visible button text (`/see more/i`), not a class name.
  Hover highlight is inline-style mutation on the matched element, never a page-level stylesheet —
  keeps Feature 1's "never touch `document.head`" rule intact. "See more" handling follows the
  PRD's resolved Open Question: click the control, poll up to 800ms; if still truncated, **no API
  call happens** — the caller shows a retry message instead. A 3-second client-side throttle between
  extractions is a concrete LinkedIn-ToS guardrail (see decisions).
- `content/main.tsx` — `ensureMounted()` re-creates the panel's host element if it's missing or has
  fallen out of the live DOM, checked on every `TOGGLE_PANEL` message (see decisions below for why).
- `content/HomeView.tsx` — replaces the placeholder text that used to be in `LoggedInView.tsx`.
  States: idle (selection mode running) → loading → result, with a `notice` state for
  truncated/throttled/unreadable outcomes. Result view shows job title/company/seniority/
  location/skills/poster info, an `is_hiring=false` note (informational, doesn't block), an
  always-editable "post link" field (pre-filled with the auto-captured value, save button PATCHes
  `post_url`), and — when `parsed_email` is null — a manual-email form. Both wired through one
  generalized `UPDATE_APPLICATION` message.
- `shared/types.ts` — `PostExtractionRequest`/`ApplicationDetail`/`PostExtractionResult` mirroring
  the backend schemas field-for-field; `ContentToBackgroundMessage` members `EXTRACT_POST` and
  `UPDATE_APPLICATION` (`{ applicationId, email?, postUrl? }` — generalized partial update, not a
  separate message per field).
- `background/service-worker.ts` — new `authorizedFetch()` helper (attaches the stored access
  token, retries once through `/auth/refresh` on 401 — generalizes the retry logic `getAuthState`
  already had so Features 5-7's background calls can reuse it) plus `extractPost`/
  `updateApplication` handlers.
- `content/styles.ts` — `.notice-text`/`.success-text`/`.field-grid` additions (kept separate from
  the existing `.field label` rule rather than reusing its selector, to avoid silently restyling
  the login form's labels too).

**Decisions/gotchas for future sessions:**
- **LinkedIn ToS posture (see the approved plan for full reasoning):** extraction is single-post
  and click-initiated only — there is no "scan all posts" affordance, and there must never be one.
  Event delegation only makes newly-rendered posts *clickable*, it doesn't auto-extract them. A
  3-second client-side throttle in `postExtraction.ts` is a concrete guardrail against anything that
  could look like automated rapid-fire extraction. Keep this posture for Features 5-7 too — nothing
  about "processing more posts faster" should ever be added without revisiting this.
- **LinkedIn's actual DOM (confirmed live, 2026-07 — this WILL go stale, LinkedIn redesigns
  often).** The original plan assumed classic LinkedIn markup (`data-urn`, `.feed-shared-update-v2`,
  BEM-style class names) — **none of it exists anymore** on the Posts search-results page. Live
  investigation found: every CSS class is a short hashed/atomic string (e.g. `_485d57b6`) that
  regenerates on each LinkedIn deploy, so **no fixed class-name selector can ever be stable here**.
  Fine-grained pieces (name, timestamp) carry a `componentkey` attribute, but its value is a
  per-render UUID, not a stable identifier — useless to hardcode, only useful structurally (as "a
  labeled sub-component exists here"). The one thing that *is* real and stable: profile links
  (`<a href="https://www.linkedin.com/in/...">`) — this is what `postExtraction.ts`'s whole
  detection strategy is built on (see above). **If extraction breaks again after a LinkedIn
  redesign, re-run the diagnostic scripts used this session** (walk-up-from-profile-link + dump
  `componentkey` descendants sorted by text length) rather than guessing new class names — they're
  what found the working approach the first time and should still work as a debugging method even
  if the specific structure has changed again.
- **A post header has two separate profile links to the same person** (avatar image + name text),
  and `querySelector` picking the *first* one blindly can land on the empty avatar link and find no
  name text at all. Fixed by scanning every profile link in the card and using the first one with
  non-empty text. Also: a link's visible name text isn't always separated from the connection-degree
  suffix ("2nd"/"3rd") by an actual newline — sometimes it's "Bhawana J.  • 2nd" as one continuous
  run — so it's stripped via an explicit trailing-pattern regex, not just a first-line split.
- **LinkedIn does not expose a per-post permalink in this page's markup** — no `data-urn`, no
  direct `/feed/update/...` href anywhere in the card (confirmed by dumping every `<a>` href and
  every attribute containing "urn"/"activity"). The only place a real permalink likely exists is
  behind the "…" overflow menu's "Copy link to post" action, which wasn't pursued — opening a menu
  the user didn't ask to open and reading/triggering its copy action goes a step further than the
  "single visible-button click" precedent the PRD itself sets for "see more," and risked silently
  overwriting the user's clipboard. Instead, `post_url` auto-fills with the current page URL (not a
  deep link) and the panel has an editable field + `PATCH` so the user can paste in the real link
  themselves if they want to revisit that exact post later.
- **The floating panel can go dark on LinkedIn's in-app navigation.** LinkedIn is a single-page app;
  navigating within it (e.g. feed → search results) can happen via client-side routing that rebuilds
  part of `<body>`, silently detaching the panel's host element even though the content script and
  its listeners are still running (Chrome doesn't re-inject content scripts on same-document
  navigation). Symptom: Alt+J does nothing on a page you navigated to in-app, even though it worked
  on the page you started from. Fixed in `main.tsx`'s `ensureMounted()` — re-creates the host/shadow
  root/React tree if it's missing or detached, checked right before every toggle.
- **Timestamp normalization is best-effort, not exact.** LinkedIn's visible post-header text is
  relative ("4w", "2h") with no absolute time in this page's DOM — `postExtraction.ts` prefers a
  `time[datetime]` attribute if present, else approximates from the relative text
  (`Date.now() - offset`), which can be off by however stale the relative label is.
- **`applications.skills` is `text[]`**, not the JD Parser's raw list re-serialized — same `ARRAY(Text)`
  pattern as `profile_experiences.responsibilities`.
- **Enum columns must be plain varchar (`native_enum=False`), never a native Postgres `ENUM` type**
  — the first draft of migration 0004 used `postgresql.ENUM(...)` for `outreach_type`/`status`,
  which would have created actual Postgres enum types that don't match the ORM's `_enum_column`
  helper (which persists a `String(32)` to sidestep CockroachDB's `ALTER TYPE ADD VALUE` quirks —
  same reasoning as Phase 1/2's enum columns). Caught before applying the migration; fixed to
  `sa.String(length=32)`. **Any future migration for an enum column must match this**, not use
  `postgresql.ENUM`.

**Verified (backend, live CockroachDB Cloud cluster, via curl):**
- `POST /applications/extract` with a post containing a real contact email → row created,
  `job_title`/`company`/`skills`/`seniority`/`location`/`parsed_email` all correctly populated,
  `is_hiring: true`.
- Same endpoint with a non-hiring post (a "we raised our Series A" announcement) → `is_hiring:
  false`, every job-data field left null (no hallucination).
- Same endpoint with a hiring post that has no email → job data populated correctly,
  `parsed_email: null`.
- `PATCH /applications/{id}` with a manual email → `parsed_email` updated, `post_url` untouched.
  `PATCH` with just `post_url` → updated, `parsed_email` untouched (independent partial updates).
- `post_snippet` confirmed capped around 500 chars (not 300) after the widen migration.
- `PATCH` on a nonexistent/not-owned application id → `404`. `POST /applications/extract` with no
  auth header → `401`.
- Test data left in the live dev cluster: `jdtest@example.com` (jobseeker) with several application
  rows from the above — harmless, a future session should know it's not empty.

**Verified end-to-end in real Chrome against live LinkedIn (Posts search-results page):** hover
highlighting, click → "Analysing post…" → correct result (job title/company/skills/seniority
parsed correctly, poster name clean with no "• 2nd" suffix, post body text correctly isolated from
the surrounding header/button noise) across multiple real posts. This took several iterations live
against the real page (see "LinkedIn's actual DOM" above) — the selector-chain approach originally
shipped did not work at all (0 matches on every guessed selector) and was replaced entirely with
the profile-link-climbing approach during this session, not merely tweaked.

**How to run/verify it locally:** same as Features 1-3 (`cd backend && uv run alembic upgrade head
&& uv run uvicorn main:app --reload --port 8123`; `cd frontend/extension && npm run build`, then
load unpacked from `dist/` in Chrome). Needs a logged-in extension session (Feature 1) on an actual
`linkedin.com` page — go to a Posts search-results page (search something like "genai hiring" →
Posts tab), Alt+J, hover/click a post.

### Feature 5 — Email drafting — ✅ done, backend verified end-to-end via curl

**Scope decisions made up front (see the approved plan for full reasoning):**
- **`agent_usage_logs` only instruments the new Email Drafter agent for now.** Retrofitting it onto
  the already-verified JD Parser (Feature 4) and Resume Parser (Feature 3) agents would mean
  changing their public function signatures and touching two working, tested call sites for a
  feature that doesn't strictly need it — deferred to `BUILD_PLAN.md`'s backlog instead.
- **Profile default in the panel = the user's `is_default` profile** (or the first profile in the
  list), not true "last-used profile" tracking — the PRD says "defaults to the last-used one," but
  that would need new state this codebase doesn't have yet (no application-history feature exists
  until Feature 7). Simplification, not an oversight.
- **`applications` needed zero new migration** — Feature 4 already built the full-shape table
  (`profile_id`, `drafted_email`, `resume_upload_id`, `status` were all sitting there unused). Only
  `agent_usage_logs` is new schema this feature.
- **Two endpoints**: `POST /applications/{id}/draft` (agent-invoking — generates a fresh draft) is
  separate from the existing `PATCH /applications/{id}` (plain field update, extended to also
  accept an edited `drafted_email` so manual edits save the same way `parsed_email`/`post_url` do).

**What was built:**

Backend:
- `backend/agent_usage/` (new module, no router yet — Feature 8's admin dashboard will read this
  table): `models.py` (`AgentUsageLog`: user_id, agent_name, model_used, input_tokens,
  output_tokens, latency_ms, created_at), `schemas.py` (`AgentUsageInfo` — plain pydantic, not
  DB-facing; agents return this alongside their real output, callers turn it into a row).
  `alembic/versions/0006_create_agent_usage_logs.py`, applied to the live cluster.
- `backend/agents/email_drafter/` (mirrors `jd_parser`/`resume_parser`): `schemas.py`
  (`EmailDraftOutput`: subject, body; `EmailDraftContext` — internal, not API-facing, bundles
  everything the prompt needs), `agent.py` (`draft_email()` — same LangGraph `@entrypoint`/`@task` +
  `ChatGroq(...).with_structured_output(...)` pattern as the other two agents, but with
  `include_raw=True` this time — the one new piece needed to read `raw.usage_metadata`
  (input/output tokens) off the underlying `AIMessage` for the usage log, plus a
  `time.monotonic()` wrap for `latency_ms`. Uses `settings.groq_drafting_model`
  (`openai/gpt-oss-120b`, already configured, no config change needed). System prompt: 150-200
  word brevity per PRD §08, grounded only in the given JD/profile/resume context (never invents
  facts), addresses the poster by name, references 2-3 concretely relevant skills/experiences,
  ends with a clear call to action.
- `backend/applications/` changes: `schemas.py` gained `drafted_email: dict | None` on
  `ApplicationResponse` (column already existed, just never exposed), `DraftEmailRequest`,
  `DraftedEmailPayload`, and a `drafted_email` field on `ApplicationUpdateRequest`.
  `service/application_service.py` gained `_build_profile_context()` (plain-text summary of a
  saved profile — name/headline/summary/skills-by-category/top experiences/projects, truncated to
  ~3000 chars), `create_draft()` (loads the owned application + owned profile via
  `profiles.service.profile_service.get_profile` + the profile's active resume via
  `profiles.service.resume_upload_service.get_active_resume`, both reused as-is; builds context;
  calls the agent; wraps failure as `EmailDraftingError`), `_persist_draft()` (same
  "DB-only step gets the retry, LLM call doesn't" split as `_persist_application`/
  `_persist_resume_record` — sets `profile_id`, `drafted_email`, bumps `status` to `draft_ready`
  only if still `extracted`, and writes the `AgentUsageLog` row in the same commit), and an
  extended `update_application()` that also accepts `drafted_email`.
  `routers/application_router.py` gained `POST /applications/{id}/draft` (maps
  `EmailDraftingError`→502, `ApplicationNotFoundError`→404, `profile_service.ProfileNotFoundError`→
  404 with a distinct "Profile not found" message, `SerializationConflictError`→409); the existing
  `PATCH` now passes `drafted_email` through too.
- `alembic/env.py` — added `import agent_usage.models`.

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `ApplicationDetail` gained `drafted_email: {subject, body} | null`; new
  `ProfileSummary` type; new messages `GET_PROFILES` and `DRAFT_EMAIL`; `UPDATE_APPLICATION`
  gained an optional `draftedEmail`; new `GetProfilesResponse`/`DraftEmailResponse` types.
- `background/service-worker.ts` — new `getProfiles()` (`authorizedFetch("/profiles")`) and
  `draftEmail()` (`authorizedFetch(POST /applications/{id}/draft)`); `updateApplication()` extended
  to include `drafted_email` in the PATCH body when present.
- `content/HomeView.tsx` — new `DraftEmailSection` component, rendered inside `ExtractionResult`
  only once `savedEmail` is truthy (matches the PRD's "email found → proceed to draft" gating).
  Fetches the profile list on mount, defaults the `<select>` to the `is_default` profile (or the
  first one), and a "Draft email"/"Regenerate draft" button calls `DRAFT_EMAIL` and shows the
  returned subject (input) and body (textarea) as editable fields with a "Save changes" button
  (disabled until dirty) that PATCHes `drafted_email`.
- `content/styles.ts` — extended the existing `.field input` rule to also cover `.field select`/
  `.field textarea` rather than adding new selectors.

**Decisions/gotchas for future sessions:**
- **`include_raw=True` is required to get token usage off a LangChain structured-output call** —
  confirmed by reading `langchain_groq/chat_models.py` directly (not just docs): without it,
  `.with_structured_output(...)` returns the parsed Pydantic object directly and discards the
  underlying `AIMessage` (and its `usage_metadata`/latency-relevant info) entirely. With
  `include_raw=True` it returns `{"raw": AIMessage, "parsed": Model | None, "parsing_error":
  Exception | None}` instead — `parsed` can be `None` if the tool call didn't validate against the
  schema, a new failure mode this agent's assertion converts into an `EmailDraftingError` (rare;
  not specifically tested, but the failure path is safe — no partial data can leak through).
- **A real bug was found in the *Resume Parser* agent (Feature 3) while creating test fixtures, and
  fixed as a follow-up within this same session** (user asked to prioritize it once found): uploading
  a resume reliably 400'd with `groq.BadRequestError: ... "attempted to call tool 'parse_resume'
  which was not in request.tools"` — `openai/gpt-oss-20b`, under the default `method="function_calling"`
  structured-output mode, was hallucinating a made-up tool name (matching the Python function's own
  name, not the actual bound tool name `ResumeParserLLMOutput`) whenever given this agent's real,
  long system prompt. 100% reproducible (5/5 and then another 5/5 failures against the live
  account, not a flake) — a genuine regression, not something Feature 3's original testing could
  have caught differently.
  **Root cause + fix, confirmed by direct A/B testing against the live Groq API**: switching
  `with_structured_output(...)` to `method="json_schema"` (Groq's dedicated Structured Output API,
  sidesteps tool-name selection entirely — there's no "tool" to misname) fixed it: 5/5 successful
  runs against the exact prompt that failed 100% of the time under `function_calling`.
  **This was first applied to all three agents (jd_parser, resume_parser, email_drafter) as a
  preemptive fix, which was wrong** — a second A/B test (job-post text that's unambiguously a hiring
  post) showed `json_schema` mode silently corrupts the *JD Parser's* output instead:
  `is_hiring: false` with every field null, **no exception raised at all** — worse than the loud
  resume-parser failure, since nothing signals the corruption. `function_calling` mode has never
  exhibited the hallucination bug for `jd_parser`'s specific schema/prompt (not in Feature 4's
  original verification, not anywhere in this session) — so **only `resume_parser` and
  `email_drafter` were switched to `method="json_schema"`; `jd_parser` was reverted back to
  `function_calling`** (with its original `"did not call a tool"` retry gate restored). **Do not
  "fix" `jd_parser` this same way again without re-running that same side-by-side comparison** —
  see `agents/jd_parser/agent.py`'s comment for the exact repro. All three agents re-verified
  correct after this reconciliation (JD extraction, resume upload, email drafting — see below).
- **A second, more serious Resume Parser issue found immediately after shipping the fix above,
  only partially mitigated — flagged clearly as NOT fully resolved.** Testing against a real,
  detailed resume (`docs/Pranay_Gulhane_Resume.pdf`, 3 work experiences) showed `json_schema` mode
  can also return a **successfully parsed but silently incomplete** result — no exception, no
  error, just missing data (observed: 1 of 3 experiences captured, or 0 experiences and 0 skills
  captured, in different runs of the identical input). This is worse than a loud failure because
  nothing signals it went wrong.
  **Ruled out max_tokens/reasoning-token exhaustion as the cause**: tested with
  `reasoning_effort="low"` — reasoning tokens dropped to ~11 and total output was ~1200 tokens,
  nowhere near the 4096 cap — and the incompleteness still reproduced. This looks like inherent
  model nondeterminism specifically around extracting multi-entry nested-object arrays
  (`experiences[].projects[]`) under Groq's `json_schema` constrained decoding, not a resource
  problem.
  **Mitigation applied** (`agents/resume_parser/agent.py`): kept `reasoning_effort="low"` (free
  latency/token-cost win even though it didn't fix completeness), and added a `_looks_empty()`
  check — if a parsed result has *nothing* in `professional_summary`/`experiences`/`skills`/
  `education`/`certifications`/`achievements`, treat it as a failed attempt and retry (bounded, same
  `_MAX_TOOL_CALL_ATTEMPTS`), falling back to returning it anyway if every attempt comes back this
  empty (a genuinely blank resume is possible, and there's no error to raise if every API call
  itself succeeded). **This does NOT catch the partial-miss case** (e.g. 1 of 3 experiences) — that
  can't be reliably distinguished from a real short resume without knowing the true expected count.
  The Web SPA's existing "review and correct any misparse before saving" step (per the PRD's own
  design for this agent) is the real backstop for whatever slips through this net.
  **Could not be fully re-verified end-to-end** — see the quota note immediately below. Revisit this
  once the account's daily quota resets: run the real resume through the upload endpoint multiple
  times and confirm the `_looks_empty` retry actually improves the observed success rate in
  practice, not just in theory.
- **Hit the Groq account's daily token quota (TPD) mid-investigation — a genuinely hard blocker,
  not a bug.** `openai/gpt-oss-20b` (the parsing-tier model, shared by both `jd_parser` and
  `resume_parser`) is on the free `on_demand` tier with a **200,000 tokens/day** limit. Extensive
  debugging in this session (many resume-parse and JD-parse calls, on top of whatever the account
  had already used today) drove usage to ~198k/200k, after which every further call to this model
  405/429'd with `rate_limit_exceeded` ("tokens per day (TPD)"). Confirmed this is a genuinely slow-
  draining rolling 24h window, not a per-minute limit that clears quickly — usage barely moved
  (198,354 → 198,160) over roughly an hour of elapsed time, and Groq's own suggested "try again in
  ~35 min" only refers to enough marginal headroom for one more small request, not real testing
  capacity. **Any future session hitting a 502 "Resume Parser agent failed to process this resume"
  or a similar JD-extraction failure should check the server log for `groq.RateLimitError` /
  `"tokens per day"` first** before assuming it's a code bug — this exact error was mistaken for one
  twice in this session before the pattern was recognized. `openai/gpt-oss-120b` (the drafting-tier
  model, used only by `email_drafter`) is a separate model with its own separate quota and was
  unaffected throughout. No code fix for this — either wait for the daily window to roll over, or
  upgrade the Groq account off the `on_demand` free tier (same conclusion Feature 3 already reached
  for the truncation/TPM issue, now compounded by this separate daily cap).
- **A stale `--reload` worker masked the fix during verification, wasting a debugging round.**
  Uvicorn's `--reload` (via `watchfiles`) logged `WatchFiles detected changes ... Reloading...` after
  the code edits but **never actually respawned the worker process** on this Windows machine — the
  same old Python process (confirmed via `Get-Process`/`Get-NetTCPConnection`, not just assumption)
  kept serving every request afterward, so a first re-test of the "fixed" code still failed with the
  exact original error. Had to manually find and kill the stale worker PID and start a fresh
  (non-`--reload`) process before the fix actually took effect. **If a code change doesn't seem to
  take effect against this dev server again, don't trust `--reload`'s log output — verify the
  actual worker PID is new** (`Get-Process -Id <pid>` / `Get-NetTCPConnection -LocalPort 8123`),
  or just restart uvicorn without `--reload` and restart manually after each change.
- **Email Drafter verification used two fresh throwaway accounts** (`drafttest1@example.com`,
  `drafttest2@example.com`, password `TestPass123!`) rather than reusing existing test data, so one
  could be given a profile with an active resume and one without, to exercise both branches of
  `create_draft`'s resume-context handling. The "has a resume" account's first `resume_uploads` row
  was inserted directly via a short Python/SQLAlchemy script (to unblock testing before the bug
  above was fixed) — after the fix, the real upload endpoint was also re-verified working end-to-end
  for the same account/profile.
- **`_build_profile_context` truncates to ~3000 chars and only includes the first 4 experiences /
  2 projects** — defensive against an unusually large profile blowing the drafting model's prompt
  budget, same class of risk as Feature 3's resume-parsing `max_tokens` tuning. Not yet stress-
  tested against a genuinely large real profile; if `openai/gpt-oss-120b`'s TPM limit on this
  account turns out tight (unverified — the two test drafts used ~600-650 input tokens each, comfortably
  under Feature 3's 8000 TPM ceiling story, but that was a different model), this is the first
  place to look.

**Verified (backend, live CockroachDB Cloud cluster, via curl):**
- `POST /applications/{id}/draft` against a profile **without** an uploaded resume → `drafted_email`
  populated (subject + ~150-200 word personalized body referencing real profile experience/
  projects), `profile_id` set, `status` → `draft_ready`, an `agent_usage_logs` row created
  (`model_used: openai/gpt-oss-120b`, real input/output token counts, latency_ms).
- Same endpoint against a profile **with** an active resume → resume content genuinely reflected in
  the draft body (e.g. the "cut query cost by 40%" detail from the synthetic resume appeared in the
  generated email), confirming `resume_context` actually reaches the prompt.
- `PATCH /applications/{id}` with an edited `drafted_email` → persists exactly the edited
  subject/body, `parsed_email`/`post_url` untouched (independent partial update, consistent with
  Feature 4's existing PATCH behavior).
- Draft on a nonexistent application id → 404 "Application not found". Draft on another user's
  application id → 404 (ownership-by-404, ApplicationNotFoundError). Draft using another user's
  profile id (own application, someone else's profile) → 404 "Profile not found" (distinct
  message, confirmed both branches are reachable and correctly isolated).
- Test data left in the live dev cluster: `drafttest1@example.com`/`drafttest2@example.com`
  (jobseeker, password `TestPass123!`), one profile each ("GenAI Engineer" / "Data Engineer"), one
  application each with a generated draft, one `resume_uploads` row for drafttest2 (inserted
  directly, see above) — harmless, a future session should know these exist.
- **Re-verified after the `json_schema`/`function_calling` reconciliation, against a freshly
  restarted (non-stale) server**: `POST /profiles/{id}/resume` with the real upload endpoint
  (not a direct-DB insert) → 201, full correct parse (personal info, skills, experience). Fresh
  `POST /applications/extract` on an unambiguous hiring post → `is_hiring: true`, all fields
  correctly populated (this specifically re-checks the case that `json_schema` mode had silently
  broken). Fresh `POST /applications/{id}/draft` → still produces a correct, personalized draft.

**Not yet verified: the extension UI.** No browser-automation tool exists in this environment (same
limitation as every prior feature) — `npm run build` succeeded, `node --check` passed on both
bundles, and `npx tsc --noEmit` shows only the pre-existing unrelated `shared/storage.ts` error (see
Feature 1/4 notes). The actual "Draft email" flow (profile dropdown populating, draft appearing,
edits saving) needs a real Chrome pass by the user against a freshly-extracted post, same as every
previous feature's extension half.

**How to run/verify it locally:** same as Features 1-4 (`cd backend && uv run alembic upgrade head
&& uv run uvicorn main:app --port 8123` — **omit `--reload`**, see the stale-worker gotcha above;
restart manually after any backend code change; `cd frontend/extension && npm run build`, load
unpacked). Extract a post (Feature 4 flow), then in the result view: pick a profile from the new
dropdown and click "Draft email" — a subject/body should appear, editable, with a "Save changes"
button that only enables once you've actually changed something.

### Groq multi-model fallback (all three agents) — ✅ done, mostly verified

**Why:** the same session that built Feature 5 hit two real problems with a single-model-per-agent
design: `openai/gpt-oss-20b`'s account-level daily token quota (200k/day, `on_demand` tier) ran out
mid-session and hard-blocked both `jd_parser` and `resume_parser` for hours — retrying the same
exhausted model is useless, since Groq's rate limits are per-model, not per-account. Separately,
individual models have shown schema-specific quirks this session (resume_parser's tool-name
hallucination, jd_parser's json_schema corruption) that a *different* model might simply not share.
User asked for a fallback chain: on failure, retry against a different model, up to 4 attempts.

**What was built** (`core/config.py`, and all three `agents/*/agent.py`):
- `core/config.py` — replaced the two singular `groq_parsing_model`/`groq_drafting_model` settings
  with three **per-agent** ordered lists: `groq_jd_parser_models`, `groq_resume_parser_models`,
  `groq_email_drafter_models` (index 0 = the previous single default in each case, so default
  behavior is unchanged unless a failure actually occurs). Per-agent rather than shared/per-tier,
  because `jd_parser` (proven-safe on `function_calling`) and `resume_parser`/`email_drafter`
  (proven-safe on `json_schema`) have different structured-output method requirements — a model
  that's fine under one method isn't necessarily safe under the other (this is literally the bug
  that was found and fixed earlier this same session for jd_parser).
- Each agent's retry loop now builds a **fresh `ChatGroq` per attempt using
  `models[min(attempt-1, len(models)-1)]`** (previously: same model, same client, built once
  outside the loop) — `_MAX_TOOL_CALL_ATTEMPTS` renamed to `_MAX_FALLBACK_ATTEMPTS = 4` in all
  three files. Each agent's own already-verified `method` (function_calling for jd_parser,
  json_schema for the other two) stays fixed across all 4 attempts — only the model changes.
- Broadened the caught exceptions to `(BadRequestError, RateLimitError, OutputParserException)` in
  all three agents (added `RateLimitError` — the actual exception this whole feature exists to
  route around — and `OutputParserException` where not already present), and **dropped
  jd_parser's old substring-specific gate** (`"did not call a tool" not in str(exc): raise`) — that
  gate existed specifically to avoid wasting retries against the *same* still-broken model; now
  every attempt is already a different model, so there's no reason to stop early for any of these
  three exception types. A genuine non-transient bug (bad API key, malformed request) still fails
  identically across all 4 models and surfaces as the final raised error — nothing is masked.
  `resume_parser`'s existing `_looks_empty` retry-on-suspiciously-empty-result check now also
  advances to the next model (previously the same model) — strictly better odds.
- Added `logger.warning(...)` per failed attempt (model + exception) in all three agents — none of
  them logged anything on retry before this; this is the observability needed to actually see the
  fallback chain doing its job in production logs later.
- `resume_parser`'s `reasoning_effort="low"` is now conditional
  (`"low" if "gpt-oss" in model else None`) — only the gpt-oss models are reasoning models; the
  Llama/Qwen fallback models were never tested with this param and it could error.
- `email_drafter`'s `AgentUsageInfo.model_used` now records the actual per-attempt `model` variable
  instead of the old static settings default — otherwise a fallback-generated draft's usage log
  would misreport which model actually wrote it.

**Model choices — researched live, not guessed** (`console.groq.com/docs/models`,
`/docs/structured-outputs`, `/docs/deprecations`, fetched during this session):
```
groq_jd_parser_models      = [gpt-oss-20b, llama-4-scout-17b-16e-instruct, qwen3-32b, llama-3.3-70b-versatile]
groq_resume_parser_models  = [gpt-oss-20b, gpt-oss-120b, llama-4-scout-17b-16e-instruct, llama-3.3-70b-versatile]
groq_email_drafter_models  = [gpt-oss-120b, gpt-oss-20b, llama-4-scout-17b-16e-instruct, llama-3.3-70b-versatile]
```
- Only `openai/gpt-oss-20b` and `openai/gpt-oss-120b` are confirmed to support **strict**
  `json_schema` (guaranteed schema compliance) per Groq's docs. `meta-llama/llama-4-scout-17b-
  16e-instruct` supports json_schema only in **best-effort** mode (schema compliance not
  guaranteed) — used anyway as `resume_parser`/`email_drafter`'s 3rd fallback since it's still
  better than a hard failure, but flagged as a real, accepted risk (could reintroduce a
  "successfully parsed but wrong" failure mode in a new shape).
- `llama-3.3-70b-versatile` (and `llama-3.1-8b-instant`, not used here) are scheduled for
  **deprecation on 2026-08-16** per Groq's own deprecations page — still work today, deliberately
  placed last in every list, and commented in `core/config.py` as "replace before then." **A future
  session must swap this out before mid-August 2026** or the 4th fallback slot silently stops
  working.
- `qwen/qwen3-32b` emits visible `<think>...</think>` reasoning prose in its raw content (observed
  directly, not from docs) — untested whether this ever interferes with `function_calling` tool-
  call extraction specifically (only used in `jd_parser`'s list, and only as the 3rd fallback).

**Verified:**
- All 4 model IDs in every list are real and reachable (confirmed via direct calls to the 3 models
  untouched by today's quota exhaustion: `llama-4-scout`, `qwen3-32b`, `llama-3.3-70b-versatile`).
- `function_calling` + `JDParserOutput` schema confirmed working correctly on both
  `llama-4-scout-17b-16e-instruct` and `qwen3-32b` (correct `is_hiring`/fields on an unambiguous
  hiring post) — these are exactly the models jd_parser would fall over to.
- Backend restarted fresh (not `--reload`, see gotcha above) after the refactor; re-ran the real
  `POST /applications/extract` and `POST /applications/{id}/draft` endpoints — both still succeed
  end-to-end on their primary (index-0) models, confirming the refactor didn't break the common
  path. `agent_usage_logs` confirmed to record the correct actual model (`openai/gpt-oss-120b`) for
  a real draft, not a stale default.
- **Not verified**: the fallback path has not been exercised end-to-end through the real HTTP
  endpoints with an actual induced failure (e.g. forcing `gpt-oss-20b` to fail and confirming
  `jd_parser`/`resume_parser` genuinely falls through to model index 1). `openai/gpt-oss-20b`'s
  quota partially recovered during this session (rolling 24h window) before this could be
  attempted, and inducing an artificial failure just to test it would burn more of an already-tight
  daily budget. The underlying loop/indexing logic was reviewed carefully by hand instead. If a
  future session hits a real `gpt-oss-20b` rate limit again, check the logs for
  `"... attempt N failed on model ..."` warnings to confirm the fallback actually engaged.
- `resume_parser`'s `_looks_empty`-triggers-next-model behavior specifically (as opposed to the
  bare mechanism) is similarly unverified end-to-end for the same quota reason — see the still-open
  backlog item in `BUILD_PLAN.md` about re-verifying the incomplete-extraction mitigation.

### Feature 6 — Gmail connect + send — ✅ done, verified end-to-end by the user in real Chrome

**What was built:**

Backend:
- `core/crypto.py` (new) — `encrypt_token`/`decrypt_token` using AES-256-GCM
  (`cryptography.hazmat...aead.AESGCM`), nonce-prepended-then-base64-encoded as a single string for
  a `Text` column. New `gmail_token_encryption_key` setting (32 random bytes, base64 — generated
  the same `secrets.token_urlsafe` way as `jwt_secret_key`).
- `core/config.py` — added `google_client_id`, `google_client_secret`, `google_redirect_uri`
  (default `http://127.0.0.1:8123/gmail/oauth/callback`, matching the extension's existing
  `API_BASE_URL`), `gmail_token_encryption_key`.
- `backend/gmail/` (new module): `models.py` (`GmailCredential` — one row per user, **unique**
  `user_id`; `GmailOAuthState` — short-lived, bridges the authenticated "start" call to Google's
  unauthenticated redirect callback, no cron cleanup, just a 10-minute freshness check at
  consume-time), `schemas.py` (`GmailStatusResponse`, `GmailAuthorizeResponse`),
  `service/gmail_service.py` (PKCE S256 pair generation; `start_oauth`; `handle_oauth_callback`
  — exchanges the code via `oauth2.googleapis.com/token`, fetches the Gmail address via
  `gmail.googleapis.com/.../profile`, encrypts + upserts `GmailCredential`; `get_status`;
  `disconnect` — best-effort revoke at Google's end, always deletes the local row regardless;
  `_get_valid_access_token` — refreshes via the stored refresh_token if `token_expiry` is within
  60s, re-encrypts + persists; `send_message` — builds the MIME message via stdlib `email.mime`
  and calls `gmail.googleapis.com/.../messages/send`), `routers/gmail_router.py` (`POST
  /gmail/oauth/start`, `GET /gmail/oauth/callback` — **not** authenticated, see decisions below,
  `GET /gmail/status`, `POST /gmail/disconnect`).
- `backend/applications/` — `service/application_service.py` gained
  `send_application_email(db, user_id, application_id)`: validates `drafted_email`/`parsed_email`/
  `profile_id` are set (`NoDraftError`/`NoRecipientError`), loads the active resume for the
  application's profile (`NoResumeError` if none — PRD's explicit pre-send check), downloads the
  PDF via `core.storage.download_pdf`, builds the attachment filename
  (`{FirstName}_{LastName}_{TargetJobTitle}_Resume.pdf`, sanitized), calls
  `gmail_service.send_message`, then persists `final_email_sent`/`resume_upload_id`/`sent_at`/
  `status=SENT` (same "DB-only step gets the retry, the external call doesn't" split as
  `_persist_draft`). `routers/application_router.py` gained `POST /applications/{id}/send`.
- `alembic/versions/0007_create_gmail_tables.py` — `gmail_credentials` (unique `user_id`),
  `gmail_oauth_states` (unique `state`). Applied to the live cluster.
- `pyproject.toml` — added `cryptography`; promoted `httpx` from the `dev` group to main
  dependencies (now used for real Google API calls, not just tests).

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `GmailStatus`; new messages `GMAIL_STATUS`/`GMAIL_CONNECT`/
  `GMAIL_DISCONNECT`/`SEND_EMAIL`; their response types.
- `background/service-worker.ts` — `getGmailStatus()`, `connectGmail()` (`POST
  /gmail/oauth/start` then `chrome.tabs.create({url: authorize_url})` — no new manifest
  permissions needed, `chrome.tabs.create` doesn't require the `"tabs"` permission for basic use,
  same as the existing `chrome.tabs.query`/`sendMessage` calls), `disconnectGmail()`,
  `sendEmail(message)`.
- `content/HomeView.tsx` — new `SendEmailSection`, mounted inside `DraftEmailSection`'s
  `hasDraft` block (below "Save changes"): checks Gmail status on mount; not connected → "Connect
  Gmail" button (opens the OAuth tab) + a manual "I've connected — refresh" button (no push
  notification exists for when that tab finishes, see decisions below); connected → shows the
  address and a "Send" button, disabled while the draft has unsaved edits (`canSend = !isDirty`,
  reusing `DraftEmailSection`'s existing dirty-tracking) to avoid sending stale text; success shows
  a "Sent!" confirmation in place of the button.

**Decisions/gotchas for future sessions:**
- **Backend-driven OAuth2 PKCE flow, not `chrome.identity.getAuthToken()`** — that Chrome API needs
  a Chrome-Web-Store-published extension with a stable ID tied to the OAuth client; this extension
  is loaded unpacked for dev, so its ID isn't stable. Matches PRD §09's literal wording ("Backend
  initiates a Google OAuth2 PKCE authorization code flow").
- **`GET /gmail/oauth/callback` deliberately has no auth dependency** — it's a top-level browser
  redirect from Google after consent, not a fetch from our own code, so it carries no JWT/cookie.
  The `state` row (`GmailOAuthState`, written during the authenticated `/oauth/start` call) is what
  recovers which user this belongs to; it's deleted once consumed.
- **"Connect/Disconnect Gmail" lives in the existing floating panel**, not a separate browser-level
  Options page. PRD §09 says "Options page *or* first-time setup" — building a whole new Options
  page (new Vite entry, new manifest field, new React root) was more plumbing than this needs when
  the panel already hosts the entire draft/send flow.
- **No push notification when the OAuth tab finishes.** Building `externally_connectable`
  messaging from the static callback page back into the extension was judged unnecessary complexity
  for a dev-scale flow — the panel re-checks status on mount, plus a manual "I've connected —
  refresh" button covers the rest. If this friction turns out to matter in practice, that's the
  first place to add real cross-context messaging.
- **`access_type=offline` + `prompt=consent` are both required** on the initial authorize request
  to reliably get a `refresh_token` back — without `prompt=consent`, a user who'd already granted
  this exact app access once might not get a fresh refresh_token on a later grant. If Google ever
  returns no `refresh_token`, `handle_oauth_callback` raises a clear `GmailApiError` telling the
  user to revoke prior access from their Google Account settings first, rather than silently
  storing a credential that can never be refreshed.
- **Direct `httpx` calls to Google's REST endpoints, not `google-api-python-client`/`google-auth`.**
  Only three endpoints are actually needed (token exchange/refresh, `messages/send`, `profile`) —
  pulling in Google's full SDK stack was judged more than this needs, consistent with this
  project's existing preference for direct/minimal library use (raw `pyjwt`, no auth framework).
- **MIME built with stdlib `email.mime`**, not a third-party mail library —
  `multipart/mixed` (PDF attachment) wrapping `multipart/alternative` (plain text + a minimally
  HTML-escaped/`<br>`-converted version of the same text, no rich template).
- **Disconnect always clears the local row even if Google's revoke call fails** (best-effort,
  logged via `logger.exception` but not re-raised) — the point of "Disconnect" from the user's
  perspective is that this app stops having access locally; a revoke-call network blip shouldn't
  leave them stuck unable to disconnect.
- **External dependency**: needs a real Google Cloud OAuth2 Web application client (Client ID +
  Secret) with redirect URI `http://127.0.0.1:8123/gmail/oauth/callback`. The user created this
  themselves this session and added real credentials to `backend/.env`
  (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`) — while the Google app is in "Testing" publish
  status, only Google accounts explicitly added as "Test users" on the OAuth consent screen can
  complete the flow.
- **Real bug found during the user's first live connect attempt, fixed same session**: the
  callback failed with "Could not fetch the Gmail address for this account." Server logs showed
  the actual cause — `GET gmail.googleapis.com/.../users/me/profile` returned `403
  ACCESS_TOKEN_SCOPE_INSUFFICIENT` ("Request had insufficient authentication scopes"). **Not**
  related to Web application vs. Chrome Extension OAuth client type (Web application is correct
  for this backend-driven flow, see above) — the real cause is that Gmail API's own
  `users.getProfile` endpoint requires a broader scope than `gmail.send` grants (confirmed live,
  not from docs). Fixed by requesting an additional `https://www.googleapis.com/auth/
  userinfo.email` scope alongside `gmail.send` (a separate, minimal, non-Gmail identity scope —
  discloses only the account's email address, nothing mail-related, so this doesn't violate the
  PRD's "gmail.send only, not gmail.readonly or broader" requirement, which is specifically about
  *Gmail* scope breadth) and calling `https://www.googleapis.com/oauth2/v2/userinfo` (field
  `email`) instead of Gmail's `users.getProfile` (field `emailAddress`) to fetch the address for
  display. **If this scope isn't already enabled on the Google Cloud OAuth consent screen, the
  user may need to add it there** (non-sensitive scopes usually don't need explicit re-verification
  but do need to be listed) — flag this if the same 403 recurs after reconnecting.

**Verified:**
- All new files import cleanly; `main.py`'s OpenAPI schema confirms all 5 new routes registered
  (`POST /gmail/oauth/start`, `GET /gmail/oauth/callback`, `GET /gmail/status`, `POST
  /gmail/disconnect`, `POST /applications/{id}/send`).
- `alembic upgrade head` applied `0007` cleanly to the live cluster.
- `core/crypto.py`'s encrypt/decrypt round-trips correctly with the real configured key.
- `GET /gmail/status` with no credential row → `{connected: false, gmail_address: null}`.
- `POST /applications/{id}/send` on a nonexistent application → 404 (ownership-by-404, consistent
  with every other application endpoint).
- `POST /gmail/oauth/start` with real Google credentials → a correctly-formed authorize URL
  (right `client_id`, `redirect_uri`, `scope=gmail.send`, PKCE `code_challenge`/`S256`, `state`).
- Extension: `npm run build` succeeds, `node --check` passes both bundles, `npx tsc --noEmit`
  shows only the pre-existing unrelated `shared/storage.ts` error.
- **Verified end-to-end by the user in real Chrome** (I can't drive a browser or hold a Google
  account myself, so this needed their hands-on pass): "Connect Gmail" → real Google consent
  screen → callback succeeded → status flipped to connected → drafted email sent via "Send" with
  the resume PDF attached, confirmed delivered. First live attempt hit a real bug (see the
  `users.getProfile` 403 scope issue above), fixed and reconnected successfully on the retry.

**How to run/verify it locally:** same as Features 1-5 (`cd backend && uv run alembic upgrade head
&& uv run uvicorn main:app --port 8123` — no `--reload`, restart manually after any change;
`cd frontend/extension && npm run build`, load unpacked). Extract a post → draft (Features 4/5
flow) → in the new "Send" section: click "Connect Gmail" (opens a Google consent tab — sign in with
whichever account was added as a Test user), approve, close the tab, click "I've connected —
refresh" back in the panel, then "Send". Check the recipient inbox (or the sending account's own
Sent folder) for the email with the resume PDF attached under the expected filename.

### Feature 7 — Application tracker — ✅ done, verified end-to-end by the user in real Chrome

**Scope:** the `applications` table already existed in full (built in Feature 4), including
`outreach_type`/`outreach_note`/`status` columns that had sat unused since Feature 4 deliberately
punted the full 4-way outreach wizard to this feature. This feature: (1) wires up all four outreach
paths (email/linkedin_dm/apply_via_link/reach_out_other) end to end, (2) adds list/detail tracker
endpoints, (3) adds a History tab to the extension and a full Tracker page to the Web SPA. No new
Alembic migration — every column this feature touches already existed.

**Design decisions:**
- `outreach_type` auto-sets to `email` whenever an email exists — at extraction time if the JD
  Parser found one, or whenever a manual email is saved via `PATCH`. The 4-way wizard UI only shows
  when there's genuinely no email; its 3 non-email branches are the only ones needing user choice.
- **`linkedin_dm` reuses the existing Email Drafter agent** rather than a second agent —
  `agents/email_drafter/schemas.py`'s `EmailDraftContext` gained a plain `is_dm: bool` (not an
  `OutreachTypeEnum` import, keeping agents decoupled from other modules' models — no agent in this
  codebase has DB/module coupling). `agents/email_drafter/agent.py` branches to a new
  `_DM_SYSTEM_PROMPT` (casual LinkedIn-DM tone, no salutation/signature block, ~80-120 words vs the
  email prompt's ~150-200) and a lower `max_tokens` (400 vs 1024) when `is_dm` is set. The
  `EmailDraftOutput` schema (subject+body) is reused unchanged — the DM path's "subject" is never
  shown to the user, it only exists because of the shared output shape.
- `apply_via_link`/`reach_out_other` get **no drafting at all** (PRD: "no email drafted", "user
  handles manually") — just persisting `outreach_type`+`outreach_note` is their whole lifecycle,
  which can go straight from `extracted` to `sent` (no `draft_ready` stage), unlike `linkedin_dm`
  which goes through a real draft first.
- **No backend "send" call for non-email outreach** — nothing to programmatically send (DM
  copy-paste, an external link, a manual contact). Two new manual-transition endpoints cover this:
  `POST /applications/{id}/mark-sent` (rejects `email`/unset outreach type — that path must use the
  existing Gmail `/send`) and `POST /applications/{id}/mark-replied` (PRD: `replied` is always a
  manual transition, for every outreach type, since there's no way to detect a reply without a
  broader Gmail scope than `gmail.send`). Both wrapped in `with_serialization_retry` — the backlog
  note from Feature 6 specifically flagged application status updates as the next place this
  would matter.
- **New list/detail endpoints** — only extract/PATCH/draft/send existed before. `GET /applications`
  (all of the current user's, `order_by(created_at.desc())`, unpaginated — same simplification
  `profile_service.list_profiles` already uses at this dev scale) and `GET /applications/{id}`.
  `ApplicationResponse` was already flat (no nested relationships like profiles has), reused as-is
  for both list rows and detail — no separate summary schema needed.
- **A real gap found while building this:** `ApplicationResponse` never exposed `final_email_sent`
  or `resume_upload_id`, even though both columns have existed since Feature 4/6 — no prior reader
  needed them. PRD §10 explicitly lists both ("Final Email Sent", "Resume Attached") as tracker
  fields, so this feature is what actually surfaces them. Added to the schema; not a migration
  (columns already existed), just a response-shape fix.
- Extension History tab is read-only-ish (list + inline expand-to-detail, "Mark as replied"/"Mark
  as sent" as the only write actions) — the richer follow-up experience lives in the Web SPA
  tracker page, matching the PRD's own language ("History tab" in the extension vs. "standalone web
  UI" for the full tracker).

**What was built:**

Backend:
- `applications/schemas.py` — `ApplicationUpdateRequest` gained `outreach_type`/`outreach_note`;
  `ApplicationResponse` gained `final_email_sent`/`resume_upload_id` (see gap above).
- `applications/service/application_service.py` — `_persist_application` auto-sets
  `outreach_type=EMAIL` when the JD Parser found an email; `update_application` gained
  `outreach_type`/`outreach_note` params (auto-sets `EMAIL` when `email` is provided, otherwise
  applies the explicit type/note); `create_draft` now computes `is_dm` from the application's
  outreach type and passes it into `EmailDraftContext`; new `list_applications`, `get_application`,
  `mark_sent_manually` (raises new `WrongOutreachTypeError` for `email`/unset), `mark_replied`
  (raises new `NotYetSentError` if not yet `sent`) — the latter two follow the existing
  `_persist_draft`/`_persist_sent` "DB-only step gets the retry" split via private
  `_mark_sent`/`_mark_replied` helpers.
- `applications/routers/application_router.py` — `GET /applications`, `GET /applications/{id}`,
  `POST /applications/{id}/mark-sent`, `POST /applications/{id}/mark-replied`; existing PATCH now
  passes `outreach_type`/`outreach_note` through.
- `agents/email_drafter/schemas.py`/`agent.py` — `is_dm` field + `_DM_SYSTEM_PROMPT` branch, as
  described above.

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `UPDATE_APPLICATION` message gained `outreachType`/`outreachNote`; new
  `LIST_APPLICATIONS`/`MARK_SENT`/`MARK_REPLIED` messages + response types; `ApplicationDetail`
  gained `final_email_sent`.
- `background/service-worker.ts` — `listApplications`/`markSent`/`markReplied`, same
  `authorizedFetch` pattern as every other function; `updateApplication`'s PATCH body extended.
- `content/HomeView.tsx` — `ExtractionResult`'s old "enter email manually or nothing" gate replaced
  with a 4-way picker (shown only when there's no email and no outreach type chosen yet); saved
  non-email outreach types show as a tag + note, with a `MarkSentInline` action for
  `apply_via_link`/`reach_out_other`. `DraftEmailSection` gained a `mode: "email" | "dm"` prop —
  in `dm` mode the subject field is hidden and a new `DmActionsSection` (copy-to-clipboard +
  "Mark as sent") replaces `SendEmailSection`.
- `content/LoggedInView.tsx` — small tab switcher (`useState<"extract"|"history">`) between
  `HomeView` and the new `HistoryView`.
- `content/HistoryView.tsx` (new) — list of past applications (status/outreach tags, truncation
  warning) with click-to-expand read-only detail and a "Mark as replied" action when `sent`.
- `content/styles.ts` — new `.tab-row`, `.tag`/`.tag-status`/`.tag-outreach`/`.tag-warning`,
  `.list-row` classes.

Web SPA (`frontend/web/src/`):
- `api/types.ts` — `OutreachType`/`ApplicationStatus` unions, `ApplicationResponse` mirroring the
  backend schema field-for-field.
- `api/tracker.ts` (new) — `listApplications`/`getApplication`/`markSent`/`markReplied`, same
  one-line `apiRequest(...)` shape as `api/profiles.ts`.
- `pages/TrackerPage.tsx` (new) — list view modeled on `ProfilesPage.tsx`'s pattern; each row a
  `Link` to the detail page with status/outreach-type/`was_truncated` badges.
- `pages/TrackerDetailPage.tsx` (new) — full read-only detail (every PRD §10 field) + "Mark as
  sent"/"Mark as replied" action buttons, shown conditionally based on outreach type and status.
- `App.tsx` — `/tracker` and `/tracker/:id` routes inside the existing `ProtectedLayout` block.
- `components/ProtectedLayout.tsx` — added "Profiles"/"Tracker" nav links to the topbar (previously
  had none at all — this is the first feature needing more than one top-level page).
- `index.css` — `.badge-warning`/`.badge-success` color variants.

**Verified (backend, via curl against a throwaway signup-created test user, live Groq calls):**
- A post with an email found → `outreach_type` auto-set to `email`.
- A no-email post → `outreach_type`/`parsed_email` both `null` → `PATCH` with
  `outreach_type=linkedin_dm` → `POST /draft` produces a real, short, DM-toned body (no formal
  salutation/signature) → `POST /mark-sent` → `status=sent` → `POST /mark-replied` →
  `status=replied`. Full `extracted → draft_ready → sent → replied` lifecycle confirmed.
- A no-email post → `PATCH` with `outreach_type=apply_via_link` + `outreach_note` (a URL) →
  `POST /mark-sent` succeeds directly from `extracted` (no draft stage, as designed) →
  `status=sent`.
- `POST /mark-sent` on an `email`-type application → 400 with the expected message (must use
  `/send` instead). `POST /mark-replied` on a not-yet-`sent` application → 400.
- `GET /applications` and `GET /applications/{id}` return the right shape (confirmed
  `final_email_sent`/`resume_upload_id` present after the schema fix above) and are scoped to the
  requesting user (404 on a nonexistent/unowned id).
- Extension: `npm run build` succeeds; `npx tsc --noEmit` shows only the pre-existing unrelated
  `shared/storage.ts` error (confirmed pre-existing via `git status` — untouched by this feature).
- Web SPA: `npx tsc --noEmit` clean; `npm run build` succeeds.

**Verified end-to-end by the user in real Chrome** (I can't drive a browser myself, so this needed
their hands-on pass): extension reload-unpacked — walked through all 3 non-email wizard branches,
the DM copy/mark-sent flow, and the History tab; Web SPA's `/tracker` and `/tracker/:id` pages —
all confirmed working.

**How to run/verify it locally:** same as Features 1-6 (`cd backend && uv run uvicorn main:app
--port 8123` — no `--reload`; `cd frontend/extension && npm run build`, load unpacked;
`cd frontend/web && npm run dev`). Extract a post with no email → walk through all 3 non-email
wizard branches on separate posts → confirm the DM draft/copy/mark-sent flow and the
link/other-contact mark-sent flow both work → switch to the History tab and confirm past
applications list with correct tags, expand one, mark a sent one as replied. Then visit `/tracker`
in the Web SPA, confirm the list matches, open a detail page, exercise mark-sent/mark-replied from
there too.

### Feature 8 — Metrics + Admin dashboard — ✅ done, verified end-to-end by the user in real Chrome

**Scope:** PRD §18. Two things were already built and unused before this feature: `core/
dependencies.py`'s `AdminUser` dependency (`require_admin`, 403s non-admins) and `auth_router.py`'s
`POST`/`GET /auth/invite-codes` (admin-gated). This feature is what actually wires up "per-user
metrics" (extension + Web SPA), "admin aggregate dashboard" (Web SPA), and "invite-code generation
UI" — the last one meant building the *UI* only, since the endpoints already existed.

**Design decisions:**
- **`last_login_at` added to `User`**, bumped in `auth_service.authenticate_user` (login) and
  `register_user` (signup) only — deliberately *not* in `get_current_user`/`refresh_tokens`, which
  fire on every authenticated request/silent token refresh. Writing there would add a DB write to
  the hottest path in the app for a signal that's supposed to mean "the user showed up", not "a
  token happened to still be valid". This is the one real gap found — nothing tracked user activity
  before this feature, and PRD's admin table wants a "last active" column.
- **Admin per-user list avoids the N+1/row-multiplication trap** the backlog already flagged for
  nested aggregates (see `BUILD_PLAN.md`): two separate `GROUP BY user_id` subqueries (one over
  `agent_usage_logs` for token sums, one over `applications` for sent-email counts) outer-joined
  once to `users`. Each subquery already collapses to one row per user, so the join can't multiply
  rows — unlike a naive join-then-group across the two to-many relations directly.
- **A real CockroachDB quirk hit while building this:** `SUM()` over an `Integer` column returns a
  `decimal`, and asyncpg's prepared statements reject `COALESCE(decimal, <int literal>)` as a type
  mismatch (`incompatible COALESCE expressions: expected $1::INT8 to be of type decimal, found type
  int`) — this works fine on plain Postgres, CockroachDB is stricter. Fixed by dropping all
  SQL-level `COALESCE(..., 0)` on summed token columns and handling `None` (no rows in range) in
  Python instead, uniformly across `metrics_service.py` and `admin_metrics_service.py`.
- **No charting library added** — confirmed none exists in `frontend/web/package.json`, and PRD
  only asks for numbers, not visualization. The two 14-day trends (signups, token spend) render as
  plain tables via a new `.data-table` CSS class, not charts.
- **Extension gets a third "Usage" tab** (alongside Extract/History), showing the same per-user
  metrics as the Web SPA's `/metrics` page — BUILD_PLAN says metrics should be visible in both
  extension and web. The admin dashboard is Web-SPA-only (nothing about admin work happens on
  LinkedIn).
- **First role-gated route in the Web SPA** — a new `AdminRoute` component (`useAuth()` →
  redirect to `/profiles` unless `role === "admin"`) wraps only `/admin`, mirroring
  `ProtectedLayout`'s own `if (!user) return <Navigate/>` pattern.
- **Important known gap, not a bug:** `agent_usage_logs` is still only retrofitted onto the Email
  Drafter agent (pre-existing `BUILD_PLAN.md` backlog item, not something this feature changed) —
  so every token/latency number here reflects Email Drafter calls only. JD Parser and Resume Parser
  usage will read as zero/absent until that backlog item is done.

**What was built:**

Backend:
- `auth/models.py` — `User.last_login_at` (nullable); `alembic/versions/0008_add_last_login_at.py`
  applied to the live cluster; `auth/schemas.py::UserResponse` gained `last_login_at`;
  `auth_service.py`'s `register_user`/`authenticate_user` both bump it.
- New `backend/metrics/` module (`schemas.py`, `service/metrics_service.py` — per-user aggregation,
  `service/admin_metrics_service.py` — platform aggregation, `routers/metrics_router.py` (`GET
  /metrics/me`), `routers/admin_router.py` (`GET /admin/overview`, `GET /admin/users`, both
  `AdminUser`-gated)). No ORM models in this module — every function is a read-only aggregation
  query over `applications`/`agent_usage_logs`/`user_profiles`/`users`, never selecting
  profile/email-body/post-content columns (PRD's "no access to content" rule).
- `main.py` — registered `metrics_router`/`admin_router`.

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `UserMetrics`/`AgentTokenBreakdown`, `GET_METRICS` message + response.
- `background/service-worker.ts` — `getMetrics()` (`GET /metrics/me`).
- `content/LoggedInView.tsx` — tab row extended to 3 (`extract`/`history`/`usage`).
- `content/UsageView.tsx` (new) — same numbers as the Web SPA's `MetricsPage`, using existing
  `.field`/`.field-grid`/`.muted` primitives.

Web SPA (`frontend/web/src/`):
- `api/types.ts` — `UserMetricsResponse`, `AgentTokenBreakdown`, `DailyCount`, `DailyTokenSpend`,
  `AgentBreakdown`, `AdminOverviewResponse`, `AdminUserRow`, `InviteCodeResponse`.
- `api/metrics.ts` (new) — `getUserMetrics`/`getAdminOverview`/`getAdminUsers`.
- `api/invites.ts` (new) — `createInviteCode`/`listInviteCodes`, thin wrappers over the
  already-existing `/auth/invite-codes` endpoints.
- `pages/MetricsPage.tsx` (new, route `/metrics`) — per-user metrics, any authenticated user.
- `pages/AdminDashboardPage.tsx` (new, route `/admin`) — platform totals, two 14-day trend tables,
  agent breakdown, per-user table, and an invite-code section ("Generate code" + list with
  used/unused status).
- `components/AdminRoute.tsx` (new) — role gate described above.
- `components/ProtectedLayout.tsx` — added "Usage" (always) and "Admin" (role === "admin" only)
  nav links.
- `index.css` — new `.data-table` class (the per-user table and the two trend tables read much
  better as real tables than as `.list-item` cards).

**Verified (backend, via curl against the same throwaway signup-created test user from Feature 7,
plus a temporary role promotion to admin for the admin-only paths — reverted back to jobseeker
immediately after):**
- `last_login_at` populates on `/auth/me` after a fresh login.
- `GET /metrics/me` matches the 3 real applications created during Feature 7's testing exactly:
  `total_applications=3`, `emails_sent=2`, `applications_by_status={replied:1, extracted:1,
  sent:1}`, `most_used_profile="Data Engineer"`, correct `email_drafter` token breakdown for
  today/this month.
- `GET /admin/overview`/`GET /admin/users` as a non-admin → both 403. Promoted the same test user
  to `admin` directly in the DB (a throwaway test account, not a real user's role) → both endpoints
  return sane, correct aggregates across all 10 real users in the dev DB (per-user token sums/
  emails-sent match; 14-day signup/token-spend trends line up with known creation dates); demoted
  back to `jobseeker` immediately after.
- `POST`/`GET /auth/invite-codes` (pre-existing endpoints) re-confirmed still working as an admin.
- Extension: `npm run build` succeeds; `npx tsc --noEmit` shows only the pre-existing unrelated
  `shared/storage.ts` error (confirmed via `git status` — untouched by this feature).
- Web SPA: `npx tsc --noEmit` clean; `npm run build` succeeds.

**Verified end-to-end by the user in real Chrome** (I can't drive a browser myself, so this needed
their hands-on pass): extension's new Usage tab, Web SPA's `/metrics` and `/admin` pages including
the admin-only redirect for a non-admin account, and the invite-code generation flow — all
confirmed working.

**How to run/verify it locally:** same as Features 1-7 (`cd backend && uv run alembic upgrade head
&& uv run uvicorn main:app --port 8123` — no `--reload`; `cd frontend/extension && npm run build`,
load unpacked; `cd frontend/web && npm run dev`). Check the extension's new "Usage" tab; visit
`/metrics` in the Web SPA; visit `/admin` with an admin account (confirm the nav link only shows
for admins, and a non-admin visiting `/admin` directly gets redirected to `/profiles`); generate an
invite code from the admin dashboard and confirm it works for a real signup.

### Feature 9 (v2) — Post Relevance Scorer — ✅ done, backend fully verified via curl; UI built and type-check clean, live browser pass pending user

**Scope:** PRD agent card A4 (`docs/prd.html` line ~544) — the last item on `BUILD_PLAN.md`'s
feature table. IN: `parsed_jd, user_profile`; OUT: `score (0-100), reasoning (string)`; displayed
as a match percentage in the panel. This closes out every feature on the roadmap (1-8 v1, 9 v2) —
the standing backlog items (agent_usage_logs retrofit onto JD/Resume Parser, the N+1 profile-read
fix) remain open and are unaffected by this feature.

**Design decisions:**
- **Scored automatically at extraction time**, alongside the JD Parser call, using the user's
  *default* profile — no extra click. If the user has no profile yet, scoring is skipped entirely
  (`relevance_score`/`relevance_reasoning` stay `null`, no error) — a v2 enrichment, not a blocker.
- **Scoring failures are non-fatal**, unlike JD parsing — a caught exception is logged and
  swallowed (`application_service._try_score_relevance`), the application still saves normally.
- **New agent, same shape as every other agent**: `agents/relevance_scorer/{schemas.py,agent.py}`
  — LangGraph `@entrypoint`/`@task` + `ChatGroq(...).with_structured_output(method="json_schema")`
  + the same 4-model fallback loop (`groq_relevance_scorer_models`) as `resume_parser`/
  `email_drafter`. No DB coupling — reuses `application_service._build_profile_context` verbatim
  (already builds exactly this kind of profile summary for the Email Drafter).
- New `profiles/service/profile_service.get_default_profile_id` (cheap single-column lookup,
  `is_default=True` else earliest-created) feeds the existing, fully eager-loaded
  `get_profile(db, user_id, id)` — no duplicate eager-loading logic.
- An `agent_usage_logs` row is written for every real scoring call (`agent_name=
  "relevance_scorer"`) from day one — not added to the JD-Parser/Resume-Parser retrofit debt.
- Displayed everywhere the other per-application tags already show (extension's live extraction
  result, extension History tab, Web SPA tracker list + detail) since it's just one more field on
  the already-shared `ApplicationResponse`/`ApplicationDetail` types.

**What was built:**

Backend:
- `core/config.py` — `groq_relevance_scorer_models`.
- `applications/models.py` — `relevance_score` (Integer, nullable), `relevance_reasoning` (Text,
  nullable); `alembic/versions/0009_add_relevance_score.py` applied to the live cluster.
- New `agents/relevance_scorer/schemas.py` (`RelevanceScorerContext`, `RelevanceScorerOutput` —
  `score: int` bounded 0-100 via `Field(ge=0, le=100)`) and `agent.py` (`score_post`).
- `profiles/service/profile_service.py` — `get_default_profile_id`.
- `applications/service/application_service.py` — new `_try_score_relevance` helper (best-effort,
  catches all exceptions); `_persist_application` gained `score`/`score_usage` params, sets the two
  new columns and logs the `AgentUsageLog` row in the same commit as the application insert.
- `applications/schemas.py` — `ApplicationResponse` gained both fields.

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `ApplicationDetail` gained `relevance_score`/`relevance_reasoning`.
- `content/HomeView.tsx` — `ExtractionResult` shows a "Match with your profile: NN%" tag +
  reasoning right after the truncation/is_hiring notices, before the job-title field-grid — the
  most prominent spot, seen immediately on extraction.
- `content/HistoryView.tsx` — row gains a match-percentage tag alongside status/outreach tags.
- `content/styles.ts` — new `.tag-match` color variant.

Web SPA (`frontend/web/src/`):
- `api/types.ts` — `ApplicationResponse` gained both fields.
- `pages/TrackerPage.tsx` — row gains a "NN% match" badge.
- `pages/TrackerDetailPage.tsx` — a "Relevance" field showing score + reasoning.

**Verified (backend, via curl against the same throwaway test user from Features 7-8, using real
Groq calls):**
- A post whose skills (SQL/Airflow/Python) matched the test profile's real skills/experience →
  score 60, reasoning correctly noted the skill overlap while flagging a seniority-level mismatch.
- A clearly mismatched post (iOS/Swift/SwiftUI against the same data-engineering profile) → score
  5, reasoning correctly identified zero skill overlap.
- The same matching post against a profile with only a `target_job_title` and no skills/experience
  filled in → score 10, reasoning correctly noted "no evidence of skills" rather than assuming fit
  from the job title alone — confirms the agent is properly grounded, not hallucinating.
- A brand-new signup with zero profiles → extraction still succeeds, both fields `null`, no error,
  no wasted LLM call (confirmed via server logs — no Groq request made for that extraction).
- `agent_usage_logs` gets a real row per scoring call (`agent_name="relevance_scorer"`, confirmed
  in server logs and indirectly via Feature 8's `GET /metrics/me` token breakdown).
- `GET /applications`/`GET /applications/{id}` surface both fields correctly; older Feature 7 test
  applications (extracted before this feature existed) correctly show `relevance_score: null` —
  scores are never computed retroactively.
- Extension: `npm run build` succeeds; `npx tsc --noEmit` shows only the pre-existing unrelated
  `shared/storage.ts` error.
- Web SPA: `npx tsc --noEmit` clean; `npm run build` succeeds.

**Not yet verified:** the actual click-through in a real browser (extension's match-percentage
display on a fresh extraction and in History; Web SPA tracker list/detail) — I can't drive a
browser myself, this needs the user's hands-on pass, same as every prior feature.

**How to run/verify it locally:** same as Features 1-8 (`cd backend && uv run alembic upgrade head
&& uv run uvicorn main:app --port 8123` — no `--reload`; `cd frontend/extension && npm run build`,
load unpacked; `cd frontend/web && npm run dev`). Extract a post as a user with a profile that has
real skills filled in and confirm a sensible match percentage + reasoning appears immediately;
check the History tab and Web SPA tracker show the same tag.

### Backlog cleanup — `agent_usage_logs` retrofit + profile-read N+1 fix — ✅ done, verified via curl

Two standing cross-cutting `BUILD_PLAN.md` backlog items, tackled together once every planned
feature (1-8 v1, 9 v2) was built.

**Part 1 — `agent_usage_logs` retrofit (JD Parser + Resume Parser):**
- `agents/jd_parser/agent.py` — added `include_raw=True` to the existing
  `with_structured_output(JDParserOutput)` call (method stays default `function_calling`,
  unchanged — see the agent's own comment on why `json_schema` isn't safe for this schema), timing
  via `time.monotonic()`, and `raw.usage_metadata` extraction. `_run_llm`/`_jd_parser_graph`/
  `parse_job_post` all now return `tuple[JDParserOutput, AgentUsageInfo]`.
- `agents/resume_parser/agent.py` — same `include_raw=True`/timing/usage pattern, but had to track
  a `best_usage` alongside the existing `best_result` in the `_looks_empty()` retry-to-next-model
  loop, since the eventually-returned result isn't always from the first attempt — whichever
  attempt's result is ultimately returned (first non-empty, or the final best-effort fallback) now
  carries its own matching usage info, not attempt 1's.
- `applications/service/application_service.py` — `create_from_extraction` unpacks `parsed,
  parsed_usage = await parse_job_post(...)`; `_persist_application` gained a `parsed_usage`
  parameter and now logs a second `AgentUsageLog(agent_name="jd_parser", ...)` row alongside the
  existing `relevance_scorer` one, same commit.
- `profiles/service/resume_upload_service.py` — same shape: `upload_and_parse_resume` unpacks
  `parsed, parsed_usage`; `_persist_resume_record` gained a `parsed_usage` parameter and now logs
  `AgentUsageLog(agent_name="resume_parser", ...)` alongside the resume record insert (net-new
  here — no prior usage-logging example existed in this file).
- No schema/migration changes — `AgentUsageLog`/`AgentUsageInfo` already had every field needed.

**Part 2 — profile-read N+1 fix:**
- **Scope was surgical, not a full rewrite**: only the trailing "re-fetch fully-hydrated and
  return" step that `get_profile`/`create_profile`/`update_profile`/`clone_profile` (and, found
  along the way, `set_default_profile` — same pattern, not explicitly named in the backlog text but
  identical cost, fixed for consistency) each already did as their last step, changed. All actual
  mutation logic (`_apply_children`'s wholesale child-list reassignment, `_demote_other_defaults`)
  stayed exactly as-is, still ORM-based — it genuinely needs mutable, cascade-aware objects.
- New `profile_service._fetch_profile_response(db, user_id, profile_id) -> ProfileResponse | None`
  — one hand-written SQL query via `sqlalchemy.text()` (**first raw-SQL query in this codebase** —
  confirmed no prior precedent via search), with a correlated `json_agg`/`row_to_json` subquery per
  child collection (skills, experiences — which nests a further subquery for
  `experience_projects` — projects, education, certifications, achievements, languages), executed
  via `text(sql).columns(personal_info=JSON, skills=JSON, ...)` so SQLAlchemy's `JSON` type applies
  its own `json.loads()` result-processing. Added a defensive `_maybe_json_loads()` helper on top
  (checks `isinstance(value, str)` before parsing) since there's no existing precedent in this
  codebase confirming whether the asyncpg driver or SQLAlchemy's type hint ends up doing the actual
  deserialization — belt-and-suspenders for a first-of-its-kind pattern.
- All 5 functions' return type changed from `UserProfile` (ORM) to `ProfileResponse` (Pydantic).
  `profiles/routers/profile_router.py`'s 5 endpoint handlers simplified from
  `ProfileResponse.model_validate(profile)` to just `return profile`/`return await ...` directly.
- **Real ripple found and fixed**: `application_service.py` had two call sites
  (`_build_profile_context`, and an inline block in `send_application_email`) doing
  `profile.personal_info.get("first_name")`-style dict access — this worked when `get_profile`
  returned an ORM `UserProfile` (whose `personal_info` is a raw JSONB dict) but breaks once it
  returns `ProfileResponse` (whose `personal_info` is a `PersonalInfo` **Pydantic model**, no
  `.get()` method). Fixed both to plain attribute access (`personal_info.first_name`), dropping the
  now-unneeded `or {}` fallback since `PersonalInfo` is always present. Every other attribute
  access in `_build_profile_context` (`.skills[i].category`, `.experiences[i].responsibilities`,
  etc.) needed no change — `ProfileResponse`'s nested schemas mirror the ORM column names exactly.

**Verified (via curl against the same throwaway test user from Features 7-9):**
- Part 1: extracted a post + uploaded `docs/Pranay_Gulhane_Resume.pdf`, then `GET /metrics/me`
  (Feature 8's endpoint) showed real token counts for all 4 agents — `relevance_scorer`,
  `email_drafter`, `jd_parser`, `resume_parser` — confirming the retrofit end to end. JD parsing
  output (job_title/company/email/skills) unaffected — still extracting correctly.
- Part 2: `PUT /profiles/{id}` with a payload covering all 7 child tables plus a nested
  `experience_projects` entry, then `GET /profiles/{id}` → confirmed every field present and
  correctly typed (UUIDs, enum `proficiency: "native"` as a plain string, nested
  `experiences[0].projects`), completing in ~1.7s total (vs. the documented ~15-25s baseline for
  the old 7-round-trip read). Confirmed `GET` on a nonexistent profile still 404s
  (`ProfileNotFoundError` → `HTTPException`, contract unchanged). Confirmed `create_profile`,
  `clone_profile` (including its nested-experience-projects copy), and `set_default_profile` all
  still work and return the same shape. Re-ran the draft flow (`POST /applications/{id}/draft`)
  against the updated profile — the generated email correctly referenced the candidate's real name,
  headline, and specific experience details, confirming `_build_profile_context`'s
  `personal_info`-attribute-access fix works correctly end to end (not just that it doesn't throw).

**How to run/verify it locally:** same as every prior feature (`cd backend && uv run uvicorn
main:app --port 8123` — no `--reload`). No new migration to run. Extract a post + upload a resume,
then `GET /metrics/me` to see all 4 agents' token usage. `PUT`/`GET` a profile with nested
experience-projects to confirm the raw-SQL read still returns identical shape to before.

### Feature 10 — Extension→SPA link, Archiving, Invite Code lifecycle, Admin user management — ✅ done, backend fully verified via curl; UI built and type-check clean, live browser pass pending user

**Scope:** four small user-requested additions bundled together since they share the tracker/admin
surfaces from Features 7-8: (1) a link from the extension panel to the Web SPA, (2) an archive
flag for tracker records, (3) invite-code expiry/manual-revoke/used-by tracking, (4) admin user
access revocation + a default 30-day access window + admin notes.

**Design decisions:**
- **SPA link**: new `WEB_APP_URL` config constant + `OPEN_WEB_APP` background message
  (content scripts can't call `chrome.tabs.create` themselves, same reason `GMAIL_CONNECT` already
  routes through the background worker) + a persistent "Open web app ↗" link in `LoggedInView`'s
  `.user-row` area. No SSO/token bridging — opening the SPA shows its own login page if not
  already signed in there, same as the two apps' always-separate sessions since Features 1/2.
- **Archive is a plain boolean** (`is_archived`) on `Application`, orthogonal to `status` — never a
  new status value, no structured "reason" field. `GET /applications` still returns everything
  unfiltered; both frontends default to hiding archived rows behind a "Show archived" toggle,
  filtered client-side. Feature 8's metrics keep counting all applications regardless of archive
  state (archiving is a tracker-view concern, not a "doesn't count" concern).
- **Invite codes** gained `expires_at` (settable at generation) and `revoked_at` (settable via a
  new manual-revoke action). A code is redeemable only if `not is_used and revoked_at is None and
  (expires_at is None or expires_at > now)`. `InviteCodeResponse` gained `used_by_email` — the
  `used_by` FK already existed since Feature 1 but was never surfaced; `auth_service.
  list_invite_codes_with_users` replaces the ad-hoc query that used to live directly in the router.
- **User access** gained `access_expires_at` (defaulted to `now + 30 days` at signup, `NULL` =
  unlimited) and `admin_notes`. Existing users got `NULL` on migration — deliberately grandfathered,
  not retroactively locked out. Enforcement lives in **three** places, not just the one originally
  scoped: `core/dependencies.get_current_user` (every request), `auth_service.authenticate_user`
  (login, distinct 403 message from the generic "incorrect email or password"), **and**
  `auth_service.refresh_tokens` (added during implementation — without it, a user whose access
  expired mid-session could keep silently renewing their access token every ~15 min until it
  naturally lapsed on its own, which would have been a real gap). "Revoke access" reuses the
  *existing* `is_active` column — there was just never an endpoint to flip it before now. Extending
  access + editing notes is one combined action endpoint (`POST /admin/users/{id}/access`, both
  fields always required, never a partial patch) — avoids the null-vs-omitted ambiguity a generic
  PATCH would have for "clear the expiry to make it unlimited."
- **Revised after initial ship**: a revoked user's login originally still returned the pre-existing
  vague 401 "Incorrect email or password" (the `is_active` check in `authenticate_user` predates
  this feature and was left alone on the first pass). The user asked for this to be explicit
  instead — added a new `AccountDisabledError` (distinct from `InvalidCredentialsError`), mapped to
  a 403 "Your access has been revoked — contact the admin", parallel to the existing
  `AccessExpiredError` → "Your access period has expired…" handling. The wrong-email/wrong-password
  case still stays deliberately vague (`InvalidCredentialsError` → 401) — only the two
  access-control cases (revoked, expired) now tell the user exactly why, since those aren't a
  security-sensitive distinction the way credential-guessing is.

**What was built:**

Backend — 3 new migrations (`0010_add_application_archive`, `0011_add_invite_code_lifecycle`,
`0012_add_user_access_management`):
- `applications/` — `Application.is_archived`; `ApplicationResponse` gained the field;
  `archive_application`/`unarchive_application` (same `with_serialization_retry`-wrapped
  single-flag-flip shape as `mark_sent_manually`/`mark_replied`); `POST /applications/{id}/archive`
  and `/unarchive`.
- `auth/` — `InviteCode.expires_at`/`revoked_at`; `User.access_expires_at`/`admin_notes`;
  `InviteCodeResponse`/`CreateInviteCodeRequest`; `register_user`'s invite-validity check extended;
  new `AccessExpiredError`/`InviteCodeNotFoundError`/`InviteCodeAlreadyUsedError`; new
  `revoke_invite_code`, `list_invite_codes_with_users`, `revoke_user_access`/
  `restore_user_access`/`update_user_access`; `POST /auth/invite-codes/{id}/revoke`; login route
  catches `AccessExpiredError` → distinct 403.
- `core/dependencies.py` — `get_current_user` gained the `access_expires_at` check.
- `metrics/` — `AdminUserRow` gained `is_active`/`access_expires_at`/`admin_notes`; new
  `AdminUserAccessUpdateRequest`; `list_admin_users`'s query gained the 3 new `User` columns (same
  query, no new round trips); new `POST /admin/users/{id}/revoke-access`, `/restore-access`,
  `/access`.

Extension: `shared/config.ts` `WEB_APP_URL`; new `OPEN_WEB_APP`/`MARK_ARCHIVED`/`MARK_UNARCHIVED`
messages; `LoggedInView.tsx` "Open web app ↗" link (new `.link-button` style); `HistoryView.tsx`
"Show archived" toggle + Archive/Unarchive action, dimmed archived rows.

Web SPA: `api/tracker.ts` archive/unarchive; `api/invites.ts` expiry param + revoke; new
`api/adminUsers.ts` (revoke/restore/update-access); `TrackerPage.tsx`/`TrackerDetailPage.tsx`
archive toggle/badge/button; `AdminDashboardPage.tsx` — invite table gained Expires/Used
by/Revoke, generate-code control gained a date picker; per-user table gained Status/Access
expires/Notes columns, Revoke/Restore, and an inline "Edit access" row (date input + notes
textarea) using the same click-to-expand pattern as `HistoryView`.

**Verified (backend, via curl against the same throwaway test user from Features 7-9, plus a
temporary role promotion to admin for the admin-only paths — reverted immediately after):**
- Archive/unarchive an application → `GET /applications` reflects the flag correctly both ways.
- Generated an invite code with a past `expires_at` → signup with it rejected (400). Generated a
  fresh code, revoked it → signup with it then also rejected (400).
- `used_by_email` correctly populated after a real signup with a valid code.
- A fresh signup's `access_expires_at` landed exactly 30 days after `created_at`.
- Admin `revoke-access` → that user's login now fails (401, the pre-existing vague message,
  confirmed unchanged); `restore-access` → login works again.
- Admin `POST .../access` with a past date → login now fails with the **distinct** 403
  access-expired message; confirmed this is enforced in real time even against an
  **already-issued, still-cryptographically-valid** access token (not just re-checked at login) —
  hit a protected endpoint with a pre-existing token after backdating the expiry and got the same
  403, proving `get_current_user` re-checks the DB on every request.
- Revoked-user login message fix: confirmed a login attempt against the same test user now returns
  `"Your access period has expired — contact the admin to extend it"` while backdated, and after
  `revoke-access`, `"Your access has been revoked — contact the admin"` — both distinct 403s,
  replacing the old vague 401 "Incorrect email or password" for these two cases. Wrong-password
  login on the same account still correctly returns the generic 401. Restored the test user
  (`restore-access` + reset `access_expires_at` to a future date) afterward.
- `GET /admin/users` surfaces all 3 new fields correctly.
- Extension: `npm run build` succeeds; `npx tsc --noEmit` shows only the pre-existing unrelated
  `shared/storage.ts` error.
- Web SPA: `npx tsc --noEmit` clean; `npm run build` succeeds.

**Not yet verified:** the actual click-through in a real browser (extension's "Open web app" link
and archive toggle; Web SPA's tracker archive controls and the full admin-dashboard invite/user-
access UI) — I can't drive a browser myself, this needs the user's hands-on pass, same as every
prior feature.

**How to run/verify it locally:** same as every prior feature (`cd backend && uv run alembic
upgrade head && uv run uvicorn main:app --port 8123` — no `--reload`; `cd frontend/extension && npm
run build`, load unpacked; `cd frontend/web && npm run dev`). Click "Open web app" in the panel;
archive/unarchive from the extension History tab and the Web SPA tracker; from `/admin`, generate
an invite code with an expiry, revoke an unused one, and exercise a test user's revoke/restore/
edit-access flow end to end.

### Feature 11 — Duplicate-contact warning at extraction time — ✅ done, backend fully verified via curl; extension built and type-check clean, live browser pass pending user

**Scope:** warn the user if they've already contacted this poster or recipient from a different
application — surfaced immediately after a post is parsed, not at send time, so the user can decide
not to bother drafting at all rather than finding out only at the last second before sending.

**Revised after initial ship:** the first pass of this feature checked only at the moment "Send"
was clicked, and only matched on recipient email. The user asked for it to move earlier — right
after parsing produces either a recipient email or the poster's LinkedIn profile link — "so the
user saves later effort and can decide whether to move forward or not." Two changes followed from
that: the trigger point moved from `SendEmailSection` to `ExtractionResult` (shown the instant
extraction succeeds), and the match broadened to include `poster_profile_url` — which is *always*
captured at extraction time, unlike `parsed_email`, which may never show up for a given post. The
old check-before-send Yes/No gate in `SendEmailSection` was removed entirely (not kept alongside)
since the warning is now shown at the earlier, more useful point and re-litigating it at send time
would just be a redundant second prompt for the same information.

**Revised again:** "View that application" originally opened the Web SPA tracker detail page in a
new browser tab. The user asked for it to show in-place instead — a popup within the extension
panel itself — so the in-progress extraction result (post details, outreach picker, any draft
in flight) doesn't disappear behind a tab switch. Since `CHECK_DUPLICATE_RECIPIENT` already returns
the full `existing_application` object, no new fetch was needed — the button just toggles a
`showDuplicateDetail` boolean and renders a `.modal-overlay`/`.modal-card` (new CSS in
`content/styles.ts`) as an absolutely-positioned overlay confined to the floating panel's own
bounds (`.panel` is `position: fixed`, which is what makes it the containing block for the
overlay's `position: absolute; inset: 0`, rather than covering the whole browser viewport).
Clicking the backdrop or the × closes it, revealing the still-mounted `ExtractionResult` underneath
exactly as it was.

**Revised a third time:** every extraction still auto-saves a new `applications` row immediately
(G5's "auto-save every application" commitment), even though the duplicate check runs right after.
The user pointed out that if they decide not to pursue a flagged duplicate, that just-created row
is pure clutter — a record for this contact already exists. Since the row's identity signals
(`poster_profile_url`/`parsed_email`) are only known *after* extraction+JD-parsing has already run
and persisted, the row can't be skipped up front — so instead a narrow "Don't save this" discard
action was added: a new `DELETE /applications/{id}` that only succeeds while the application is
still `status=extracted` (nothing drafted or sent yet), reusing the same `_get_owned` ownership
check every other mutator uses. This is deliberately not a general delete — it only exists in the
duplicate-warning banner, and the backend guard (409 once a draft exists) keeps it from ever
touching a record that represents real work, preserving G5 for the ordinary flow.

**Design decisions:**
- **Still a purely advisory `GET`, not a change to `/send`.** `POST /applications/{id}/send` keeps
  sending unconditionally — this remains a UX nudge, not a data-integrity rule. `GET
  /applications/{id}/duplicate-check` reports whether a prior *successfully sent* application
  (`status` = `sent`/`replied`) exists for the same contact, plus that application's full detail.
- **Match on `poster_profile_url` OR `parsed_email` (case-insensitive), scoped to the user,
  excluding the application itself.** `poster_profile_url` is the durable identity signal (same
  pattern as Feature 7's `linkedin_dm` outreach type, which uses the profile URL as the contact
  target precisely because there's often no email) — matching on it catches "I already reached out
  to this exact person" even if this post has no email or a different one. Matching on
  `parsed_email` separately catches "I already used this address" even from a different poster
  (e.g. a shared HR inbox). `DuplicateCheckResponse.matched_via` (`"email"` | `"poster_profile_url"`)
  tells the UI which one fired, preferring to report `poster_profile_url` when both match since
  "you already contacted this person" is the more useful framing.
- **Trigger moved to `ExtractionResult`'s mount** (a `useEffect` keyed on `application.id`), same
  lifecycle timing as the relevance-score display already at the top of that component — not a
  click handler anymore.
- **Display is a non-blocking banner**, not a Yes/No prompt — matching the existing
  `is_hiring`/`was_truncated`/relevance-score notices already at the top of `ExtractionResult`.
  Shows who/when it matched plus a "View that application" button that opens the record in an
  in-panel modal (see "Revised again" above) — the user reads it and decides for themselves
  whether to continue drafting or select another post.

**What was built:**

Backend (`applications/`):
- `schemas.py` — `DuplicateCheckResponse(is_duplicate, matched_via, existing_application)`.
- `service/application_service.py` — `check_duplicate_contact(db, user_id, application_id) ->
  tuple[Application, str] | None`: loads the application via the existing `_get_owned`, then
  queries the most recent other application for this user matching `poster_profile_url ==` OR
  (`parsed_email` set AND `func.lower(...)` equal), `status IN (sent, replied)`, ordered by
  `sent_at DESC`; derives `matched_via` in Python from which column actually matched.
- `routers/application_router.py` — same route (`GET /applications/{id}/duplicate-check`), calling
  the renamed service function and threading `matched_via` through.
- `service/application_service.py` — new `NotDiscardableError`; new `delete_application(db,
  user_id, application_id)`: loads via `_get_owned`, raises `NotDiscardableError` unless
  `status == ApplicationStatusEnum.EXTRACTED`, otherwise hard-deletes the row (confirmed safe —
  nothing else in the schema FKs to `applications.id`).
- `routers/application_router.py` — new `DELETE /applications/{id}` → 204; 404 via
  `ApplicationNotFoundError`; 409 via `NotDiscardableError` ("already has a draft or was sent").

Extension (`frontend/extension/src/`):
- `shared/types.ts` — `CheckDuplicateResponse` gained `matched_via`.
- `background/service-worker.ts` — `checkDuplicateRecipient()` passes `matched_via` through
  unchanged otherwise; `openWebApp` still appends an optional `path` (from Feature 10, now unused
  by this feature but kept — the extension panel's "Open web app" link still relies on it).
- `content/HomeView.tsx`'s `ExtractionResult` — new `useEffect` calls `CHECK_DUPLICATE_RECIPIENT`
  as soon as the extraction result renders; renders the banner ("You already contacted **{poster}**
  on {date}[, at {company}]" or "…already contacted **{email}**…", phrased per `matched_via`) right
  alongside the existing is_hiring/was_truncated notices, with a "View that application" button
  that opens `duplicate.existing` (already fully fetched, no extra round trip) in an in-panel modal.
- `content/HomeView.tsx`'s `SendEmailSection` — reverted to a plain, unconditional Send button; the
  check-before-send logic and Yes/No block from the original pass were removed.
- `content/styles.ts` — new `.modal-overlay`/`.modal-card`/`.modal-card-header` classes.
- `shared/types.ts` — new `DELETE_APPLICATION` message + `DeleteApplicationResponse`.
- `background/service-worker.ts` — new `deleteApplication()`, `DELETE /applications/{id}`,
  expecting 204 (not 200 — `fetchJson`'s `res.json().catch(() => undefined)` already handles the
  empty body gracefully).
- `content/HomeView.tsx`'s `ExtractionResult` — duplicate banner gained a "Don't save this" button
  next to "View that application"; calls `DELETE_APPLICATION` for the *current* (just-extracted)
  application, and on success calls `onSelectAnother()` to return to post-selection mode. A failed
  delete (e.g. the 409 if a draft snuck in first) surfaces as an inline `error-text` without
  touching any other state.

**Verified (backend, via curl against the same throwaway test user from Features 7-10):**
- Extracted an application with the *same* `poster_profile_url` as a prior `sent` application but a
  *different* email → `is_duplicate: true`, `matched_via: "poster_profile_url"`, confirming the
  broadened match works independently of email.
- Extracted an application with a *different* poster but the *same* email (different casing) as a
  prior `sent` application → `is_duplicate: true`, `matched_via: "email"`, confirming the original
  email-match path still works standalone.
- Self-exclusion still holds (`GET .../duplicate-check` on the sent application itself → `false`).
- Extracted a fresh throwaway application (`status=extracted`) and `DELETE`d it → 204; re-`GET` it
  → 404, confirming the row is actually gone.
- Attempted `DELETE` on an already-`sent` test application → 409 "already has a draft or was sent —
  it can't be discarded"; attempted `DELETE` on a nonexistent id → 404.
- Extension: `npm run build` succeeds; `npx tsc --noEmit` shows only the pre-existing unrelated
  `shared/storage.ts` error.

**Not yet verified:** the actual click-through in a real browser (extract a post from an
already-contacted poster/email and confirm the banner appears immediately, before touching
Draft/Send at all; confirm "View that application" opens the in-panel modal with the right
record's details, that the backdrop/× both close it, and that the underlying extraction result is
unchanged after closing; click "Don't save this" and confirm it returns to post-selection mode
with the row actually deleted from the tracker; confirm Send no longer shows any duplicate prompt)
— I can't drive a browser myself, this needs the user's hands-on pass, same as every prior feature.

**How to run/verify it locally:** same as every prior feature (`cd backend && uv run uvicorn
main:app --port 8123` — no `--reload`, no new migration; `cd frontend/extension && npm run build`,
load unpacked). Extract a post from a poster or recipient you've already emailed and confirm the
warning banner appears on the extraction result immediately, before drafting; click "Don't save
this" and confirm the application disappears from the tracker; separately, click "View that
application" and confirm the modal shows the right record without navigating away, and that closing
it returns to the same extraction result state.

## Backend module log

Historical record from before the feature-slice restructure. "Phase 1" = the auth backend (now the backend half
of Feature 1); "Phase 2" = the profiles backend (now the backend half of Feature 2). Kept as originally written.

### Phase 1 — Foundation + Auth — ✅ done, verified against live CockroachDB Cloud

**What was built** (all under `backend/`):
- `core/config.py` — `pydantic-settings` `Settings` (env: `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`,
  `ACCESS_TOKEN_EXPIRE_MINUTES`=15, `REFRESH_TOKEN_EXPIRE_DAYS`=7, `CORS_ORIGINS`, `ENVIRONMENT`, `APP_NAME`).
- `core/database.py` — async SQLAlchemy engine (`postgresql+asyncpg`), `AsyncSessionLocal`, declarative `Base`,
  `get_db()` FastAPI dependency.
- `core/security.py` — bcrypt password hashing, PyJWT access/refresh token create+decode (`TokenType` enum
  distinguishes access vs refresh so a refresh token can't be used as an access token).
- `core/dependencies.py` — `get_current_user` (Bearer token → DB user), `CurrentUser` / `AdminUser` `Annotated`
  aliases, `require_admin` (403 if `role != admin`). Uses `HTTPBearer` (not `OAuth2PasswordBearer` — swapped
  after initial Phase 1 build): `/auth/login` takes a JSON body, not OAuth2's form-encoded grant, so Swagger's
  "Authorize" dialog for `OAuth2PasswordBearer` would show a login form that could never actually succeed against
  our endpoint. `HTTPBearer` gives Swagger a plain paste-your-token box instead — verified working via
  `/docs` → login → Authorize → `/auth/me`.
- `auth/models.py` — `User` (id uuid, email unique, hashed_password, `role` enum stored as varchar via
  `native_enum=False` — deliberate: avoids CockroachDB's `ALTER TYPE ADD VALUE` quirks with native PG enums,
  is_active, created_at) and `InviteCode` (id, code unique, created_by/used_by FK → users, is_used, used_at,
  created_at).
- `auth/schemas.py` — Pydantic v2: `SignupRequest`, `LoginRequest`, `RefreshRequest`, `TokenResponse`,
  `UserResponse`, `InviteCodeResponse`.
- `auth/service/auth_service.py` — `register_user` (validates invite code with `SELECT ... FOR UPDATE` inside the
  same transaction as user creation + marking the code used, so signup is atomic), `authenticate_user`,
  `refresh_tokens`, `create_invite_code`. Typed exceptions (`EmailAlreadyRegisteredError`,
  `InvalidInviteCodeError`, `InvalidCredentialsError`, `UserNotFoundError`) that the router maps to HTTP statuses.
- `auth/routers/auth_router.py` — `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`,
  `POST /auth/invite-codes` (admin), `GET /auth/invite-codes` (admin).
- `main.py` — FastAPI app, CORS middleware, router registration, `GET /health`.
- `alembic/` — async-engine-aware `env.py` (imports `auth.models` so `Base.metadata` is populated; uses
  `run_sync` since the app engine is async), `alembic.ini`, `versions/0001_create_users_and_invite_codes.py`.
  **The initial migration was hand-written, not autogenerated** — there was no live DB to autogenerate against.
  Double-check it matches `auth/models.py` if models change before this migration has been applied anywhere.
- `pyproject.toml` — deps: fastapi, uvicorn[standard], sqlalchemy[asyncio]+asyncpg, alembic, pydantic(-settings),
  pyjwt, bcrypt, python-multipart, email-validator. Dev group: httpx, pytest, pytest-asyncio.
- `.env.example` — template; real `.env` is gitignored (via root `.gitignore`, already covered).

**Decisions/gotchas for future sessions:**
- **Python pinning**: system only has Python 3.14 (via `py` launcher), which is too new/risky for library wheel
  availability. Backend pins **Python 3.12** via `uv python install 3.12` + `uv python pin 3.12` +
  `uv venv --python 3.12` — independent of system Python. `backend/.python-version` = `3.12`. Always run backend
  commands via `uv run ...` from `backend/` so this pin is respected.
- `uv` is not on system PATH by default in this environment; it was installed via
  `py -m pip install --user uv` and lives at `%APPDATA%\Roaming\Python\Python314\Scripts\uv.exe`. Add that dir to
  PATH in a session before running `uv` commands, e.g. (bash) `export PATH="$PATH:/c/Users/<user>/AppData/Roaming/Python/Python314/Scripts"`.
  `uv sync` from `backend/` installs everything into `backend/.venv`.
  All 40 dependencies installed cleanly on Python 3.12 — no wheel issues.
- **DB URL dialect/SSL**: use `postgresql+asyncpg://` prefix (not bare `postgresql://`). CockroachDB Cloud's
  "Connect" panel gives you `sslmode=verify-full`, but **asyncpg's driver doesn't accept a `sslmode` kwarg at
  all** (`TypeError: connect() got an unexpected keyword argument 'sslmode'`) — use `?ssl=require` in the query
  string instead (still encrypted, just no CA pinning; fine for a dev cluster).
- **CockroachDB version-string bug (real, fixed)**: SQLAlchemy's Postgres dialect runs `SELECT version()` on
  first connect and regex-parses it expecting `"PostgreSQL X.Y..."`. CockroachDB returns
  `"CockroachDB CCL v25.4.10 (...)"`, which doesn't match, and raises `AssertionError: Could not determine
  version from string`. `sqlalchemy-cockroachdb` fixes this but only wraps the sync `psycopg2` driver — there's
  no maintained CockroachDB-aware **asyncpg** dialect. Fixed in `core/database.py` by monkeypatching
  `PGDialect_asyncpg._get_server_version_info` to always return `(13, 0)` (CockroachDB is wire/SQL-compatible
  with Postgres 13). If a future SQLAlchemy/asyncpg upgrade changes this internal method's signature, revisit
  this patch.
- **Enum storage bug (real, fixed)**: `auth/models.py`'s `role` column used `Enum(RoleEnum, native_enum=False)`
  without `values_callable`, so SQLAlchemy persisted the Python enum **name** (`"ADMIN"`, `"JOBSEEKER"`) instead
  of its **value** (`"admin"`, `"jobseeker"`) — inconsistent with the migration's `server_default="jobseeker"`
  and with the value every other consumer (JSON API, PRD's `role: enum` values) uses. Confirmed live via
  `SELECT role FROM users` returning `'ADMIN'`. Fixed by adding
  `values_callable=lambda enum_cls: [m.value for m in enum_cls]` to the column definition. **Any future enum
  column (e.g. `applications.status`, `applications.outreach_type` in later phases) needs this same
  `values_callable` from the start** — don't repeat this bug.
- **Bootstrapping the first admin**: there's no signup path to create the very first admin (the invite-code
  endpoint that generates codes is itself admin-only, and every fresh user is created as `jobseeker`). Bootstrap
  by inserting an `InviteCode` row and promoting the first signed-up user directly via the ORM/SQL — see the
  one-liners used during verification below. This is a one-time manual step per environment, not a gap to fix.

**Verified live** (CockroachDB Cloud cluster `zebra-serpent-28425`, `defaultdb`):
- `alembic upgrade head` applied migration `0001` cleanly (after the SSL and version-string fixes above).
- Full HTTP flow via `uvicorn` + `curl`: signup with a valid invite code → tokens issued; signup with an
  already-used invite code → 400; signup with a duplicate email → 409; login with wrong password → 401; login
  with correct password → tokens; `/auth/me` with a valid access token → 200 with correct user data; `/auth/me`
  with no token → 401; `/auth/me` using a **refresh token** as the bearer token → 401 (access/refresh type
  isolation works); `/auth/refresh` with a valid refresh token → new token pair; jobseeker calling
  `POST /auth/invite-codes` → 403; after promoting a user to `admin` directly via SQL, that same user calling
  `POST /auth/invite-codes` and `GET /auth/invite-codes` → 201/200 with correct data.
- Test data (2 users: one admin `pranay@example.com`, one jobseeker `jobseeker2@example.com`; 2 invite codes)
  was left in the live dev cluster — harmless, but a future session doing a clean-slate test should know it's
  not an empty table.

**How to run it locally:**
```bash
cd backend
export PATH="$PATH:/c/Users/<user>/AppData/Roaming/Python/Python314/Scripts"  # if uv isn't on PATH
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8123
# bootstrap the first admin (one-time, per environment):
uv run python -c "
import asyncio, secrets
from core.database import AsyncSessionLocal
from auth.models import InviteCode
async def main():
    async with AsyncSessionLocal() as db:
        code = secrets.token_urlsafe(9)
        db.add(InviteCode(code=code)); await db.commit(); print(code)
asyncio.run(main())
"
# then POST /auth/signup with that code, then promote that user's role to 'admin' via SQL/ORM.
```

### Phase 2 — User Profiles — ✅ done, verified against live CockroachDB Cloud

**What was built** (all under `backend/profiles/`):
- `models.py` — `UserProfile` (id, user_id FK, target_job_title, is_default, professional_summary, `personal_info`
  as a single JSONB blob — matches the PRD's DB schema diagram exactly rather than 17 separate columns, plus
  created_at/updated_at) and 8 child tables: `ProfileSkill`, `ProfileExperience` (+ `ExperienceProject` nested one
  level deeper), `ProfileProject` (personal projects), `ProfileEducation`, `ProfileCertification`,
  `ProfileAchievement`, `ProfileLanguage` (`proficiency` enum — used `values_callable` from the start this time,
  see Phase 1's enum bug). A **partial unique index** (`ix_user_profiles_one_default_per_user`, `WHERE is_default
  = true`) enforces "at most one default profile per user" at the DB level, not just in application code.
- `schemas.py` — `PersonalInfo` (all-optional, since Phase 3's resume parser will hand back partial data),
  one Pydantic class per child table (doubles as both write-item and read-item shape, `id` optional so it's
  ignored on write), `ProfileWriteRequest` (used for both POST and PUT — see design note below),
  `ProfileResponse` (full nested detail), `ProfileSummaryResponse` (flat, no nested collections — see perf note).
- `service/profile_service.py` — `create_profile`, `list_profiles`, `get_profile`, `update_profile`,
  `delete_profile`, `set_default_profile`, `clone_profile`. Every getter filters by `user_id` — a profile that
  exists but belongs to someone else returns 404 (`ProfileNotFoundError`), not 403, so ownership isn't leaked.
- `routers/profile_router.py` — `POST/GET /profiles`, `GET/PUT/DELETE /profiles/{id}`,
  `POST /profiles/{id}/set-default`, `POST /profiles/{id}/clone`. All behind `CurrentUser`.
- `alembic/versions/0002_create_profile_tables.py` — hand-written (same reason as 0001: no autogenerate target
  reachable ahead of time), includes the partial unique index.

**Design decisions for future sessions:**
- **Aggregate resource, not per-item CRUD.** A profile + all its nested collections (skills, experience,
  education, etc.) is treated as ONE resource. `PUT /profiles/{id}` replaces every nested collection wholesale
  (delete-orphan cascade + reassign the list) inside one transaction, rather than exposing 8 separate nested
  CRUD sub-resources (~30+ endpoints). This matches how the PRD describes both the resume parser ("partial
  UserProfile object") and the profile-edit UI (one form, one save) — there's no use case in the PRD for editing
  a single skill in isolation. **If a future UI needs granular per-item edits without resending the whole
  profile, that's a deliberate scope change from this design, not a bug.**
- **`experience_projects.experience_id` → `profile_experiences.id`, not `profile_id`.** The PRD's prose says
  "Additional sub-tables ... all reference profile_id as a foreign key" but that's loose — a project nested
  inside one specific job (not the profile as a whole) has to key off that experience row, or there'd be no way
  to know which job a project belongs to. Deliberate deviation from the literal prose, not an oversight.
- **One default profile per user is invariant**, enforced at two layers: a partial unique DB index, and service
  logic that (a) forces the first profile a user creates to be default regardless of the payload, (b) refuses to
  let `PUT` silently demote the current default (only `set_default_profile`, i.e. promoting a *different*
  profile, can change which one is default), and (c) auto-promotes the most-recently-created remaining profile
  when the current default is deleted. There should never be a moment where a user has ≥1 profile but zero
  defaults. Verified live (see below) — including the "PUT with `is_default:false` on the current default is
  ignored, stays true" case specifically, since that's the easiest invariant to accidentally break later.
- **List vs. detail split is a real perf fix, not just REST taste.** Originally `GET /profiles` eager-loaded all
  7 child relationships per profile via `selectinload` — correct for avoiding cartesian-product blowup (which
  `joinedload` would cause with multiple to-many relationships in one query), but each relationship is a
  separate round trip. Against this project's CockroachDB Cloud cluster, each round trip costs ~1–3.5s
  (observed, not a bug — likely geographic distance to `aws-us-east-1` plus serverless characteristics), so
  listing profiles with full nested detail eagerly loaded took 20-30s and looked like a hang. Fixed by making
  `GET /profiles` return `ProfileSummaryResponse` (no nested collections, 1 query total); `GET /profiles/{id}`
  still returns full detail and still costs ~7 round trips (~15-25s against this specific cluster). **Any new
  endpoint that eager-loads several to-many relationships on a remote DB should expect this same per-relationship
  round-trip cost** — it's inherent to `selectinload`, not something to "just fix" without accepting either
  cartesian-product risk (`joinedload`) or fewer relationship types loaded at once.

**Verified live** (same CockroachDB Cloud cluster as Phase 1):
- Full nested create (personal_info + skills + experience with a nested experience-project + personal project +
  education + certification + achievement + language) → 201 with all nested rows correctly persisted and
  returned with server-generated ids.
- First profile a user creates → `is_default: true` automatically, even though the request body said `false`
  implicitly (field omitted defaults to `false` in the schema).
- Second profile created with `is_default: false` → correctly stays non-default; first profile remains default.
- `GET /profiles` (summary, no nested data) → fast; `GET /profiles/{id}` → full nested detail.
- `POST /profiles/{id}/set-default` → atomically flips default from one profile to another (confirmed via
  before/after list).
- `PUT /profiles/{id}` on a non-default profile → target_job_title/summary/skills/languages all replaced
  wholesale (old skill rows gone, new ones present with new ids).
- `PUT /profiles/{id}` on the *current default* profile with `is_default: false` in the payload → demotion is
  ignored, profile stays default (invariant-protection check).
- `POST /profiles/{id}/clone` → new profile with a new `target_job_title`, `is_default: false` regardless of
  source, and all nested collections (skills, etc.) deep-copied with new ids.
- Cross-user isolation: a second user (`jobseeker2@example.com`, from Phase 1) attempting `GET` or `DELETE` on
  the first user's profile id → 404 `"Profile not found"` (not 403 — existence isn't leaked); that user's own
  `GET /profiles` → `[]`.
- Deleting the current default profile (with 2 other profiles remaining) → the most-recently-created remaining
  profile (the clone) automatically became the new default.
- Test data left in the live dev cluster: `pranay@example.com` ended with 2 profiles ("GenAI Engineer (Senior)"
  non-default, "Software Engineer" default — the former clone); the originally-default "Data Engineer" profile
  was deleted during verification. Harmless, but a future session should know the table isn't empty.

**How to run it locally:** same as Phase 1 (`uv run alembic upgrade head`, `uv run uvicorn main:app --reload`) —
no new setup steps. Try `/docs` → login → Authorize → `POST /profiles` with a full nested body to see the shape.

### Gap-closing pass (post Phase 1+2) — ✅ done, one real bug found and fixed

After the initial Phase 1/2 builds, went back and specifically tested edge cases and failure paths that the
happy-path verification hadn't covered. Found and fixed one real concurrency bug; everything else passed.

**Bug found and fixed — unhandled CockroachDB serialization conflicts (500 instead of a clean retry/409).**
Firing two concurrent `POST /profiles/{id}/set-default` calls for the same user (racing to make two different
profiles the default) reliably produced one `200` and one raw `500` with:
`asyncpg.exceptions.SerializationError: restart transaction: TransactionRetryWithProtoRefreshError:
ReadWithinUncertaintyIntervalError` (SQLSTATE `40001`). This is CockroachDB's SERIALIZABLE isolation correctly
aborting the losing transaction under write contention — **not** data corruption (a follow-up check confirmed
exactly one profile stayed default, never zero or two) — but the app was propagating the DB's "please retry
me" signal as an unhandled 500 instead of retrying, which is CockroachDB's own documented required pattern for
SQLSTATE `40001` (see cockroachlabs.com/docs → transaction-retry-error-reference).
Fixed generically, not just for this one endpoint: added `with_serialization_retry()` and
`SerializationConflictError` to `core/database.py` — retries a service call up to 3 times on SQLSTATE `40001`
(checked via `exc.orig.sqlstate`, falling back to string-matching "restart transaction"), rolling back the
session between attempts; raises `SerializationConflictError` (→ router maps to `409`) only if still conflicting
after all retries, and re-raises immediately (no retry) for any other kind of DB error so unrelated bugs aren't
masked. Applied to every mutating endpoint in `profiles/routers/profile_router.py`
(create/update/delete/set-default/clone). Re-ran the same race 3 times after the fix — all 3 came back `200`/`200`
(the retry silently absorbed the conflict) with exactly one default profile in the final state each time.
**Any future mutating endpoint with a read-modify-write pattern (Gmail token refresh in Phase 6, applications in
Phase 5, etc.) should wrap its service call in `with_serialization_retry` the same way** — this class of error
can happen on any concurrent write, not just profile defaults.

**Also verified (all passed, no code changes needed):**
- Deleting a **non-default** profile leaves the actual default profile completely untouched.
- Deleting a user's **last remaining** profile succeeds cleanly (204, no reassignment error) and `GET /profiles`
  correctly returns `[]` afterward.
- Malformed input → clean `422`s: invalid UUID in a path param, missing required field (`target_job_title`),
  invalid enum value for `languages[].proficiency`.
- Disabled account (`is_active = false`, set directly via SQL): a **pre-issued token from before disabling** is
  rejected with `403 "Account is disabled"` on the next request (not just blocked at login) — confirms
  `core/dependencies.py`'s check runs on every request, not only at token issuance. Fresh login attempt on the
  disabled account → `401`. Account was re-enabled afterward to leave test data usable.
- Genuinely expired token (hand-crafted with `exp` 5 minutes in the past, signed with the real secret) → `401`,
  confirming PyJWT's expiry check actually fires and isn't just theoretically wired up.
- Concurrent race on invite-code claiming (two simultaneous signups against the same fresh code) → exactly one
  `201`, one clean `400` — the existing `SELECT ... FOR UPDATE` row lock in `auth_service.register_user` already
  serializes this correctly (confirmed only one new user row actually existed afterward), no `40001` surfaced
  here because the explicit lock prevents the conflict rather than needing a retry after the fact.

**Known, deliberately unverified: Swagger UI in an actual browser.** I don't have browser-automation tooling in
this environment, so the `/docs` → Authorize → paste-token flow described when Phase 1 was built has only been
proven indirectly (confirmed via curl that `HTTPBearer` is the security scheme in the OpenAPI schema, and that
the `Authorization: Bearer <token>` header round-trip it implies works end-to-end). If something looks off in
the actual Swagger UI, that's the one thing in this checklist that's inference, not observation.

**New test data from this pass:** `racer1@example.com` (jobseeker) with 2 profiles ("Profile A", "Profile B",
currently "Profile B" is default) — used for the concurrency races, harmless to leave.
