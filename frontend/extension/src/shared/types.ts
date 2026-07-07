export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "jobseeker";
}

// Mirrors backend applications/schemas.py::PostExtractionRequest field-for-field (snake_case kept
// as-is rather than transformed, since this is sent straight through to the API).
export interface PostExtractionRequest {
  poster_name: string;
  poster_profile_url: string;
  poster_headline: string | null;
  post_content: string;
  post_url: string;
  post_timestamp: string | null;
  was_truncated: boolean;
}

// Mirrors backend applications/schemas.py::ApplicationResponse.
export interface ApplicationDetail {
  id: string;
  user_id: string;
  profile_id: string | null;
  poster_name: string;
  poster_profile_url: string;
  poster_headline: string | null;
  post_url: string;
  post_timestamp: string | null;
  post_snippet: string;
  was_truncated: boolean;
  company: string | null;
  job_title: string | null;
  skills: string[];
  seniority: string | null;
  location: string | null;
  parsed_email: string | null;
  outreach_type: string | null;
  outreach_note: string | null;
  drafted_email: { subject: string; body: string } | null;
  final_email_sent: string | null;
  resume_upload_id: string | null;
  relevance_score: number | null;
  relevance_reasoning: string | null;
  is_archived: boolean;
  status: string;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

// Mirrors backend profiles/schemas.py::ProfileSummaryResponse (only the fields the panel needs).
export interface ProfileSummary {
  id: string;
  target_job_title: string;
  is_default: boolean;
}

// Mirrors backend applications/schemas.py::PostExtractionResponse.
export interface PostExtractionResult {
  application: ApplicationDetail;
  is_hiring: boolean;
}

// Mirrors backend gmail/schemas.py::GmailStatusResponse.
export interface GmailStatus {
  connected: boolean;
  gmail_address: string | null;
}

// Mirrors backend metrics/schemas.py::AgentTokenBreakdown.
export interface AgentTokenBreakdown {
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
}

// Mirrors backend metrics/schemas.py::UserMetricsResponse.
export interface UserMetrics {
  total_applications: number;
  total_applications_this_month: number;
  emails_sent: number;
  drafted_not_sent: number;
  applications_by_status: Record<string, number>;
  most_used_profile: string | null;
  tokens_today: AgentTokenBreakdown[];
  tokens_this_month: AgentTokenBreakdown[];
}

// Content script -> background service worker (request/response via chrome.runtime.sendMessage).
export type ContentToBackgroundMessage =
  | { type: "GET_AUTH_STATE" }
  | { type: "LOGIN"; email: string; password: string }
  | { type: "LOGOUT" }
  | { type: "EXTRACT_POST"; payload: PostExtractionRequest }
  | {
      type: "UPDATE_APPLICATION";
      applicationId: string;
      email?: string;
      postUrl?: string;
      draftedEmail?: { subject: string; body: string };
      outreachType?: string;
      outreachNote?: string;
    }
  | { type: "GET_PROFILES" }
  | { type: "DRAFT_EMAIL"; applicationId: string; profileId: string }
  | { type: "GMAIL_STATUS" }
  | { type: "GMAIL_CONNECT" }
  | { type: "GMAIL_DISCONNECT" }
  | { type: "SEND_EMAIL"; applicationId: string }
  | { type: "LIST_APPLICATIONS" }
  | { type: "MARK_SENT"; applicationId: string }
  | { type: "MARK_REPLIED"; applicationId: string }
  | { type: "GET_METRICS" }
  | { type: "OPEN_WEB_APP"; path?: string }
  | { type: "MARK_ARCHIVED"; applicationId: string }
  | { type: "MARK_UNARCHIVED"; applicationId: string }
  | { type: "CHECK_DUPLICATE_RECIPIENT"; applicationId: string }
  | { type: "DELETE_APPLICATION"; applicationId: string };

export type AuthStateResponse = { authenticated: true; user: AuthUser } | { authenticated: false };
export type LoginResponse = { ok: true; user: AuthUser } | { ok: false; error: string };
export type LogoutResponse = { ok: true };
export type ExtractPostResponse = { ok: true; result: PostExtractionResult } | { ok: false; error: string };
export type UpdateApplicationResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type GetProfilesResponse = { ok: true; profiles: ProfileSummary[] } | { ok: false; error: string };
export type DraftEmailResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type GmailStatusResponse = { ok: true; status: GmailStatus } | { ok: false; error: string };
export type GmailConnectResponse = { ok: true } | { ok: false; error: string };
export type GmailDisconnectResponse = { ok: true } | { ok: false; error: string };
export type SendEmailResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type ListApplicationsResponse =
  | { ok: true; applications: ApplicationDetail[] }
  | { ok: false; error: string };
export type MarkSentResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type MarkRepliedResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type GetMetricsResponse = { ok: true; metrics: UserMetrics } | { ok: false; error: string };
export type OpenWebAppResponse = { ok: true };
export type MarkArchivedResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type MarkUnarchivedResponse = { ok: true; application: ApplicationDetail } | { ok: false; error: string };
export type CheckDuplicateResponse =
  | {
      ok: true;
      is_duplicate: boolean;
      matched_via: "email" | "poster_profile_url" | null;
      existing_application: ApplicationDetail | null;
    }
  | { ok: false; error: string };
export type DeleteApplicationResponse = { ok: true } | { ok: false; error: string };

// Background -> content script (fire-and-forget).
export type BackgroundToContentMessage = { type: "TOGGLE_PANEL" };
