import { createRoot } from "react-dom/client";
import { App } from "./App";
import { panelStore } from "./panelStore";
import { PANEL_STYLES } from "./styles";
import type { BackgroundToContentMessage } from "../shared/types";

const HOST_ID = "lja-outreach-extension-root";

function mount(): void {
  if (document.getElementById(HOST_ID)) return; // already injected (defensive; shouldn't happen for a static content script)

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

mount();

chrome.runtime.onMessage.addListener((message: BackgroundToContentMessage) => {
  if (message.type === "TOGGLE_PANEL") panelStore.toggle();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") panelStore.close();
});
