# Extending Beyond LinkedIn: Career Pages & Public Job Sources

**Status:** Exploration / requirements doc, not yet scoped into `BUILD_PLAN.md`.
**Relates to:** `docs/prd.html` §02 (Non-Goals: "No support for job boards other than LinkedIn in v1"),
`docs/PROGRESS.md` Feature 4 (LinkedIn ToS posture).

This doc lays out how to extend the platform to source opportunities from company career pages and
the wider public internet — not just posts a user manually clicks on LinkedIn — without violating
ToS or getting stuck in bot-blocking arms races, and what that costs in engineering and compute.

---

## 1. Why this is a different problem than what's built today

The current architecture is deliberately **single-post, click-initiated, user-driven**:

- The user finds a post themselves (via LinkedIn search).
- The user clicks it. One extraction. A 3-second client-side throttle exists specifically so nothing
  could be mistaken for automated scanning.
- There is no "scan all posts" affordance, and the PRD/PROGRESS notes say there must never be one.

That posture works because a human is in the loop for every single fetch — it doesn't look like a
bot to LinkedIn, and it doesn't need to survive LinkedIn's anti-automation defenses because it isn't
automation from LinkedIn's perspective.

**"Extend to career pages and the public internet" is a fundamentally different ask**: it implies
*discovering* opportunities the user hasn't seen yet, which means fetching pages nobody clicked,
usually on a schedule, across many companies. That's automation by definition. The question becomes
which sources tolerate automation, on what terms, and at what cost — not how to disguise a bot as a
human.

---

## 2. The source landscape, ranked by how automatable they are

### Tier 1 — Structured APIs (no scraping at all)

Most mid-size-to-large companies don't hand-roll their careers page; they embed an **ATS (Applicant
Tracking System)** widget, and several of the big ATS vendors expose the *same data the widget
renders* as a public, documented, unauthenticated JSON API:

| ATS | Public API | Notes |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{board_token}/jobs` | Fully open, no key needed, documented. Huge adoption (thousands of companies). |
| Lever | `api.lever.co/v0/postings/{company}?mode=json` | Fully open, documented, JSON. |
| Ashby | `jobs.ashbyhq.com/api/non-user-graphql` (public job board GraphQL) | Documented for embedding; same data as their public board pages. |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{company}/postings` | Public postings API, documented. |
| Workday | No general public API; each tenant's `wd*.myworkdayjobs.com` site is a JS SPA backed by an internal-but-discoverable JSON endpoint (`/wday/cxs/...`). Not "documented for third parties" — gray area, see §3. |
| Recruitee, Personio, Teamtait, etc. | Most smaller ATS vendors have a similar public "jobs JSON" feed powering their own embeddable widget. |

**This is the highest-leverage tier.** It requires zero browser automation, zero bot-blocker
concerns (these are meant to be machine-read — that's the whole point of a "job board API"), trivial
compute (plain HTTP GET + JSON parse), and no ToS ambiguity because the vendor built the endpoint
*for* consumption outside their own site. The catch: coverage is capped at however many companies
you bother to map to their ATS + board token, and you don't get *arbitrary* company career pages this
way — only ones on a supported ATS.

### Tier 2 — RSS/job feeds and aggregator APIs

- Aggregators like **RemoteOK, WeWorkRemotely, Indeed (limited/paid), Adzuna, USAJobs, The Muse,
  Arbeitnow, Himalayas** publish either free public JSON/RSS feeds or a documented (sometimes paid)
  API with clear usage terms. These exist specifically to be consumed programmatically.
- Same profile as Tier 1: legal by design, cheap, no bot-blocking to fight.
- Coverage and freshness vary; some (Indeed) heavily restrict or paywall API access precisely because
  they don't want you scraping their site instead — a strong signal about where the ToS line is.

### Tier 3 — Static/server-rendered career pages with no API

Plenty of smaller companies just have a plain HTML "Careers" page (sometimes hand-written, sometimes
a lightweight ATS that server-renders HTML instead of exposing JSON). These can be fetched with a
**plain HTTP client** (no browser) and parsed with an HTML parser — no JavaScript execution needed,
so no Playwright/Selenium, no headless-browser fingerprint, no bot-blocker interaction at all beyond
normal rate-limiting courtesy. This is still "scraping" in the colloquial sense but technically and
legally lighter than Tier 4.

### Tier 4 — JS-rendered pages that require a real browser to see content

Some career pages (React/Vue/Angular SPAs, some Workday tenants, some custom-built ones) render the
job list client-side via JS after page load — a plain HTTP GET returns an empty shell. This is the
tier that actually needs Playwright/Selenium, and it's also the tier most likely to run anti-bot
defenses (Cloudflare, PerimeterX/HUMAN, DataDome, Akamai Bot Manager), because those defenses are
sold as a bundle to companies and get turned on site-wide, careers page included, whether or not the
careers page itself has anything worth protecting.

### Tier 5 — Sites that explicitly prohibit automated access

LinkedIn, Indeed (for scraping, as opposed to their limited API), and many others state in their
Terms of Service that automated scraping is prohibited, and back it with active bot detection. This
tier should be **out of scope for anything beyond what's already built** (the click-initiated,
human-in-the-loop LinkedIn flow). Automating around a site's explicit anti-scraping stance is exactly
the "getting stuck in bot blockers" problem the question is asking how to avoid — the honest answer
for this tier is: don't build the automation, keep the human-click model, or use their official API
if one exists (LinkedIn does have a limited, restrictive, partner-only Jobs API — not realistically
accessible to an individual project).

