export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "jobseeker";
}

// Content script -> background service worker (request/response via chrome.runtime.sendMessage).
export type ContentToBackgroundMessage =
  | { type: "GET_AUTH_STATE" }
  | { type: "LOGIN"; email: string; password: string }
  | { type: "LOGOUT" };

export type AuthStateResponse = { authenticated: true; user: AuthUser } | { authenticated: false };
export type LoginResponse = { ok: true; user: AuthUser } | { ok: false; error: string };
export type LogoutResponse = { ok: true };

// Background -> content script (fire-and-forget).
export type BackgroundToContentMessage = { type: "TOGGLE_PANEL" };
