import type { PostExtractionRequest } from "../shared/types";

// LinkedIn's current build uses hashed/atomic CSS classes (e.g. "_485d57b6") that regenerate on
// every deploy and per-item "componentkey" UUIDs that aren't stable across page loads — neither is
// usable as a fixed selector. So post-card detection is structural instead: a profile link
// (`a[href*="/in/"]`) is a reliable anchor (real, meaningful hrefs), and "one post" is defined as
// the largest ancestor of a click/hover target that still contains exactly one such link — climb
// up until a second one would be included, then stop. See docs/PROGRESS.md's Feature 4 log for the
// live-DOM investigation that led here (confirmed via manual testing, not guessed).
const PROFILE_LINK_SELECTOR = 'a[href*="/in/"]';

// Minimum length for a text block to plausibly be post body copy rather than a name/timestamp/
// connection-degree snippet (all of which are short).
const MIN_BODY_TEXT_LENGTH = 40;

const TIME_PREFIX_PATTERN = /^\d+\s*(mo|yr|min|hr|[mhdw])\b/i;
const DEGREE_PATTERN = /^(1st|2nd|3rd)\+?$/i;

const SEE_MORE_TEXT_PATTERN = /see more/i;
const SEE_MORE_MAX_LENGTH = 20; // avoids matching a long sentence that happens to contain the phrase

// See PRD Open Questions (§20): "no capture proceeds on truncated content" — 800ms is the PRD's
// own specified wait budget for the programmatic "see more" click to take effect.
const SEE_MORE_EXPAND_TIMEOUT_MS = 800;
const SEE_MORE_POLL_INTERVAL_MS = 50;

// Client-side throttle: a concrete guardrail against anything that could look like automated
// rapid-fire extraction, even though the click-driven design already makes that unlikely (see the
// LinkedIn ToS posture notes in the Feature 4 plan).
const SELECTION_THROTTLE_MS = 3000;

export type ExtractionOutcome =
  | { status: "extracted"; data: PostExtractionRequest }
  | { status: "truncated" }
  | { status: "throttled" }
  | { status: "unreadable" };

let active = false;
let hoveredEl: HTMLElement | null = null;
let lastExtractionAt = 0;
let onSelectCallback: ((outcome: ExtractionOutcome) => void) | null = null;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function distinctProfileHrefCount(el: Element): number {
  // A single post's header commonly has *two* separate <a> tags to the same profile (avatar
  // image + name text) — counting raw elements would treat that as "two posts" and stop climbing
  // too early (confirmed via live testing: this is exactly what happened). Count distinct URLs
  // instead, so multiple links to the same person don't falsely end the climb.
  const hrefs = new Set<string>();
  if (el.matches(PROFILE_LINK_SELECTOR)) hrefs.add(normalizeProfileUrl((el as HTMLAnchorElement).href));
  for (const a of el.querySelectorAll<HTMLAnchorElement>(PROFILE_LINK_SELECTOR)) hrefs.add(normalizeProfileUrl(a.href));
  return hrefs.size;
}

function findPostCard(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null;
  let node: Element | null = target;
  let candidate: HTMLElement | null = null;
  while (node && node !== document.body && node !== document.documentElement) {
    const count = distinctProfileHrefCount(node);
    if (count === 1) {
      candidate = node as HTMLElement; // still one post's worth — keep climbing for the full extent
    } else if (count > 1) {
      break; // this ancestor now spans a second distinct person's post — stop
    }
    node = node.parentElement;
  }
  return candidate;
}

function clearHover(): void {
  if (!hoveredEl) return;
  hoveredEl.style.outline = "";
  hoveredEl.style.outlineOffset = "";
  hoveredEl.style.cursor = "";
  hoveredEl = null;
}

function handleMouseOver(e: MouseEvent): void {
  const card = findPostCard(e.target);
  if (card === hoveredEl) return;
  clearHover();
  if (!card) return;
  // Inline style mutation, reverted on mouseout — never touches document.head, so LinkedIn's page
  // never gets a stylesheet injected onto it (same isolation rule as the shadow-root panel CSS).
  card.style.outline = "2px solid #0a5c88";
  card.style.outlineOffset = "-2px";
  card.style.cursor = "pointer";
  hoveredEl = card;
}

function handleMouseOut(e: MouseEvent): void {
  const card = findPostCard(e.target);
  if (!card || card !== hoveredEl) return;
  const relatedNode = e.relatedTarget instanceof Node ? e.relatedTarget : null;
  if (relatedNode && card.contains(relatedNode)) return; // moved to a child, not actually leaving
  clearHover();
}

function normalizeProfileUrl(href: string): string {
  try {
    const url = new URL(href, window.location.origin);
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return href;
  }
}

