import { apiRequest } from "./client";
import type { ApplicationResponse } from "./types";

export function listApplications(): Promise<ApplicationResponse[]> {
  return apiRequest<ApplicationResponse[]>("/applications");
}

export function getApplication(id: string): Promise<ApplicationResponse> {
  return apiRequest<ApplicationResponse>(`/applications/${id}`);
}

export function markSent(id: string): Promise<ApplicationResponse> {
  return apiRequest<ApplicationResponse>(`/applications/${id}/mark-sent`, { method: "POST" });
}

export function markReplied(id: string): Promise<ApplicationResponse> {
  return apiRequest<ApplicationResponse>(`/applications/${id}/mark-replied`, { method: "POST" });
}

export function archiveApplication(id: string): Promise<ApplicationResponse> {
  return apiRequest<ApplicationResponse>(`/applications/${id}/archive`, { method: "POST" });
}

export function unarchiveApplication(id: string): Promise<ApplicationResponse> {
  return apiRequest<ApplicationResponse>(`/applications/${id}/unarchive`, { method: "POST" });
}
