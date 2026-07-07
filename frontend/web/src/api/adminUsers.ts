import { apiRequest } from "./client";
import type { AdminUserAccessUpdateRequest, AuthUser } from "./types";

export function revokeUserAccess(id: string): Promise<AuthUser> {
  return apiRequest<AuthUser>(`/admin/users/${id}/revoke-access`, { method: "POST" });
}

export function restoreUserAccess(id: string): Promise<AuthUser> {
  return apiRequest<AuthUser>(`/admin/users/${id}/restore-access`, { method: "POST" });
}

export function updateUserAccess(id: string, payload: AdminUserAccessUpdateRequest): Promise<AuthUser> {
  return apiRequest<AuthUser>(`/admin/users/${id}/access`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