---

## 3. Where the actual legal/ToS line is (practically speaking, not legal advice)

- **robots.txt and a site's ToS are the first and clearest signal.** If `robots.txt` disallows a path,
  or the ToS has an explicit "no automated access / no scraping" clause, treat that as a hard no for
  that site — this is squarely what the question is trying to avoid, and it's also usually correlated
  with the site actively investing in bot detection (i.e., trying to route around it is also the most
  compute-expensive option).
- **Public API endpoints designed for third-party consumption (Tier 1/2) are unambiguous** — no ToS
  conflict, because being machine-read is the intended use.
- **Plain server-rendered pages with no anti-bot stance and no explicit prohibition (Tier 3)** are the
  legally-greyest-but-most-tolerated zone — the *hiQ Labs v. LinkedIn* line of US case law leans
  toward "scraping publicly accessible data that doesn't require bypassing an access control isn't a
  CFAA violation," but that's about criminal liability, not a company's own ToS-based civil claims,
  and it doesn't apply outside the US. Practical mitigations regardless of jurisdiction:
  - Identify the crawler honestly in the `User-Agent` (a real product name + a contact URL/email),
    the way well-behaved crawlers (Googlebot, etc.) do.
  - Respect `robots.txt` and any documented crawl-delay.
  - Rate-limit aggressively per-domain (e.g., one request every several seconds per company site,
    not concurrent hammering) — this is both the ethical thing and the thing that keeps you off a
    bot-blocker's radar in the first place, since most WAF/anti-bot triggers are volume- or
    pattern-based.
  - Only store what's needed for the product's purpose (job postings), not a full site mirror.
  - Provide a way for a site owner to ask to be excluded (even just an email in the UA string covers
    this in practice).
- **Tier 4/5 sites actively defending against bots** are where "getting stuck in bot blockers" stops
  being an incidental risk and becomes the entire cost center — see §4. The realistic choices here
  are: (a) skip the site, (b) use its official API if one exists, or (c) pay for the site's own
  paid/partner API tier if offered. Building a stealth pipeline specifically to defeat commercial
  anti-bot vendors (CAPTCHA-solving services, residential proxy rotation, browser fingerprint
  spoofing) is the "arms race" the question is trying to avoid, is against those platforms' terms
  practically by definition, and is not recommended for this project regardless of technical
  feasibility.

**Recommended posture for this project:** build Tiers 1–3 (structured APIs, feeds, and plain HTML
career pages with no anti-bot stance). Deliberately do not build Tier 4/5 automation. This mirrors
the existing LinkedIn decision (human-click, no bulk scan) — it's not a technical limitation, it's a
line drawn on purpose.

---

## 4. Do Playwright/Selenium help, and how do bot blockers actually work?

**Short answer: they help you render JS-heavy pages (Tier 4), but they do not help you evade
detection, and detection is the actual problem at that tier — so for the scope this project should
target (Tiers 1–3), neither tool is needed at all.**

### What Playwright/Selenium actually are
Both drive a real (or real-ish) browser engine programmatically — Selenium via the WebDriver
protocol, Playwright via each browser's native devtools/automation protocol (faster, more modern,
better at intercepting network calls). Both execute JavaScript exactly like a human's browser would,
which is the only reason to reach for them: **rendering client-side content**, not "looking human."

### How commercial anti-bot systems (Cloudflare, DataDome, PerimeterX/HUMAN, Akamai) actually detect automation
- **TLS/JA3 fingerprinting** — the exact cipher suite order/extensions a client offers during the TLS
  handshake differs between real Chrome and most automation stacks (including default
  Playwright/Selenium configurations, and virtually all plain HTTP libraries) — flagged before a
  single byte of HTTP is even sent.
