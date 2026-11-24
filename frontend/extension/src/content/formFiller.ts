import type { ExperienceSummary, ProfileDetail } from "../shared/types";

// Step 1 of form-autofill (see docs/FORM_AUTOFILL_EXTENSION.md, docs/prd.html §13): fills
// deterministic fields (name/email/phone/current employer/etc.) directly from the active profile.
// Classification is layered, cheapest-first (§2.2): autocomplete attribute, then a synonym match
// against a corpus built from the field's label *and* its name/id/placeholder attributes (many ATS
// forms render the visible caption as unlinked text, so label-only matching misses most of the
// page), then — because every company phrases the same field differently ("Candidate Name" vs.
// "Full Name" vs. "Full Name (as per ID proof)" vs. separate First/Last boxes) and no fixed synonym
// list will ever cover all of them — a batched LLM fallback (see classifyUnmatched param on
// autofillForm) for whatever the heuristics still couldn't confidently match. Subjective/essay
// questions are detected and left untouched regardless of which layer would otherwise classify
// them; answering them is Step 2, a separate feature.

export type ProfileFieldKey =
  | "first_name"
  | "last_name"
  | "full_name"
  | "email"
  | "phone_number"
  | "current_city"
  | "state_province"
  | "country"
  | "linkedin_url"
  | "github_url"
  | "portfolio_website"
  | "personal_website"
  | "work_authorization"
  | "willing_to_relocate"
  | "nationality"
  | "current_employer"
  | "current_job_title";

// Runtime mirror of the type above — needed to validate the LLM-fallback response (see
// classifyUnmatched below) against the known vocabulary before trusting it, since a `fetch().json()`
// result is only ever as trustworthy as its runtime shape, regardless of what the response's TS
// type claims. Keep in sync with backend/agents/field_classifier/schemas.py's ProfileFieldKey.
const PROFILE_FIELD_KEYS = new Set<ProfileFieldKey>([
  "first_name",
  "last_name",
  "full_name",
  "email",
  "phone_number",
  "current_city",
  "state_province",
  "country",
  "linkedin_url",
  "github_url",
  "portfolio_website",
  "personal_website",
  "work_authorization",
  "willing_to_relocate",
  "nationality",
  "current_employer",
  "current_job_title",
]);

export function isProfileFieldKey(value: unknown): value is ProfileFieldKey {
  return typeof value === "string" && PROFILE_FIELD_KEYS.has(value as ProfileFieldKey);
}

interface FieldOption {
  value: string;
  text: string;
}

interface FieldDescriptor {
  el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
  tag: string;
  type: string; // input type, "select", "textarea", or "radio-group"
  autocomplete: string | null;
  label: string; // best-effort display label, used for the "filled"/"skipped" UI list
  matchText: string; // normalized corpus (label + name/id/placeholder) used for synonym matching — a superset of `label`, since many custom-styled ATS forms carry no visible/linked label at all
  maxLength: number | null;
  options?: FieldOption[]; // select options, or one entry per radio in a "radio-group"
  optionElements?: HTMLInputElement[]; // parallel to options, radio-group only
}

export interface FieldResult {
  label: string;
  key: ProfileFieldKey;
}

export interface AutofillResult {
  fieldsOnPage: number; // every fillable input/select/textarea/radio-group discovered on the page
  total: number; // classifiable ("known") fields found on the page
  filled: FieldResult[];
  skipped: FieldResult[]; // classified but not filled (no value on the profile, or no matching option)
}

// One entry per field the heuristic pass left unclassified, keyed by its position in
// discoverFields()'s output — the caller doesn't need to know anything about FieldDescriptor.
export interface UnmatchedFieldForClassifier {
  index: number;
  text: string;
  field_type: string;
  options: string[];
}

// Injected by the caller (AutofillView.tsx owns all chrome.runtime messaging — formFiller.ts stays
// a pure DOM module with no messaging/network concerns of its own, same separation GET_PROFILE_DETAIL
// already follows). Return a Map from field index -> a validated ProfileFieldKey, or null/omitted
// for "no confident match" — autofillForm treats a missing map entry the same as a null one.
export type ClassifyUnmatchedFn = (
  fields: UnmatchedFieldForClassifier[],
) => Promise<Map<number, ProfileFieldKey | null>>;

