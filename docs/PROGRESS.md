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
| 3 | Resume upload & parsing | ⬜ not started |
| 4 | Post extraction + JD parsing | ⬜ not started |
| 5 | Email drafting | ⬜ not started |
| 6 | Gmail connect + send | ⬜ not started |
| 7 | Application tracker | ⬜ not started |
| 8 | Metrics + Admin dashboard | ⬜ not started |
| 9 | *(v2)* Post Relevance Scorer | ⬜ not started |

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
