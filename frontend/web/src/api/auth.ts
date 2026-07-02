import { apiRequest } from "./client";
import type { AuthUser } from "./types";

export function login(email: string, password: string): Promise<AuthUser> {
  return apiRequest<void>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }).then(me);
}

export function signup(email: string, password: string, inviteCode: string): Promise<AuthUser> {
  return apiRequest<void>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, invite_code: inviteCode }),
  }).then(me);
}

export function logout(): Promise<void> {
  return apiRequest<void>("/auth/logout", { method: "POST" });
}

export function me(): Promise<AuthUser> {
  return apiRequest<AuthUser>("/auth/me");
}
