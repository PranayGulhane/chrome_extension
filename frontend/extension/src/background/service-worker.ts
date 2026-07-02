import { API_BASE_URL } from "../shared/config";
import { clearAuthStorage, getAuthStorage, setAuthStorage } from "../shared/storage";
import type {
  AuthStateResponse,
  AuthUser,
  BackgroundToContentMessage,
  ContentToBackgroundMessage,
  LoginResponse,
  LogoutResponse,
} from "../shared/types";

// All backend API calls happen here, not in the content script — this is deliberate (see PRD's
// architecture: content script -> background -> FastAPI backend). It keeps host_permissions/CORS
// concerns in one place and gives us one spot to add token-refresh scheduling later.

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

async function fetchJson(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await res.json().catch(() => undefined);
  return { status: res.status, body };
}

async function fetchMe(accessToken: string): Promise<AuthUser | null> {
  const { status, body } = await fetchJson("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return status === 200 ? (body as AuthUser) : null;
}

async function refreshTokens(refreshToken: string): Promise<TokenPair | null> {
  const { status, body } = await fetchJson("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  return status === 200 ? (body as TokenPair) : null;
}

async function getAuthState(): Promise<AuthStateResponse> {
  const { access_token, refresh_token } = await getAuthStorage();
  if (!access_token) return { authenticated: false };

  let user = await fetchMe(access_token);
  if (!user && refresh_token) {
    const refreshed = await refreshTokens(refresh_token);
    if (refreshed) {
      await setAuthStorage(refreshed);
      user = await fetchMe(refreshed.access_token);
    }
  }

  if (!user) {
    await clearAuthStorage();
    return { authenticated: false };
  }
  await setAuthStorage({ user });
  return { authenticated: true, user };
}

async function login(email: string, password: string): Promise<LoginResponse> {
  const { status, body } = await fetchJson("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Login failed";
    return { ok: false, error: detail };
  }

  const tokens = body as TokenPair;
  const user = await fetchMe(tokens.access_token);
  if (!user) {
    return { ok: false, error: "Logged in but could not load account details" };
  }
  await setAuthStorage({ ...tokens, user });
  return { ok: true, user };
}

async function logout(): Promise<LogoutResponse> {
  await clearAuthStorage();
  return { ok: true };
}

function handleMessage(message: ContentToBackgroundMessage) {
  switch (message.type) {
    case "GET_AUTH_STATE":
      return getAuthState();
    case "LOGIN":
      return login(message.email, message.password);
    case "LOGOUT":
      return logout();
  }
}

chrome.runtime.onMessage.addListener((message: ContentToBackgroundMessage, _sender, sendResponse) => {
  handleMessage(message).then(sendResponse);
  return true; // keep the message channel open for the async response above
});

async function toggleActiveTabPanel(): Promise<void> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return;
  const message: BackgroundToContentMessage = { type: "TOGGLE_PANEL" };
  // Rejects if the content script isn't present on this tab (e.g. not a linkedin.com page) —
  // nothing to relay to in that case, so swallow it.
  chrome.tabs.sendMessage(tab.id, message).catch(() => undefined);
}

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-panel") void toggleActiveTabPanel();
});

chrome.action.onClicked.addListener(() => void toggleActiveTabPanel());