function firstNonEmptyLine(text: string): string | null {
  return text.split("\n").map((line) => line.trim()).find(Boolean) ?? null;
}

// A profile link's visible text is sometimes a single continuous run rather than separate lines —
// e.g. "Bhawana J.  • 2nd" with no actual newline before the connection degree — so splitting on
// "\n" alone doesn't always isolate the name. Strip a trailing "• 1st/2nd/3rd(+)" suffix
// explicitly (confirmed via live testing to be a reliable, consistently-formatted marker).
function stripConnectionDegree(text: string): string {
  return text.replace(/\s*•?\s*(1st|2nd|3rd)\+?\s*$/i, "").trim();
}

function extractPosterInfo(card: HTMLElement): { name: string; profileUrl: string; headline: string | null } | null {
  // A post header commonly has *two* separate <a> tags to the same profile — an avatar-image link
  // (no visible text) and a name-text link — and they can appear in either order. Taking the first
  // DOM match blindly can land on the empty avatar link and find no name at all (confirmed via
  // live testing). Scan every profile link in the card and use the first one that actually has
  // visible text.
  const candidateLinks = card.matches(PROFILE_LINK_SELECTOR)
    ? [card as HTMLAnchorElement, ...card.querySelectorAll<HTMLAnchorElement>(PROFILE_LINK_SELECTOR)]
    : [...card.querySelectorAll<HTMLAnchorElement>(PROFILE_LINK_SELECTOR)];

  let link: HTMLAnchorElement | null = null;
  let name: string | null = null;
  for (const candidate of candidateLinks) {
    // The link's own text often bundles the name with extra lines (connection degree, blank
    // spacer lines) — e.g. "Bhawana J.\n\n\n• 2nd" — so only the first non-empty line is the name.
    const line = firstNonEmptyLine(candidate.textContent ?? "");
    const text = line ? stripConnectionDegree(line) : null;
    if (text) {
      link = candidate;
      name = text;
      break;
    }
  }
  if (!link || !name) return null;

  // Headline (job title/company under the name) has no stable marker either — best-effort only,
  // and it's an optional field. Look for a short-ish, non-metadata text line near the author link
  // that isn't the name itself.
  let headline: string | null = null;
  const container = link.closest<HTMLElement>("div") ?? card;
  for (const el of container.querySelectorAll<HTMLElement>("[componentkey]")) {
    const text = firstNonEmptyLine(el.innerText ?? "");
    if (!text || text === name || TIME_PREFIX_PATTERN.test(text) || DEGREE_PATTERN.test(text)) continue;
    if (text.length > 3 && text.length < 150) {
      headline = text;
      break;
    }
  }

  return { name, profileUrl: normalizeProfileUrl(link.href), headline };
}

function findPostBody(card: HTMLElement, authorName: string): HTMLElement | null {
  const candidates: HTMLElement[] = [];
  for (const el of card.querySelectorAll<HTMLElement>("[componentkey]")) {
    const text = el.innerText?.trim() ?? "";
    if (text.length < MIN_BODY_TEXT_LENGTH) continue;
    if (text === authorName || TIME_PREFIX_PATTERN.test(text) || DEGREE_PATTERN.test(text)) continue;
    candidates.push(el);
  }
  // An ancestor's innerText always includes every descendant's text, so without this, an outer
  // wrapper spanning "Feed post" label + name + headline + body would always "win" over the
  // actual standalone body element purely by being longer (confirmed via live testing — this is
  // exactly what happened on real posts). Exclude any candidate that contains another candidate,
  // keeping only the innermost (most specific) block for a given piece of text.
  const leafCandidates = candidates.filter((el) => !candidates.some((other) => other !== el && el.contains(other)));

  let best: HTMLElement | null = null;
  let bestLength = 0;
  for (const el of leafCandidates) {
    const length = (el.innerText ?? "").trim().length;
    if (length > bestLength) {
      best = el;
      bestLength = length;
    }
  }
  return best;
}

function findSeeMoreButton(card: HTMLElement): HTMLElement | null {
  for (const el of card.querySelectorAll<HTMLElement>('button, [role="button"], a')) {
    const text = el.innerText?.trim() ?? "";
    if (text.length <= SEE_MORE_MAX_LENGTH && SEE_MORE_TEXT_PATTERN.test(text)) return el;
  }
  return null;
}