// Caps how many fields get escalated to the LLM fallback per fill — keeps the batched request
// small/cheap/fast even on an unusually large form, and a form with more than this many genuinely
// ambiguous fields is an edge case not worth optimizing for yet.
const MAX_FIELDS_FOR_CLASSIFIER = 40;

const FILLED_OUTLINE = "2px solid #1a7a3c";
const EXCLUDED_INPUT_TYPES = new Set(["hidden", "submit", "button", "reset", "image", "file", "password", "range", "color"]);
const SUBJECTIVE_HINTS = ["describe", "tell us", "tell me", "explain", "why do you", "why are you", "what is your", "what are your"];

const AUTOCOMPLETE_MAP: Record<string, ProfileFieldKey> = {
  "given-name": "first_name",
  "family-name": "last_name",
  name: "full_name",
  email: "email",
  tel: "phone_number",
  "tel-national": "phone_number",
  organization: "current_employer",
  "organization-title": "current_job_title",
  url: "portfolio_website",
  "address-level2": "current_city",
  "address-level1": "state_province",
  country: "country",
  "country-name": "country",
};

// Order matters: more specific phrases before the generic ones they'd otherwise be swallowed by
// (e.g. "portfolio website" must be checked before personal_website's bare "website").
const LABEL_SYNONYMS: { key: ProfileFieldKey; patterns: string[] }[] = [
  { key: "full_name", patterns: ["full name", "your name", "legal name", "candidate name", "applicant name"] },
  { key: "first_name", patterns: ["first name", "given name", "legal first name", "fname", "forename"] },
  { key: "last_name", patterns: ["last name", "family name", "surname", "legal last name", "lname"] },
  { key: "email", patterns: ["email", "e mail"] },
  {
    key: "phone_number",
    patterns: ["phone", "mobile", "contact number", "telephone", "cell number", "cell phone", "primary number"],
  },
  { key: "current_city", patterns: ["current city", "city", "town"] },
  { key: "state_province", patterns: ["state province", "state", "province", "region"] },
  { key: "country", patterns: ["country of residence", "country"] },
  { key: "linkedin_url", patterns: ["linkedin"] },
  { key: "github_url", patterns: ["github"] },
  { key: "portfolio_website", patterns: ["portfolio"] },
  { key: "personal_website", patterns: ["personal website", "website url", "website", "blog"] },
  {
    key: "work_authorization",
    patterns: [
      "work authorization",
      "work authorisation",
      "visa status",
      "authorized to work",
      "authorised to work",
      "eligible to work",
      "sponsorship",
      "require visa",
    ],
  },
  { key: "willing_to_relocate", patterns: ["willing to relocate", "open to relocation", "relocate", "relocation"] },
  { key: "nationality", patterns: ["nationality", "citizenship"] },
  {
    key: "current_employer",
    patterns: [
      "current employer",
      "current company",
      "employer name",
      "where do you currently work",
      "present employer",
      "company name",
    ],
  },
  {
    key: "current_job_title",
    patterns: ["current job title", "current title", "current position", "current role"],
  },
];

