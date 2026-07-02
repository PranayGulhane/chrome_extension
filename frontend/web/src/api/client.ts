import { API_BASE_URL } from "./config";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function extractDetail(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  // FastAPI 422 validation errors: detail is a list of {loc, msg, ...}
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return null;
}

// The access token cookie is only good for 15 minutes (see backend/core/config.py). Filling out a
// long profile form easily takes longer than that, and losing the whole form to a raw 401 on save
// is a bad experience — so a 401 triggers one silent refresh-and-retry before giving up. Dedupe
// concurrent refreshes (e.g. two requests both 401'ing around the same moment) into a single call.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh`, { method: "POST", credentials: "include" })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// credentials: 'include' on every request is what makes the httpOnly auth cookies actually get
// sent — without it the browser withholds them even though they're set for this origin.
export async function apiRequest<T>(path: string, init?: RequestInit, isRetry = false): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (res.status === 401 && !isRetry && path !== "/auth/refresh" && path !== "/auth/login") {
    if (await refreshSession()) {
      return apiRequest<T>(path, init, true);
    }
  }

  if (res.status === 204) return undefined as T;

  const body = await res.json().catch(() => undefined);
  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(body) ?? `Request failed with status ${res.status}`);
  }
  return body as T;
}
