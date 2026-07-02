import { apiRequest } from "./client";
import type { ProfileResponse, ProfileSummaryResponse, ProfileWriteRequest } from "./types";

export function listProfiles(): Promise<ProfileSummaryResponse[]> {
  return apiRequest<ProfileSummaryResponse[]>("/profiles");
}

export function getProfile(id: string): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>(`/profiles/${id}`);
}

export function createProfile(payload: ProfileWriteRequest): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>("/profiles", { method: "POST", body: JSON.stringify(payload) });
}

export function updateProfile(id: string, payload: ProfileWriteRequest): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>(`/profiles/${id}`, { method: "PUT", body: JSON.stringify(payload) });
}

export function deleteProfile(id: string): Promise<void> {
  return apiRequest<void>(`/profiles/${id}`, { method: "DELETE" });
}

export function setDefaultProfile(id: string): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>(`/profiles/${id}/set-default`, { method: "POST" });
}

export function cloneProfile(id: string, targetJobTitle: string): Promise<ProfileResponse> {
  return apiRequest<ProfileResponse>(`/profiles/${id}/clone`, {
    method: "POST",
    body: JSON.stringify({ target_job_title: targetJobTitle }),
  });
}