function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function normalizeLabel(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// ---- label resolution ----
// Standard <label> association chain, since real HTML forms (unlike LinkedIn's post cards) usually
// have real labels. Falls back to a structural "nearest preceding text" climb, the same philosophy
// postExtraction.ts uses for LinkedIn's unpredictable markup, for the forms that don't.

function findNearestPrecedingText(el: Element): string {
  let node: Element | null = el;
  let hops = 0;
  while (node && hops < 6) {
    let sibling = node.previousElementSibling;
    while (sibling) {
      if (!sibling.querySelector("input, textarea, select")) {
        const text = normalizeWhitespace(sibling.textContent ?? "");
        if (text && text.length <= 200) return text;
      }
      sibling = sibling.previousElementSibling;
    }
    node = node.parentElement;
    hops += 1;
  }
  return "";
}

// Removes every case-insensitive occurrence of `needle` from `haystack`, preserving the original
// casing of what's left (unlike a toLowerCase()-based split/join, which would lose it).
function stripAllOccurrences(haystack: string, needle: string): string {
  if (!needle) return haystack;
  const lowerNeedle = needle.toLowerCase();
  let result = haystack;
  let idx = result.toLowerCase().indexOf(lowerNeedle);
  while (idx !== -1) {
    result = result.slice(0, idx) + result.slice(idx + needle.length);
    idx = result.toLowerCase().indexOf(lowerNeedle);
  }
  return result;
}

// aria-labelledby before aria-label — matches the WAI-ARIA accessible-name computation's own
// precedence, and matters in practice: Microsoft Forms (and other frameworks) set aria-label to a
// generic type hint ("Single line text", "Single choice") on the question's element while the
// *actual* question text is only reachable via aria-labelledby pointing at separate title/
// description elements elsewhere in the DOM. Those referenced elements are also frequently
// adjacent DOM nodes with no whitespace between them in the markup itself (CSS alone provides the
// visual gap), AND one of them often re-duplicates that same generic hint text — so a question
// numbered "1." titled "Name" can come back as the unreadable "1.NameSingle line text. Single line
// text." with the real title buried inside it. Stripping out the redundant hint text using the
// exact string already given to us via aria-label (rather than guessing at per-framework markup)
// reliably un-garbles the title. Shared by resolveLabel (for an input's own attributes) and
// resolveGroupLabel (for a radio-group container's attributes) — both hit this exact pattern.
function resolveAriaText(el: Element): string {
  const ariaLabelRaw = normalizeWhitespace(el.getAttribute("aria-label") ?? "");
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    let text = labelledBy.split(/\s+/).map((refId) => document.getElementById(refId)?.textContent ?? "").join(" ");
    if (ariaLabelRaw) text = stripAllOccurrences(text, ariaLabelRaw);
    const cleaned = normalizeWhitespace(text);
    if (cleaned) return cleaned;
  }
  return ariaLabelRaw;
}

function resolveLabel(el: Element): string {
  const id = el.getAttribute("id");
  if (id) {
    const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    const text = normalizeWhitespace(label?.textContent ?? "");
    if (text) return text;
  }

  const wrappingLabel = el.closest("label");
  const wrappingText = normalizeWhitespace(wrappingLabel?.textContent ?? "");
  if (wrappingText) return wrappingText;

  const ariaText = resolveAriaText(el);
  if (ariaText) return ariaText;

  const nearby = findNearestPrecedingText(el);
  if (nearby) return nearby;

  const placeholder = normalizeWhitespace((el as HTMLInputElement).placeholder ?? "");
  return placeholder;
}

function resolveGroupLabel(radios: HTMLInputElement[]): string {
  for (const radio of radios) {
    const legend = radio.closest("fieldset")?.querySelector("legend");
    const text = normalizeWhitespace(legend?.textContent ?? "");
    if (text) return text;
  }

  // A radiogroup container's own aria-labelledby/aria-label (when present) names the *question*
  // — e.g. "Are you currently employed?" — whereas each individual radio's own aria-labelledby
  // names its own *option* (e.g. "Yes"). Falling straight to resolveLabel(radios[0]) would pick up
  // the option text instead of the question, so check the container first.
  const container = radios[0].closest('[role="radiogroup"], [role="group"], fieldset');
  const containerAriaText = container ? resolveAriaText(container) : "";
  if (containerAriaText) return containerAriaText;

  return resolveLabel(radios[0]);
}

// ---- matching corpus ----
// Real-world ATS forms (Greenhouse, Workday, Lever, custom React builds) frequently render the
// visible field caption as a plain <div>/<span> with no `<label for>`, `aria-label`, or
// `aria-labelledby` link to the input at all — resolveLabel() falls through to the structural
// "nearest preceding text" guess for these, which is unreliable, or returns "" entirely. But these
// same inputs almost always keep a semantic `name`/`id` (e.g. name="firstName", id="input-email")
// for the framework's own form state, since that's how libraries like Formik/React Hook Form work
// regardless of what's visually rendered. Humanizing those attributes and folding them into the
// matching corpus recovers a large chunk of fields that resolveLabel() alone silently drops.

