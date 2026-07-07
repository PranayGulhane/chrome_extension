import { apiRequest } from "./client";
import type { AdminOverviewResponse, AdminUserRow, UserMetricsResponse } from "./types";

export function getUserMetrics(): Promise<UserMetricsResponse> {
  return apiRequest<UserMetricsResponse>("/metrics/me");
}

export function getAdminOverview(): Promise<AdminOverviewResponse> {
  return apiRequest<AdminOverviewResponse>("/admin/overview");
}

export function getAdminUsers(): Promise<AdminUserRow[]> {
  return apiRequest<AdminUserRow[]>("/admin/users");
}
