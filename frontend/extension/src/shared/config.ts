// TODO: point at the deployed backend once one exists (and add its origin to
// public/manifest.json's host_permissions — the dev localhost entry alone won't cover it).
export const API_BASE_URL = "http://127.0.0.1:8123";

// TODO: point at the deployed Web SPA once one exists. Opened in a new tab (chrome.tabs.create),
// not fetched, so this doesn't need a host_permissions entry — it's a top-level navigation, same
// as the Gmail OAuth consent tab.
export const WEB_APP_URL = "http://localhost:5173";