const GENERATED_ID_PATTERN = /^[a-f0-9]{6,}$/i;
// Generated ids/names are sometimes a single non-hex prefix letter glued onto an otherwise-hex run
// (observed on Microsoft Forms: React-style internal names like "r6a27357d0dce4a1993840dc27f1de872"
// — literally "r" + a GUID with the dashes stripped), which GENERATED_ID_PATTERN alone doesn't
// catch since the leading letter breaks the "all hex" requirement. No real field-name word is ever
// this long, so a length cap catches these regardless of the exact prefixing scheme.
const MAX_IDENTIFIER_WORD_LENGTH = 20;

function humanizeIdentifier(raw: string | null): string {
  if (!raw) return "";
  const spaced = raw
    .replace(/[-_.]/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase();
  const words = spaced
    .split(/\s+/)
    .filter(
      (w) => w.length > 1 && w.length <= MAX_IDENTIFIER_WORD_LENGTH && !/^\d+$/.test(w) && !GENERATED_ID_PATTERN.test(w),
    );
  if (words.length === 0 || words.length > 6) return ""; // empty or too noisy to be a real field name
  return words.join(" ");
}

function capitalize(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

function buildMatchText(...parts: string[]): string {
  return normalizeLabel(parts.filter(Boolean).join(" "));
}

// ---- discovery ----

function isVisible(el: HTMLElement): boolean {
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  return el.getAttribute("aria-hidden") !== "true";
}

function groupRadiosByName(root: ParentNode): HTMLInputElement[][] {
  const radios = Array.from(root.querySelectorAll<HTMLInputElement>('input[type="radio"]')).filter(
    (r) => !r.disabled && isVisible(r) && r.name,
  );
  const groups = new Map<string, HTMLInputElement[]>();
  for (const radio of radios) {
    const group = groups.get(radio.name);
    if (group) group.push(radio);
    else groups.set(radio.name, [radio]);
  }
  return Array.from(groups.values());
}

function describe(
  rawLabel: string,
  name: string,
  id: string,
  placeholder: string,
): { label: string; matchText: string } {
  const nameWords = humanizeIdentifier(name);
  const idWords = humanizeIdentifier(id);
  const label = rawLabel || placeholder || capitalize(nameWords) || capitalize(idWords) || "";
  const matchText = buildMatchText(rawLabel, nameWords, idWords, placeholder);
  return { label, matchText };
}

function discoverFields(root: ParentNode): FieldDescriptor[] {
  const descriptors: FieldDescriptor[] = [];

  for (const radios of groupRadiosByName(root)) {
    const { label, matchText } = describe(resolveGroupLabel(radios), radios[0].name, radios[0].id, "");
    descriptors.push({
      el: radios[0],
      tag: "input",
      type: "radio-group",
      autocomplete: null,
      label,
      matchText,
      maxLength: null,
      options: radios.map((r) => ({ value: r.value, text: resolveLabel(r) })),
      optionElements: radios,
    });
  }

  const elements = Array.from(
    root.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input, textarea, select"),
  );
  for (const el of elements) {
    if (el.disabled || !isVisible(el)) continue;

    if (el instanceof HTMLInputElement) {
      if (el.type === "radio") continue; // handled above as a group
      if (EXCLUDED_INPUT_TYPES.has(el.type)) continue;
      const { label, matchText } = describe(resolveLabel(el), el.name, el.id, el.placeholder);
      descriptors.push({
        el,
        tag: "input",
        type: el.type,
        autocomplete: el.autocomplete || null,
        label,
        matchText,
        maxLength: el.maxLength > 0 ? el.maxLength : null,
      });
      continue;
    }

    if (el instanceof HTMLTextAreaElement) {
      const { label, matchText } = describe(resolveLabel(el), el.name, el.id, el.placeholder);
      descriptors.push({
        el,
        tag: "textarea",
        type: "textarea",
        autocomplete: null,
        label,
        matchText,
        maxLength: el.maxLength > 0 ? el.maxLength : null,
      });
      continue;
    }

    const { label, matchText } = describe(resolveLabel(el), el.name, el.id, "");
    descriptors.push({
      el,
      tag: "select",
      type: "select",
      autocomplete: el.autocomplete || null,
      label,
      matchText,
      maxLength: null,
      options: Array.from(el.options).map((o) => ({ value: o.value, text: o.text })),
    });
  }

  return descriptors;
}

// ---- classification ----

function classifyField(f: FieldDescriptor): ProfileFieldKey | "subjective" | null {
  // <textarea> alone is a reliable "this is an essay question" signal — nobody renders "Name" as a
  // multi-line box. A large maxlength on a single-line <input>, by contrast, is NOT reliable on its
  // own: Microsoft Forms (observed) sets the same generously large maxlength on every "single line
  // text" input regardless of question type, so "Name" and "Describe your biggest challenge" can
  // carry the identical maxlength. Treating that as a trigger by itself silently marked every plain
  // short-answer field on an MS Forms page as "subjective" and skipped it entirely — including from
  // the LLM fallback, since subjective fields are deliberately never escalated to it (Step 2's job).
  // Lexical phrasing (SUBJECTIVE_HINTS, checked next) is the only signal used for <input> now.
  if (f.tag === "textarea") return "subjective";
  const corpus = f.matchText;
  if (SUBJECTIVE_HINTS.some((hint) => corpus.includes(hint))) return "subjective";

  if (f.autocomplete) {
    const mapped = AUTOCOMPLETE_MAP[f.autocomplete.trim().toLowerCase()];
    if (mapped) return mapped;
  }

  if (!corpus) return null;
  for (const { key, patterns } of LABEL_SYNONYMS) {
    if (patterns.some((p) => corpus.includes(p))) return key;
  }
  return null;
}

// ---- resolving a profile value for a classified key ----

function mostRelevantExperience(experiences: ExperienceSummary[]): ExperienceSummary | null {
  if (experiences.length === 0) return null;
  const current = experiences.find((e) => e.currently_working_here);
  if (current) return current;
  return [...experiences].sort((a, b) => (b.start_date ?? "").localeCompare(a.start_date ?? ""))[0];
}

function valueForKey(key: ProfileFieldKey, profile: ProfileDetail): string | boolean | null {
  const info = profile.personal_info;
  switch (key) {
    case "first_name":
      return info.first_name;
    case "last_name":
      return info.last_name;
    case "full_name": {
      const parts = [info.first_name, info.last_name].filter((p): p is string => Boolean(p));
      return parts.length ? parts.join(" ") : null;
    }
    case "email":
      return info.email;
    case "phone_number":
      return info.phone_number;
    case "current_city":
      return info.current_city;
    case "state_province":
      return info.state_province;
    case "country":
      return info.country;
    case "linkedin_url":
      return info.linkedin_url;
    case "github_url":
      return info.github_url;
    case "portfolio_website":
      return info.portfolio_website;
    case "personal_website":
      return info.personal_website;
    case "work_authorization":
      return info.work_authorization;
    case "willing_to_relocate":
      return info.willing_to_relocate;
    case "nationality":
      return info.nationality;
    case "current_employer":
      return mostRelevantExperience(profile.experiences)?.company_name ?? null;
    case "current_job_title":
      return mostRelevantExperience(profile.experiences)?.job_title ?? null;
  }
}

// ---- writing values in ----
// Native property setter + dispatched input/change events — required for React/Vue-controlled
// fields, which ignore a plain `element.value =` assignment (the framework's onChange listener
// never fires, so the value snaps back on the next render).

function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype = el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function fuzzyTextMatch(optionText: string, value: string): boolean {
  const a = normalizeLabel(optionText);
  const b = normalizeLabel(value);
  if (!a || !b) return false;
  return a === b || a.includes(b) || b.includes(a);
}

function fillField(f: FieldDescriptor, rawValue: string | boolean | null): HTMLElement | null {
  if (rawValue === null || rawValue === "") return null;

  if (f.type === "radio-group") {
    if (!f.options || !f.optionElements) return null;
    const target = typeof rawValue === "boolean" ? (rawValue ? "yes" : "no") : rawValue;
    const index = f.options.findIndex((o) => fuzzyTextMatch(o.text, target));
    if (index === -1) return null;
    const radio = f.optionElements[index];
    if (!radio.checked) radio.click();
    return radio;
  }

  if (f.type === "checkbox") {
    if (typeof rawValue !== "boolean") return null;
    const checkbox = f.el as HTMLInputElement;
    if (checkbox.checked !== rawValue) checkbox.click();
    return checkbox;
  }

  // Past this point (select, plain text/textarea inputs) a boolean profile value — e.g.
  // willing_to_relocate — has no native boolean widget to target, so it's expressed as text.
  const value = typeof rawValue === "boolean" ? (rawValue ? "Yes" : "No") : rawValue;

  if (f.tag === "select") {
    const select = f.el as HTMLSelectElement;
    const option = Array.from(select.options).find((o) => fuzzyTextMatch(o.text, value));
    if (!option) return null;
    select.value = option.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return select;
  }

  if (typeof value !== "string") return null;
  setNativeValue(f.el as HTMLInputElement, value);
  return f.el;
}

function markFilled(el: HTMLElement): void {
  el.style.outline = FILLED_OUTLINE;
  el.style.outlineOffset = "1px";
}

// ---- orchestrator ----

export async function autofillForm(profile: ProfileDetail, classifyUnmatched?: ClassifyUnmatchedFn): Promise<AutofillResult> {
  const fields = discoverFields(document);
  const filled: FieldResult[] = [];
  const skipped: FieldResult[] = [];

  // Heuristic pass first (free, synchronous) — classifications[i] is undefined for fields with no
  // matchText at all (nothing to classify against, never escalated), null for fields the heuristics
  // looked at but couldn't confidently map, "subjective" for fields that look like essay/open-ended
  // questions locally (a <textarea>, or open-ended phrasing), or a resolved ProfileFieldKey.
  const classifications = new Map<number, ProfileFieldKey | "subjective" | null>();
  fields.forEach((f, index) => {
    if (f.matchText) classifications.set(index, classifyField(f));
  });

  // Every company phrases the same field differently, and no fixed synonym list covers all of
  // them — escalate whatever's left to the batched LLM fallback, capped to keep the request small.
  // This includes fields the local heuristic guessed "subjective": that guess is often wrong (e.g.
  // a structured multiple-choice question like "Notice Period" isn't an essay question just
  // because it's not in our synonym dictionary), and it's safe to let the backend make the actual
  // call — its output schema is a strict enum of known profile keys, not free text, so worst case
  // it correctly declines an actually-open-ended question exactly like the local guess would have.
  // Best-effort either way: any failure here just leaves those fields unfilled, it never blocks or
  // degrades the heuristic results already computed above.
  if (classifyUnmatched) {
    const unresolved = fields
      .map((f, index) => ({ f, index }))
      .filter(({ index }) => {
        const c = classifications.get(index);
        return c === null || c === "subjective";
      })
      .slice(0, MAX_FIELDS_FOR_CLASSIFIER);

    if (unresolved.length > 0) {
      const toClassify: UnmatchedFieldForClassifier[] = unresolved.map(({ f, index }) => ({
        index,
        text: f.matchText,
        field_type: f.type,
        options: f.options?.map((o) => o.text) ?? [],
      }));
      try {
        const results = await classifyUnmatched(toClassify);
        for (const { index } of unresolved) {
          const key = results.get(index);
          if (isProfileFieldKey(key)) classifications.set(index, key);
        }
      } catch {
        // Network/agent failure — the heuristic-only results stand as-is.
      }
    }
  }

  fields.forEach((f, index) => {
    const classification = classifications.get(index);
    if (!classification || classification === "subjective") return; // unclassified, or Step 2's job

    const value = valueForKey(classification, profile);
    const changedEl = fillField(f, value);
    if (changedEl) {
      markFilled(changedEl);
      filled.push({ label: f.label, key: classification });
    } else {
      skipped.push({ label: f.label, key: classification });
    }
  });

  return { fieldsOnPage: fields.length, total: filled.length + skipped.length, filled, skipped };
}
