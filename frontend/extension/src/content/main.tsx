import { createRoot } from "react-dom/client";
import { App } from "./App";
import { panelStore } from "./panelStore";
import { PANEL_STYLES } from "./styles";
import type { BackgroundToContentMessage } from "../shared/types";

const HOST_ID = "lja-outreach-extension-root";

function mount(): void {
  const host = document.createElement("div");
  host.id = HOST_ID;
  document.body.appendChild(host);

  // Shadow DOM keeps LinkedIn's CSS out of the panel and the panel's CSS out of LinkedIn — see
  // the PRD's explicit requirement to avoid CSS conflicts.
  const shadowRoot = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = PANEL_STYLES;
  shadowRoot.appendChild(style);

  const container = document.createElement("div");
  shadowRoot.appendChild(container);

  createRoot(container).render(<App />);
}

// LinkedIn is a single-page app — navigating within it (e.g. feed -> search results) often
// happens via client-side routing rather than a full page load. If LinkedIn's router rebuilds
// `<body>`'s subtree during that navigation, our panel host gets silently detached even though
// this content script and its listeners are still running (Chrome doesn't re-inject content
// scripts on same-document navigation, so nothing else would notice). Re-mount whenever the host
// is missing or has fallen out of the live DOM, checked right before every toggle rather than via
// a continuously-running observer — cheap and sufficient since the check only needs to happen at
// the moment the user actually tries to open the panel.
function ensureMounted(): void {
  const existing = document.getElementById(HOST_ID);
  if (existing && document.body.contains(existing)) return;
  existing?.remove(); // stale detached node, if any — drop it before creating a fresh one
  mount();
}

mount();

chrome.runtime.onMessage.addListener((message: BackgroundToContentMessage) => {
  if (message.type === "TOGGLE_PANEL") {
    ensureMounted();
    panelStore.toggle();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") panelStore.close();
});