- **Browser fingerprinting** — `navigator.webdriver === true` (set by default in automated browsers
  unless explicitly patched), missing or inconsistent `navigator.plugins`/`navigator.languages`,
  headless-specific rendering quirks (canvas/WebGL output, font enumeration, `Notification.permission`
  defaults), and inconsistent screen/viewport metadata.
- **Behavioral signals** — mouse movement (or its total absence), scroll patterns, keystroke timing,
  time-to-first-interaction. A script that jumps straight to reading the DOM with zero simulated
  human interaction is trivially distinguishable from a real visit.
- **Network-level signals** — request volume/pattern per IP, datacenter vs. residential IP ranges
  (most cloud compute — AWS/GCP/Azure/Cloudflare Workers/most VPS — is on well-known datacenter IP
  lists that get flagged immediately), and repeat visits with identical fingerprints.
- **Challenge pages** — when suspicious, these systems serve a JS challenge (compute a
  proof-of-work, solve a CAPTCHA, or just silently tarpit) rather than blocking outright, and
  outsmarting *that* dynamically is the actual "arms race": "stealth" plugins
  (`playwright-extra` + `puppeteer-extra-plugin-stealth`) patch the easy fingerprint tells,
  but DataDome/Cloudflare/PerimeterX update their detection within weeks of any popular stealth
  patch becoming known, commercial CAPTCHA-solving services exist specifically to plug the resulting
  gap (2Captcha, Anti-Captcha, CapSolver — priced per solve), and residential-proxy providers
  (Bright Data, Oxylabs, Smartproxy) exist specifically to dodge the datacenter-IP signal — each of
  these is a recurring dollar cost per request, not a one-time engineering fix, precisely because the
  defending side keeps moving.

This is the treadmill the question is asking to avoid, and the recommendation in §3 is exactly to not
get on it: any site running one of these vendors and actively contesting automated access is a site
where "help" from Playwright/Selenium is real but the underlying goal (defeat the anti-bot vendor) is
the thing to skip, not solve.

### Where Playwright/Selenium are legitimately useful here (Tier 3/4 boundary, no active anti-bot vendor)
A plain small-company career page built as a React/Vue SPA with **no** Cloudflare/DataDome/PerimeterX
in front of it isn't "detecting" anything — it just needs JS execution to produce the job list HTML.
Playwright (preferred over Selenium: faster startup, first-class async API, better network
interception so you can often grab the underlying JSON XHR response directly instead of parsing
rendered HTML at all — many "SPA career pages" are just as easily consumed by intercepting their own
internal `fetch()`/XHR call as by rendering the page and scraping the DOM) is the right tool for
exactly this: no adversary, just a rendering requirement.

Practical rule of thumb before reaching for a browser at all: **check the Network tab first.** A
large fraction of "JS-rendered" career pages are calling a JSON endpoint under the hood (their own
internal API, even if undocumented) — hitting that endpoint directly with a plain HTTP client is
strictly cheaper and more reliable than rendering the whole page, and it's the same principle as
Tier 1/2 (consume structured data, don't scrape rendered HTML) even when the company didn't intend to
publish an "API."

---

## 5. Compute cost estimate

Costs scale entirely with how much of Tier 3/4 (real page fetch/render) you do vs. Tier 1/2 (API
calls). Rough numbers for planning:

| Approach | Per-fetch cost | Concurrency ceiling on a small VM (e.g. 2 vCPU / 4GB) | Notes |
|---|---|---|---|
| Tier 1/2 — JSON API call (`httpx`) | ~5–50ms CPU, a few KB RAM, negligible | Hundreds concurrent | Same cost class as this project's existing `httpx` calls to Google/Groq. No new infra. |
| Tier 3 — plain HTTP GET + HTML parse (`httpx` + `selectolax`/`beautifulsoup4`) | ~20–100ms CPU, a few MB RAM | 50–100+ concurrent | Still cheap; the parse, not the fetch, dominates CPU. |
| Tier 4 — headless Playwright page render | ~1–3s wall time, **150–400MB RAM per browser context**, meaningful CPU during JS execution/rendering | Realistically 3–8 concurrent contexts per 4GB of RAM before swapping/instability (each Chromium process is heavy even headless) | This is the expensive tier. A scheduled crawl of, say, 200 JS-rendered career pages sequentially at 2s each is ~7 minutes; running them at concurrency 5 is more like ~90 seconds but needs ~1–2GB RAM headroom just for browser contexts, on top of the rest of the backend. |

**Practical sizing for this project's likely scale** (a personal/small-user-base tool crawling
maybe dozens to low-hundreds of company sources on a daily/hourly schedule, not continuous
high-volume crawling):

