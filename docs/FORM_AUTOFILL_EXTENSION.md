# Extending Beyond LinkedIn: Autofilling Any Job Application Form

**Status:** Exploration / requirements doc, not yet scoped into `BUILD_PLAN.md`.
**Relates to:** `docs/prd.html` (existing Profile/Resume schema, Email Drafter agent pattern),
`docs/OPPORTUNITY_SOURCES_EXTENSION.md` (sourcing opportunities from career pages — this doc is
the natural next step once the user is *on* an application form, from whatever source).

This doc lays out how to extend the extension so it can fill in **any application form on any
site** the user is currently looking at — not just LinkedIn — split into two clearly different
problems: filling fields whose answer is already known data, and drafting answers to open-ended
questions that require generation.

---

## 1. Why this splits into two steps

A job application form is really two different kinds of input mixed together on one page:

- **Deterministic fields** — email, first name, last name, phone, current employer, LinkedIn URL,
  work authorization, years of experience. These already exist as structured data in
  `user_profiles` (Feature 2) and just need to be *placed into the right box*. This is a matching
  and DOM-manipulation problem, not a generation problem — no LLM call is needed at all for most of
  these.
- **Subjective/open-ended fields** — "Tell me about the most difficult situation you've faced in
  your career," "Describe a project where you implemented RAG," "Why do you want to work here?"
  These have no single correct value sitting in the profile; they need to be *written*, grounded in
  the user's real experience (profile + resume + relevant project details), the same class of
  problem the existing Email Drafter agent (Feature 5) already solves for cold-email bodies.

