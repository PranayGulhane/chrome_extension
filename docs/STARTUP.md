# Startup Guide — running the stack locally

How to bring up all three pieces of this project on a dev machine, in the right order, on the
right ports. Written against the current repo state (2026-07-28) and the Windows machine this
project is developed on.

## The three processes and their ports

| # | Piece | Directory | Port | URL |
|---|-------|-----------|------|-----|
| 1 | Backend API (FastAPI/uvicorn) | `backend/` | **8123** | `http://localhost:8123` |
| 2 | Web SPA (Vite dev server) | `frontend/web/` | **5173** | `http://localhost:5173` |
| 3 | Chrome extension (build only, no server) | `frontend/extension/` | — | loaded unpacked from `dist/` |

The database is **not** local — it's a CockroachDB Cloud serverless cluster reached over the
network via `DATABASE_URL`. There is no Docker/compose step.

**These ports are not arbitrary — do not change them casually.** Four things are hardcoded to
them:

- `frontend/web/src/api/config.ts` → `http://localhost:8123`
- `frontend/extension/src/shared/config.ts` → `http://127.0.0.1:8123` (API) and
  `http://localhost:5173` (SPA link)
- `frontend/extension/public/manifest.json` → `host_permissions: ["http://127.0.0.1:8123/*"]`
- `backend/.env` → `GOOGLE_REDIRECT_URI=http://127.0.0.1:8123/gmail/oauth/callback`, which must
  match the redirect URI registered on the Google Cloud OAuth client exactly

Changing the backend port means editing all four *and* the Google Cloud console entry.

### `localhost` vs `127.0.0.1` — they are not interchangeable here

Both resolve to the same machine, but browsers treat them as **different sites** for `SameSite`
cookie purposes, and the auth cookies are `SameSite=Strict`.

- **Web SPA → backend: use `localhost`.** The SPA runs on `http://localhost:5173`, so it must
  call `http://localhost:8123`. Using `127.0.0.1` makes the browser set the cookie on login and
  then refuse to send it back — you get silent-looking `401`s on `/auth/me`.
- **Extension → backend: use `127.0.0.1`.** That's what `manifest.json`'s `host_permissions`
  grants and what the Google OAuth redirect URI is registered as.

Uvicorn's default bind (`127.0.0.1`) serves both names, so no extra flag is needed — just keep
each frontend pointed at the hostname it already uses.

---

## One-time setup

### Prerequisites

- **Python 3.12** — pinned by `backend/.python-version`. Do not use the system Python 3.14;
  `uv` installs and manages 3.12 itself.
- **`uv`** — installed at `%APPDATA%\Python\Python314\Scripts\uv.exe`. It is **not on PATH**, so
  either add that directory to PATH or invoke it by full path:
  ```powershell
  & "$env:APPDATA\Python\Python314\Scripts\uv.exe" --version
  ```
  All `uv ...` commands below assume it's on PATH; otherwise substitute the full path.
- **Node.js** — v23.11.1 / npm 10.9.2 on system PATH. No version pinning needed.
- **Google Chrome** — for the extension.

### Backend environment file

`backend/.env` already exists on this machine. On a fresh checkout, copy the template and fill it
in:

```powershell
Copy-Item backend\.env.example backend\.env
```

Required keys (all documented inline in `.env.example`):

| Key | Notes |
|-----|-------|
| `DATABASE_URL` | CockroachDB Cloud, asyncpg driver. Use `sslmode=require`, **not** `verify-full` — asyncpg needs a local CA bundle for the latter. |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENVIRONMENT` | `development` — keeps cookies non-`Secure` so they work over plain `http://`. |
| `CORS_ORIGINS` | JSON list. Must include `http://localhost:5173`. Currently `["http://localhost:5173","http://localhost:5174"]`. |
| `GROQ_API_KEY` | LLM agents. https://console.groq.com/keys |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` | Cloudflare R2, stores resume PDFs. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth client of type **Web application**. |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:8123/gmail/oauth/callback` — must match Google Cloud exactly. |
| `GMAIL_TOKEN_ENCRYPTION_KEY` | AES-256-GCM key: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

Every key above without a default in `core/config.py` is mandatory — the app refuses to start with
a pydantic-settings `ValidationError` if any is missing. The existing `backend/.env` on this
machine has all thirteen.

`.env` is gitignored. Never commit it.

### Install dependencies

```powershell
cd backend
uv sync

cd ..\frontend\web
npm install

cd ..\extension
npm install
```

---

## Every-session startup

Run these in **three separate terminals** (the first two are long-running).

### 1. Backend — port 8123

```powershell
cd backend
uv run alembic upgrade head
uv run uvicorn main:app --port 8123
```

`alembic upgrade head` reads `DATABASE_URL` straight from `core/config.py` (see
`alembic/env.py:27`), so there's no separate DB config to keep in sync. Re-run it only when new
migrations land in `alembic/versions/`.