- If sourcing stays in Tiers 1–3 (recommended scope, §3): the existing backend's current
  CockroachDB-Cloud + no-Docker, single small process setup handles this with no new infrastructure
  — it's the same shape of I/O-bound `httpx` work the app already does for Google/Groq calls, run on
  a schedule instead of per-request.
- If Tier 4 is added for a *small, curated* allowlist of specific known-JS-only career pages (not a
  general crawler): budget a dedicated worker process with Playwright installed (~400–500MB extra
  disk for the browser binaries, `playwright install chromium`), run with low concurrency (2–4
  contexts), and treat it as a background job, not something that ever blocks a user-facing request.
  A single low-end VM (2 vCPU/4GB) is enough at this scale; there is no case for a browser farm or
  headless-browser-as-a-service product (Browserless, ScrapingBee, Bright Data Scraping Browser) at
  the volumes implied by "a personal job-search tool," and those services exist mainly to absorb the
  Tier 4/5 anti-bot arms race cost — which is exactly the tier this project should avoid entering in
  the first place.
- **Do not budget for proxy rotation or CAPTCHA-solving services** — needing either is itself the
  signal that a source has crossed from Tier 3/4 into Tier 5 and should be dropped, not engineered
  around.

---

## 6. How this would extend the existing platform, at a glance

(High-level shape only — not a committed plan; would need its own design pass before implementation.)

- **New `backend/sources/` module**, sibling to `applications/`/`profiles/`: an `OpportunitySource`
  concept (ATS connector config — company name, ATS type, board token/URL) and a scheduled job
  (APScheduler or a simple cron-triggered script, given there's no existing task-queue infra like
  Celery/Redis in this stack) that polls Tier 1/2 APIs first, Tier 3 static pages second.
- **Reuse the existing JD Parser agent unchanged** — a Greenhouse/Lever JSON posting or a scraped
  HTML job description is still "raw job text in, structured job data out," the exact shape
  `agents/jd_parser` already handles. No new agent needed for parsing; only the *acquisition* layer
  is new.
- **`applications` table already has room for this** — `poster_profile_url`/`post_url` are
  LinkedIn-shaped names today, but a `source_type` (`linkedin` / `greenhouse` / `lever` / `manual`
  scrape / …) column would let the same table represent a career-page-sourced opportunity without a
  schema rewrite, since job_title/company/skills/email/status/outreach_type are all already
  source-agnostic.
- **New user-facing surface**: instead of "click a post," this becomes "browse a feed of
  auto-discovered postings matching your profile" — which is much closer to the already-planned (v2,
  Feature 9) **Post Relevance Scorer** agent than to anything LinkedIn-specific. That agent's
  `(parsed_jd, user_profile) → score` shape is exactly what would rank/filter an auto-discovered feed,
  suggesting this extension and the existing Relevance Scorer backlog item should be designed
  together rather than separately.
- **New dependency**: `httpx` (already a dependency) covers Tiers 1–3 entirely. Playwright would be
  an additive, optional dependency (`playwright` + a one-time `playwright install chromium`) isolated
  to whatever narrow Tier 4 allowlist is decided on later — not a core requirement for the first cut
  of this feature.

---

## 7. Recommended phasing (if pursued)

1. **Tier 1 only, smallest possible slice**: hardcode a handful of Greenhouse/Lever board tokens for
   companies the user actually cares about, poll their public JSON APIs on a schedule, feed results
   through the existing JD Parser, surface as a new list. Zero bot-blocker risk, zero new heavy infra,
   validates the end-to-end shape (source → parse → dedupe against existing `applications` →
   surface to user) cheaply.
2. **Add Tier 2 aggregator feeds** (RemoteOK/Arbeitnow/etc.) for broader coverage without adding new
   scraping surface.
3. **Add Tier 3** (plain HTML career pages, `httpx` + an HTML parser, no browser) for companies not
   on a Tier 1 ATS, with strict per-domain rate limiting and an honest User-Agent from day one.
4. **Only if there's a clear, specific need**: a narrow, explicitly-allowlisted Tier 4 Playwright
   worker for a small number of known JS-only career pages that have no anti-bot vendor in front of
   them — checked individually, not treated as a general crawler.
5. **Never**: Tier 5 (sites with an explicit no-scraping stance and active bot defense). If a
   specific company's postings only exist behind that kind of wall, the answer is "not sourced
   automatically," same as the deliberate decision already made for LinkedIn's own bulk-scan
   question.
