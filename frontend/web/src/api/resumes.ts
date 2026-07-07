import { apiRequest, apiUpload } from "./client";
import type { ResumeUploadResponse, ResumeUploadResult } from "./types";

export function uploadResume(profileId: string, file: File): Promise<ResumeUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload<ResumeUploadResult>(`/profiles/${profileId}/resume`, formData);
}

export function getActiveResume(profileId: string): Promise<ResumeUploadResponse> {
  return apiRequest<ResumeUploadResponse>(`/profiles/${profileId}/resume`);
}
