import type { AuthUser } from "./types";

interface AuthStorage {
  access_token?: string;
  refresh_token?: string;
  user?: AuthUser;
}

const KEYS = ["access_token", "refresh_token", "user"] as const;

export async function getAuthStorage(): Promise<AuthStorage> {
  return (await chrome.storage.local.get(KEYS)) as AuthStorage;
}

export async function setAuthStorage(value: AuthStorage): Promise<void> {
  await chrome.storage.local.set(value);
}

export async function clearAuthStorage(): Promise<void> {
  await chrome.storage.local.remove(KEYS);
}
