import { apiRequest } from "./client";
import type { InviteCodeResponse } from "./types";

export function createInviteCode(expiresAt?: string): Promise<InviteCodeResponse> {
  return apiRequest<InviteCodeResponse>("/auth/invite-codes", {
    method: "POST",
    body: JSON.stringify({ expires_at: expiresAt ?? null }),
  });
}

export function listInviteCodes(): Promise<InviteCodeResponse[]> {
  return apiRequest<InviteCodeResponse[]>("/auth/invite-codes");
}

export function revokeInviteCode(id: string): Promise<InviteCodeResponse> {
  return apiRequest<InviteCodeResponse>(`/auth/invite-codes/${id}/revoke`, { method: "POST" });
}