**Omit `--reload`.** On this Windows machine, uvicorn's `--reload` has been observed logging
`WatchFiles detected changes ... Reloading...` while **never actually respawning the worker
process** — the stale process keeps serving requests and your code change silently doesn't take
effect. This cost a full debugging round once already. Restart uvicorn manually (Ctrl+C, re-run)
after every backend code change.

If you suspect a stale worker anyway, verify the PID rather than trusting the log:

```powershell
Get-NetTCPConnection -LocalPort 8123 | Select-Object OwningProcess
Get-Process -Id <pid>
```

Confirm it's up:

```powershell
Invoke-RestMethod http://localhost:8123/health   # -> status: ok
```

Interactive API docs: `http://localhost:8123/docs`.

### 2. Web SPA — port 5173

```powershell
cd frontend\web
npm run dev
```

Serves `http://localhost:5173`. Vite's config (`vite.config.ts`) does not pin the port, so **if
5173 is already taken Vite silently moves to 5174** — and the extension's "open web app" link
still points at 5173. If you see that, kill whatever holds 5173 rather than accepting the drift,
or start it explicitly:

```powershell
npm run dev -- --port 5173 --strictPort
```

(`--strictPort` makes Vite fail loudly instead of hopping ports.) `.env`'s `CORS_ORIGINS` already
allows 5174 as a fallback, so the SPA will still function on it — only the extension's deep link
breaks.

Routes: `/login`, `/signup`, `/profiles`, `/profiles/:id`, `/profiles/:id/view`, `/tracker`,
`/tracker/:id`, `/metrics`, `/admin` (admin-gated).

### 3. Chrome extension — build, then load unpacked

The extension has no dev server. It's a two-pass Vite library build (background worker and content
script are built separately — see the comments in `vite.background.config.ts`):

```powershell
cd frontend\extension
npm run build          # one-shot -> dist/{background.js, content.js, manifest.json}
# or
npm run dev            # same build with --watch
```

Then in Chrome, once:

1. `chrome://extensions`
2. Enable **Developer mode** (top right)
3. **Load unpacked** → select `frontend\extension\dist`

After each rebuild, click the **reload** (↻) icon on the extension card in `chrome://extensions`,
then **hard-refresh the LinkedIn tab** — the old content script stays injected in already-open
tabs otherwise. `npm run dev`'s watch mode rebuilds the files but cannot reload the extension for
you; both manual steps are still required.

Usage: open a LinkedIn page and press **Alt+J** (or click the toolbar icon) to toggle the floating
panel. **Esc** closes it.

---

## Startup order and dependencies

```
backend (8123)  ──┬──> web SPA (5173)     needs backend for /auth/*, profiles, tracker
                  └──> extension          needs backend for everything; opens SPA at 5173
```

Start the backend first. The other two will load without it but every API call fails.

## Quick reference

```powershell
# Terminal 1 — backend
cd backend; uv run uvicorn main:app --port 8123

# Terminal 2 — web SPA
cd frontend\web; npm run dev -- --port 5173 --strictPort

# Terminal 3 — extension (rebuild after each change)
cd frontend\extension; npm run build
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Pydantic `ValidationError` naming `r2_account_id` etc. on startup | Missing keys in `backend/.env`. Every non-defaulted field in `core/config.py` is mandatory. |
| Login succeeds but `/auth/me` immediately 401s in the SPA | Hostname mismatch — SPA on `localhost` calling `127.0.0.1` (or vice versa). `SameSite=Strict` cookie is set but not sent back. Keep the SPA on `localhost` on both sides. |
| CORS error in the SPA console | The SPA's actual origin isn't in `.env`'s `CORS_ORIGINS` — commonly because Vite drifted to 5174+. Restart the backend after editing `.env`. |
| Backend code change has no effect | Stale uvicorn worker. Don't trust `--reload`'s log — verify the PID via `Get-NetTCPConnection -LocalPort 8123`, or restart without `--reload`. |
| Extension change has no effect | Rebuilt but didn't reload the extension in `chrome://extensions` and hard-refresh the LinkedIn tab. |
| Extension network calls blocked | Backend not on `127.0.0.1:8123` — that exact origin is what `manifest.json`'s `host_permissions` grants. |
| Gmail OAuth `redirect_uri_mismatch` | `GOOGLE_REDIRECT_URI` must match the Google Cloud OAuth client's registered URI character-for-character, including `127.0.0.1` and port 8123. |
| Agent calls fail with `RateLimitError` / "tokens per day" | Groq free-tier daily quota, not a code bug. Wait for the window to roll over or upgrade the account. Each agent has a model fallback chain in `core/config.py`. |
| `uv` not found | Not on PATH. Use `& "$env:APPDATA\Python\Python314\Scripts\uv.exe"`. |

## See also

- `docs/PROGRESS.md` — feature-by-feature build log, environment notes, and the full story behind
  the gotchas summarized above.
- `docs/BUILD_PLAN.md` — scope and feature list.
- `docs/prd.html` — product spec.