async function resolvePostBody(card: HTMLElement, authorName: string): Promise<{ text: string; wasTruncated: boolean }> {
  const before = findPostBody(card, authorName)?.innerText.trim() ?? "";
  const seeMoreBtn = findSeeMoreButton(card);
  if (!seeMoreBtn) return { text: before, wasTruncated: false };

  // A simulated single click on a visible, already-rendered button — equivalent to the user
  // clicking it themselves (PRD §20's own reasoning for why this isn't scraping).
  seeMoreBtn.click();

  const deadline = Date.now() + SEE_MORE_EXPAND_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await sleep(SEE_MORE_POLL_INTERVAL_MS);
    // Re-query rather than reuse a cached element reference — React may replace the subtree
    // rather than mutate it in place after the click.
    const after = findPostBody(card, authorName)?.innerText.trim() ?? "";
    if (after.length > before.length) return { text: after, wasTruncated: false };
  }
  return { text: before, wasTruncated: true };
}

function findTimestampText(card: HTMLElement): string | null {
  for (const el of card.querySelectorAll<HTMLElement>("[componentkey]")) {
    const firstLine = firstNonEmptyLine(el.innerText ?? "");
    if (firstLine && (TIME_PREFIX_PATTERN.test(firstLine) || /^just now$/i.test(firstLine))) return firstLine;
  }
  return null;
}

const RELATIVE_TIME_UNIT_MS: Record<string, number> = {
  m: 60_000,
  min: 60_000,
  h: 3_600_000,
  hr: 3_600_000,
  d: 86_400_000,
  w: 7 * 86_400_000,
  mo: 30 * 86_400_000,
  yr: 365 * 86_400_000,
};

function parseRelativeTimestamp(text: string): string | null {
  if (/^just now$/i.test(text)) return new Date().toISOString();
  const match = text.match(/^(\d+)\s*(mo|yr|min|hr|[mhdw])\b/i);
  if (!match) return null;
  const amount = Number.parseInt(match[1], 10);
  const ms = RELATIVE_TIME_UNIT_MS[match[2].toLowerCase()];
  if (!ms) return null;
  // Best-effort only — LinkedIn's DOM only exposes relative text ("4w", "2h"), not an absolute
  // timestamp, in this markup. Precision degrades the staler the relative label is.
  return new Date(Date.now() - amount * ms).toISOString();
}

async function extractFromCard(card: HTMLElement): Promise<ExtractionOutcome> {
  const posterInfo = extractPosterInfo(card);
  if (!posterInfo) return { status: "unreadable" };

  // Per PRD §20's resolved "see more" question: if expansion doesn't complete in time, no
  // extraction/API call happens at all — the caller shows a retry prompt instead.
  const body = await resolvePostBody(card, posterInfo.name);
  if (body.wasTruncated) return { status: "truncated" };
  if (!body.text) return { status: "unreadable" };

  const timestampText = findTimestampText(card);

  return {
    status: "extracted",
    data: {
      poster_name: posterInfo.name,
      poster_profile_url: posterInfo.profileUrl,
      poster_headline: posterInfo.headline,
      post_content: body.text,
      // No stable permalink source found on the search-results page markup investigated so far
      // (no data-urn, no direct /feed/update/ href) — falls back to the current page URL. Revisit
      // if a "copy link" menu action turns out to expose the real permalink via some attribute.
      post_url: window.location.href,
      post_timestamp: timestampText ? parseRelativeTimestamp(timestampText) : null,
      was_truncated: false,
    },
  };
}

function handleClick(e: MouseEvent): void {
  const card = findPostCard(e.target);
  if (!card) return;
  // LinkedIn post clicks normally navigate to the post's own page — suppress that while in
  // selection mode, since selecting is the action here, not navigating.
  e.preventDefault();
  e.stopPropagation();

  if (Date.now() - lastExtractionAt < SELECTION_THROTTLE_MS) {
    onSelectCallback?.({ status: "throttled" });
    return;
  }

  void extractFromCard(card).then((outcome) => {
    if (outcome.status === "extracted") lastExtractionAt = Date.now();
    onSelectCallback?.(outcome);
  });
}

export function startSelectionMode(onSelect: (outcome: ExtractionOutcome) => void): void {
  if (active) return;
  active = true;
  onSelectCallback = onSelect;
  // Event delegation on `document` (capture phase, so it runs before LinkedIn's own click
  // handlers) rather than per-post listeners — this already covers infinite-scroll/newly-rendered
  // posts for free, so no MutationObserver is needed.
  document.addEventListener("mouseover", handleMouseOver, true);
  document.addEventListener("mouseout", handleMouseOut, true);
  document.addEventListener("click", handleClick, true);
}

export function stopSelectionMode(): void {
  if (!active) return;
  active = false;
  onSelectCallback = null;
  clearHover();
  document.removeEventListener("mouseover", handleMouseOver, true);
  document.removeEventListener("mouseout", handleMouseOut, true);
  document.removeEventListener("click", handleClick, true);
}