Treating these as one problem leads to either under-using the LLM (trying to "match" a subjective
question to a profile field, which doesn't work) or over-using it (burning a model call to decide
that a field labeled "Email" should get the user's email). Splitting them lets step 1 be nearly free
(pure JS, no network call) and step 2 reuse the agent infrastructure that's already proven out.

---

## 2. Step 1 — Known-field autofill

### 2.1 Field discovery
Runs entirely in the content script, on whatever page the user has the panel open on (no new
`host_permissions` needed beyond broadening the existing content-script match pattern from
LinkedIn-only to `<all_urls>` or a user-opt-in per-site list — see §5). Walk the current page's
`<form>` (or, for JS SPAs with no real `<form>` element, all `input`/`textarea`/`select`/
`[contenteditable]` elements reachable from a detected "application" container) and build a list of
field descriptors: tag/type, current value, associated label text, `name`/`id`/`autocomplete`
attributes, and — for constrained inputs — the available option set (`<select>` options, radio
group labels, checkbox label).

### 2.2 Classifying each field — a layered, mostly-free pipeline
Resolve fields in cheapest-first order, only escalating what's left unresolved:

1. **HTML `autocomplete` attribute first.** This is the actual web standard browsers themselves use
   to power native autofill (`autocomplete="given-name"`, `"family-name"`, `"email"`, `"tel"`,
   `"organization"`, `"address-level2"`, etc. — the WHATWG Autofill spec has ~50 standardized
   tokens). Well-built ATS forms (Greenhouse, Lever, Workday, iCIMS all use real `<input>` elements
   for the common fields) frequently set this correctly, since it's how they get Chrome's own
   autofill to work for their users too. Where present, this is a direct, free, unambiguous mapping
   to the profile schema — no matching logic needed.
2. **Label-text + name/id heuristic matching.** For fields without a usable `autocomplete` value,
   resolve the associated label (via `<label for>`, `aria-label`, `aria-labelledby`, or nearest
   preceding text node — the same "structural, not class-name-based" approach already used
   successfully for LinkedIn post extraction) and fuzzy-match it against a small synonym dictionary
   keyed to the existing `Profile`/`PersonalInfo` schema (`"first name"`/`"given name"`/`"legal
   first name"` → `first_name`; `"current company"`/`"employer"`/`"where do you currently work"` →
   derived from the profile's most recent `Experience` entry, etc.). This is the bulk of real-world
   coverage and, like `autocomplete`, costs nothing but a bit of JS.
3. **LLM fallback, batched, only for what's left.** Whatever fields survive steps 1–2 unresolved
   get sent — as a single batched call, not one call per field — to a small structured-output
   classifier: "given this label text and the list of known profile field keys, which key does this
   map to, or `none`." This mirrors the JD Parser's existing "regex first, LLM verifies/covers the
   rest" pattern (Feature 4). Because most fields resolve in steps 1–2, this call is small and rare,
   not a per-field cost.

### 2.3 Writing the value in — the actual hard engineering part
This is the part that has nothing to do with ToS or bot-blocking and everything to do with modern
web apps: **most ATS application forms are React/Vue/Angular SPAs where the visible `<input>` is
a controlled component.** Setting `element.value = "..."` directly does not update the framework's
internal state and the field will visually show the value for a moment and then snap back empty (or
submit empty) the instant the framework re-renders. The correct approach — well-established in the
browser-extension/autofill-tooling space — is to invoke the native property setter directly
(`Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(element,
value)`) and then dispatch a real `Event("input", { bubbles: true })` (and `"change"` for
selects/checkboxes) so the framework's own listener sees it exactly as it would a real keystroke.
This needs to be handled per input type:
- **Text/email/tel/etc.** — native setter + `input`/`change` events, as above.
- **`<select>`** — match the profile value against the option list's *visible text* (not just
  `value` attribute, which is often an opaque internal ID) using the same fuzzy-match approach as
  §2.2, then set `.value` to the matched option and dispatch `change`.
- **Radio/checkbox groups** — match the profile value (e.g. `work_authorization`,
  `willing_to_relocate`) against each option's label text, click the matched one programmatically
  (a real `.click()`, which naturally fires the right events, rather than toggling `.checked`
  directly).
- **File upload ("Resume", "Cover Letter")** — construct a `File` from the already-stored active
  resume PDF (same R2-backed blob Feature 3/6 already fetch for email attachments), wrap it in a
  `DataTransfer`, and assign `input.files = dataTransfer.files` + dispatch `change` — this is the
  standard (and only) way to programmatically populate a file input's `FileList`.
- **Address fields split across multiple inputs** (street/city/state/zip as separate boxes) — map
  each sub-input independently via the same label-matching pass rather than trying to detect "this
  is one address" as a unit.

### 2.4 Never silently submit
Every filled field gets a lightweight visual marker (e.g. a colored outline, consistent with the
existing "hover highlight via inline style" pattern from post extraction) so the user can see at a
glance what was auto-filled and review it before doing anything else. **The extension never clicks
Submit, and never auto-advances a multi-step form's "Next" button.** The user does that themselves,
after reviewing — this keeps a human in the loop for the one action (submission) that actually
matters to a site's terms of service and to the user's own risk (a wrong or half-filled field going
out under their name).

---

## 3. Step 2 — Subjective / open-ended questions

### 3.1 Detecting a "this needs writing, not matching" field
Heuristics: a `<textarea>` or `[contenteditable]` element, or a text input with a notably high
`maxlength` (a name field doesn't have `maxlength="2000"`; an essay question does), especially when
its associated label reads as a question or instruction rather than a data-field name (ends in `?`,
contains phrases like "describe," "tell us about," "explain," "why do you want to"). Any explicit
length constraint near the field (`maxlength` attribute, or visible helper text like "500 words
max" or a live character counter) is captured alongside the question text — the generated answer
must respect it.

### 3.2 Generating an answer — a new agent, same proven shape as Email Drafter
A new agent (e.g. `agents/form_answer_drafter/`) follows the exact pattern already validated three
times over (JD Parser, Resume Parser, Email Drafter): LangGraph `@entrypoint`/`@task`,
`ChatGroq(...).with_structured_output(...)`, the same multi-model fallback chain infrastructure
already built for the other three agents, and the same non-negotiable system-prompt rule Email
Drafter already enforces — **grounded only in the given profile/resume/project context, never
invents facts**. This matters more here than for a cold-email body: a fabricated answer to "explain
a project where you implemented RAG" is a much larger credibility risk if the user doesn't catch it
before submitting than a slightly generic email opener would be.

**Inputs the agent needs**, in order of how much they improve answer quality:
- The user's active profile (headline, skills, experience, project descriptions — the same
  `_build_profile_context()` shape Email Drafter already builds).
- The active resume's parsed content (same as Email Drafter's resume-context branch).
- **Job/company context, if available.** If the user arrived at this form via the tracker (an
  existing `applications` row with a parsed JD already sitting in the DB from extraction), pass
  that straight through — no extra work. If there's no existing application record (e.g. the user
  opened a career page's application form directly), best-effort grab just the job title/company
  name visible on the current page — not a full scrape of the site, just the same "read what's
  already rendered in front of the user" scope the LinkedIn extraction feature already operates
  under.
- The literal question text and any detected length constraint, passed verbatim — the agent should
  answer *that specific question*, not a generic version of it.

### 3.3 Consistency across applications — a small new `saved_answers` table
Common behavioral questions ("tell me about a challenge," "why this company," "describe a time you
disagreed with a teammate") recur across many different companies' forms almost verbatim. Two
things follow from that:
- **Reuse before regenerating.** Normalize the question text (lowercased, whitespace-collapsed —
  an embedding-similarity match is a reasonable upgrade later, but exact/near-exact matching
  covers the common case cheaply) and check a `saved_answers` table (`profile_id`, `question_text`,
  `answer`, `last_used_at`) before calling the agent again. This also means a user's own edits to a
  generated answer "stick" — the next time the same question appears, they see their edited version
  as the suggestion, not a fresh unrelated generation.
- **User answers should stay internally consistent.** If the RAG-project answer says the project cut
  latency by 40% in one application, the same question on a different company's form shouldn't
  produce a different number by chance of model sampling — reusing the saved answer (with an
  explicit "Regenerate" button for when the user *wants* a fresh take, e.g. to tailor tone to a
  specific company) solves this directly rather than needing the agent to somehow be deterministic.

### 3.4 Always a suggestion, never a submitted fact
The generated text is inserted into the field as an **editable, visually marked suggestion** (same
marker convention as step 1), and the user is expected to read and adjust it before moving on —
this is a strictly higher-scrutiny bar than step 1's structured fields, since prose has much more
room to be subtly wrong, off-tone, or (rarely, but possibly) not quite true to the specifics of the
question asked. No auto-submit here either, for the same reason as §2.4, more so.

---

## 4. ToS and ethics posture for this feature specifically

This feature is meaningfully **lower-risk** than the career-page-discovery doc's Tier 4/5 sourcing
question, and it's worth being explicit about why:

- It only ever acts on a page the user has personally navigated to and opened the panel on — there
  is no background fetching of other companies' pages, no scraping, no request to any server this
  extension doesn't already talk to. Functionally, this is the same category of thing as a password
  manager's or the browser's own native autofill — reading the current page's DOM and writing values
  into it on the user's explicit request.
- **Commercial precedent already exists for exactly this feature** (Simplify Jobs, Teal,
  Careerflow, LazyApply, and others ship "autofill this application" as a core feature) — this is
  not a novel or unusually risky category of browser extension behavior.
- The risk that *does* apply, and needs an explicit guardrail: some ATS platforms' terms of service
  prohibit "automated applications" specifically meaning **automated submission** (bulk, unattended
  application flows), not assisted data entry with a human reviewing and clicking Submit themselves.
  This doc's design keeps every fill action reviewable and puts the actual submit action solely in
  the user's hands, which keeps the feature on the "autofill assistant" side of that line rather
  than the "bot that applies to jobs unattended" side. **Do not build a "submit N applications
  automatically" mode** — that's the one line this feature must not cross, and it's also exactly
  the kind of usage pattern that gets an account or IP flagged by the sites it operates on.
- **If a CAPTCHA or bot-verification challenge appears on the form itself, stop and let the user
  solve it manually.** Do not attempt to detect, solve, or route around it — same posture as the
  sourcing doc's stance on Tier 5 sites, applied here to individual forms rather than whole
  domains.
- Writing native `input`/`change` events to make a value stick in a React-controlled field (§2.3)
  is a compatibility technique, not an anti-detection one — it's solving "the framework didn't see
  my change," which is a completely different problem from "the site is trying to tell I'm not
  human." No fingerprint-spoofing, timing-randomization, or stealth technique is needed or should be
  added for this feature; there's no adversary to evade in the first place when a human is sitting
  there clicking Submit.

---

## 5. Scope/permissions change this implies

Today the extension's `host_permissions`/content-script matches are LinkedIn-only. Supporting
"any form on any site" means broadening this, which is a real, user-visible permission change (a
content script running on every page a person visits is a much bigger ask than "runs on
linkedin.com"). Two reasonable options, not mutually exclusive:
- **User-maintained site allowlist** (Options page: "enable on these domains"), defaulting to
  empty/off everywhere except LinkedIn — matches Chrome's own permission model
  (`activeTab`/optional host permissions requested per-site) and avoids asking for a blanket
  `<all_urls>` grant up front.
- **`activeTab` + explicit user action** (e.g. clicking the toolbar icon or a keyboard shortcut
  grants access to just the current tab for that session) — no persistent broad host permission at
  all, at the cost of needing the user to trigger it per form rather than it working automatically.
This is a decision to make explicitly before implementation, not an afterthought — it directly
affects the Chrome Web Store review process too (broad host permissions draw more review scrutiny
than `activeTab`).

---

## 6. Compute cost

This feature is **far cheaper than the career-page-sourcing doc** — there is no background
crawling, no headless browser, no new fetches to third-party servers at all:

| Piece | Cost |
|---|---|
| Field discovery + `autocomplete`/label-matching (§2.1–2.2 steps 1–2) | Pure client-side JS, runs once per form, effectively free (milliseconds, no network call). |
| LLM field-classification fallback (§2.2 step 3) | One small batched call per form, only for the (usually few) fields steps 1–2 couldn't resolve — same cost class as a single JD Parser call. |
| Subjective-question generation (§3.2) | One agent call per *distinct, not-yet-answered* question — the `saved_answers` reuse (§3.3) means this cost is paid once per question ever seen, not once per application. |
| DOM writing (§2.3) | Free, synchronous JS. |

No new infrastructure, no browser automation, no proxies — this reuses the exact `agents/*` +
`agent_usage_logs` plumbing already built for Features 3–5, just pointed at a new input shape
(a form field's label/question instead of a LinkedIn post).

---

## 7. Architecture integration sketch

- **`content/formFiller.ts`** (new, extension) — field discovery, classification-pipeline steps 1–2,
  DOM writing (§2.3), the visual "filled/suggested" marker convention. Triggered by a new
  panel action ("Fill this form") rather than running automatically on every page load, consistent
  with this project's existing "user-initiated, not passive scanning" posture.
- **`background/service-worker.ts`** — new messages: `CLASSIFY_FIELDS` (batched fallback to the
  backend for step 1's step-3 escalation), `GET_SAVED_ANSWER` / `DRAFT_FORM_ANSWER` /
  `SAVE_ANSWER_EDIT`.
- **`backend/agents/form_answer_drafter/`** (new) — mirrors `email_drafter/` exactly (schemas.py +
  agent.py, same multi-model fallback list pattern, same `agent_usage_logs` instrumentation).
- **A small field-classification endpoint** (reuses `jd_parser`-style "structured output, small
  fixed schema" agent, or could even be a cheap non-LLM heuristic-only v1 with the LLM fallback
  added later once real-world label-text variety is observed).
- **New `form_answers` table** (`profile_id`, `question_text_normalized`, `answer`, `source:
  generated|user_edited`, `last_used_at`) — small, independent of `applications`, since the same
  answer can and should be reused across many different application records.
- **Profile schema** — no changes needed; step 1 only *reads* the existing `user_profiles` shape
  (Feature 2) plus the active resume (Feature 3).

---

## 8. Recommended phasing

1. **Step 1 only, `autocomplete` + label-heuristics, no LLM fallback yet.** Validates the DOM-write
   mechanics (the React-controlled-input problem in §2.3 is the real engineering risk here) against
   a handful of real ATS forms (Greenhouse and Lever's own hosted application pages are good first
   targets — well-structured, high adoption, likely to have correct `autocomplete` attributes).
2. **Add the LLM classification fallback** once real unmapped-field label text has been observed
   across enough real forms to know it's actually needed and to shape the synonym dictionary from
   real examples rather than guesses.
3. **Add step 2 (subjective questions)**, starting with no `saved_answers` reuse (simplest correct
   version), get the grounding/quality bar right first.
4. **Add `saved_answers` reuse/regenerate** once step 2 is generating decent answers and the
   "same question, different company" pattern is actually observed in practice.
5. **Never**: an unattended "auto-submit" or "auto-advance multi-step form" mode — see §4.
