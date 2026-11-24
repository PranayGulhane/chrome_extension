import { API_BASE_URL, WEB_APP_URL } from "../shared/config";
import { clearAuthStorage, getAuthStorage, setAuthStorage } from "../shared/storage";
import type {
  ApplicationDetail,
  ArchiveMailRowResponse,
  AuthStateResponse,
  AuthUser,
  BackgroundToContentMessage,
  CheckDuplicateResponse,
  ClassifyFieldsMatch,
  ClassifyFieldsResponse,
  ContentToBackgroundMessage,
  DeleteApplicationResponse,
  DraftEmailResponse,
  DraftFollowupResponse,
  ExtractPostResponse,
  GetMetricsResponse,
  GetProfileDetailResponse,
  GetProfilesResponse,
  GetSentMailPageResponse,
  GmailConnectResponse,
  GmailDisconnectResponse,
  GmailStatusResponse,
  ListApplicationsResponse,
  LoginResponse,
  LogoutResponse,
  MailboxSummary,
  MarkArchivedResponse,
  MarkRepliedResponse,
  MarkSentResponse,
  MarkUnarchivedResponse,
  OpenWebAppResponse,
  PostExtractionResult,
  ProfileDetail,
  ProfileSummary,
  SendEmailResponse,
  SendFollowupResponse,
  SentMailRow,
  UnarchiveMailRowResponse,
  UpdateApplicationResponse,
  UserMetrics,
} from "../shared/types";

// All backend API calls happen here, not in the content script — this is deliberate (see PRD's
// architecture: content script -> background -> FastAPI backend). It keeps host_permissions/CORS
// concerns in one place and gives us one spot to add token-refresh scheduling later.

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

async function fetchJson(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await res.json().catch(() => undefined);
  return { status: res.status, body };
}

async function fetchMe(accessToken: string): Promise<AuthUser | null> {
  const { status, body } = await fetchJson("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return status === 200 ? (body as AuthUser) : null;
}

async function refreshTokens(refreshToken: string): Promise<TokenPair | null> {
  const { status, body } = await fetchJson("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  return status === 200 ? (body as TokenPair) : null;
}

// Generalized authenticated-request helper for any endpoint beyond auth itself (post extraction
// here; drafting/sending/tracker in Features 5-7 reuse this the same way). Attaches the stored
// access token and retries once through /auth/refresh on a 401 — same recovery logic
// getAuthState() already has, just not tied to the auth flow specifically.
async function authorizedFetch(path: string, init?: RequestInit): Promise<{ status: number; body: unknown }> {
  const { access_token, refresh_token } = await getAuthStorage();
  if (!access_token) return { status: 401, body: { detail: "Not signed in" } };

  let attempt = await fetchJson(path, { ...init, headers: { Authorization: `Bearer ${access_token}`, ...init?.headers } });
  if (attempt.status !== 401 || !refresh_token) return attempt;

  const refreshed = await refreshTokens(refresh_token);
  if (!refreshed) {
    await clearAuthStorage();
    return attempt;
  }
  await setAuthStorage(refreshed);
  attempt = await fetchJson(path, {
    ...init,
    headers: { Authorization: `Bearer ${refreshed.access_token}`, ...init?.headers },
  });
  return attempt;
}

async function extractPost(payload: ContentToBackgroundMessage & { type: "EXTRACT_POST" }): Promise<ExtractPostResponse> {
  const { status, body } = await authorizedFetch("/applications/extract", {
    method: "POST",
    body: JSON.stringify(payload.payload),
  });
  if (status !== 201) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Post extraction failed";
    return { ok: false, error: detail };
  }
  return { ok: true, result: body as PostExtractionResult };
}

async function updateApplication(
  message: ContentToBackgroundMessage & { type: "UPDATE_APPLICATION" },
): Promise<UpdateApplicationResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}`, {
    method: "PATCH",
    body: JSON.stringify({
      parsed_email: message.email ?? null,
      post_url: message.postUrl ?? null,
      drafted_email: message.draftedEmail ?? null,
      outreach_type: message.outreachType ?? null,
      outreach_note: message.outreachNote ?? null,
    }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not save that";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function getProfiles(): Promise<GetProfilesResponse> {
  const { status, body } = await authorizedFetch("/profiles");
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not load your profiles";
    return { ok: false, error: detail };
  }
  return { ok: true, profiles: body as ProfileSummary[] };
}

async function getProfileDetail(
  message: ContentToBackgroundMessage & { type: "GET_PROFILE_DETAIL" },
): Promise<GetProfileDetailResponse> {
  const { status, body } = await authorizedFetch(`/profiles/${message.profileId}`);
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not load that profile";
    return { ok: false, error: detail };
  }
  return { ok: true, profile: body as ProfileDetail };
}

async function classifyFields(
  message: ContentToBackgroundMessage & { type: "CLASSIFY_FIELDS" },
): Promise<ClassifyFieldsResponse> {
  const { status, body } = await authorizedFetch("/profiles/classify-fields", {
    method: "POST",
    body: JSON.stringify({ fields: message.fields }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not classify these fields";
    return { ok: false, error: detail };
  }
  return { ok: true, matches: (body as { matches: ClassifyFieldsMatch[] }).matches };
}

async function draftEmail(message: ContentToBackgroundMessage & { type: "DRAFT_EMAIL" }): Promise<DraftEmailResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/draft`, {
    method: "POST",
    body: JSON.stringify({ profile_id: message.profileId }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not draft an email for this post";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function getGmailStatus(): Promise<GmailStatusResponse> {
  const { status, body } = await authorizedFetch("/gmail/status");
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not check Gmail status";
    return { ok: false, error: detail };
  }
  return { ok: true, status: body as { connected: boolean; gmail_address: string | null } };
}

async function connectGmail(): Promise<GmailConnectResponse> {
  const { status, body } = await authorizedFetch("/gmail/oauth/start", { method: "POST" });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not start Gmail connection";
    return { ok: false, error: detail };
  }
  const { authorize_url } = body as { authorize_url: string };
  await chrome.tabs.create({ url: authorize_url });
  return { ok: true };
}

async function disconnectGmail(): Promise<GmailDisconnectResponse> {
  const { status, body } = await authorizedFetch("/gmail/disconnect", { method: "POST" });
  if (status !== 204) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not disconnect Gmail";
    return { ok: false, error: detail };
  }
  return { ok: true };
}

async function sendEmail(message: ContentToBackgroundMessage & { type: "SEND_EMAIL" }): Promise<SendEmailResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/send`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not send this email";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function listApplications(): Promise<ListApplicationsResponse> {
  const { status, body } = await authorizedFetch("/applications");
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not load your application history";
    return { ok: false, error: detail };
  }
  return { ok: true, applications: body as ApplicationDetail[] };
}

async function markSent(message: ContentToBackgroundMessage & { type: "MARK_SENT" }): Promise<MarkSentResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/mark-sent`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not mark this as sent";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function markReplied(
  message: ContentToBackgroundMessage & { type: "MARK_REPLIED" },
): Promise<MarkRepliedResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/mark-replied`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not mark this as replied";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function getMetrics(): Promise<GetMetricsResponse> {
  const { status, body } = await authorizedFetch("/metrics/me");
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not load your usage metrics";
    return { ok: false, error: detail };
  }
  return { ok: true, metrics: body as UserMetrics };
}

async function openWebApp(message: ContentToBackgroundMessage & { type: "OPEN_WEB_APP" }): Promise<OpenWebAppResponse> {
  // Content scripts can't call chrome.tabs.create themselves — same reason connectGmail routes
  // its consent-tab opening through the background worker. path defaults to "" (today's plain
  // "open the app" behavior) — Feature 11 passes e.g. "/tracker/{id}" to deep-link a specific record.
  await chrome.tabs.create({ url: `${WEB_APP_URL}${message.path ?? ""}` });
  return { ok: true };
}

async function checkDuplicateRecipient(
  message: ContentToBackgroundMessage & { type: "CHECK_DUPLICATE_RECIPIENT" },
): Promise<CheckDuplicateResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/duplicate-check`);
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not check for a duplicate recipient";
    return { ok: false, error: detail };
  }
  const result = body as {
    is_duplicate: boolean;
    matched_via: "email" | "poster_profile_url" | null;
    existing_application: ApplicationDetail | null;
  };
  return {
    ok: true,
    is_duplicate: result.is_duplicate,
    matched_via: result.matched_via,
    existing_application: result.existing_application,
  };
}

async function markArchived(
  message: ContentToBackgroundMessage & { type: "MARK_ARCHIVED" },
): Promise<MarkArchivedResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/archive`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not archive this application";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function markUnarchived(
  message: ContentToBackgroundMessage & { type: "MARK_UNARCHIVED" },
): Promise<MarkUnarchivedResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}/unarchive`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not unarchive this application";
    return { ok: false, error: detail };
  }
  return { ok: true, application: body as ApplicationDetail };
}

async function deleteApplication(
  message: ContentToBackgroundMessage & { type: "DELETE_APPLICATION" },
): Promise<DeleteApplicationResponse> {
  const { status, body } = await authorizedFetch(`/applications/${message.applicationId}`, { method: "DELETE" });
  if (status !== 204) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not discard this application";
    return { ok: false, error: detail };
  }
  return { ok: true };
}

async function getSentMailPage(
  message: ContentToBackgroundMessage & { type: "GET_SENT_MAIL_PAGE" },
): Promise<GetSentMailPageResponse> {
  const { status, body } = await authorizedFetch("/mailbox/sent", {
    method: "POST",
    body: JSON.stringify({
      page_size: message.pageSize,
      page_token: message.pageToken ?? null,
      date_from: message.dateFrom ?? null,
      date_to: message.dateTo ?? null,
    }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not load your sent mail";
    return { ok: false, error: detail };
  }
  const result = body as { rows: SentMailRow[]; next_page_token: string | null; summary: MailboxSummary };
  return { ok: true, rows: result.rows, nextPageToken: result.next_page_token, summary: result.summary };
}

async function draftFollowup(
  message: ContentToBackgroundMessage & { type: "DRAFT_FOLLOWUP" },
): Promise<DraftFollowupResponse> {
  const { status, body } = await authorizedFetch(`/mailbox/${message.gmailSentMessageId}/followup/draft`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not draft a follow-up for this email";
    return { ok: false, error: detail };
  }
  const result = body as { subject: string; body: string; grounding: "full" | "subject_only" };
  return { ok: true, subject: result.subject, body: result.body, grounding: result.grounding };
}

async function sendFollowup(
  message: ContentToBackgroundMessage & { type: "SEND_FOLLOWUP" },
): Promise<SendFollowupResponse> {
  const { status, body } = await authorizedFetch(`/mailbox/${message.gmailSentMessageId}/followup/send`, {
    method: "POST",
    body: JSON.stringify({ subject: message.subject, body: message.body }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not send this follow-up";
    return { ok: false, error: detail };
  }
  return { ok: true, row: body as SentMailRow };
}

async function archiveMailRow(
  message: ContentToBackgroundMessage & { type: "ARCHIVE_MAIL_ROW" },
): Promise<ArchiveMailRowResponse> {
  const { status, body } = await authorizedFetch(`/mailbox/${message.gmailSentMessageId}/archive`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not archive this row";
    return { ok: false, error: detail };
  }
  return { ok: true, row: body as SentMailRow };
}

async function unarchiveMailRow(
  message: ContentToBackgroundMessage & { type: "UNARCHIVE_MAIL_ROW" },
): Promise<UnarchiveMailRowResponse> {
  const { status, body } = await authorizedFetch(`/mailbox/${message.gmailSentMessageId}/unarchive`, {
    method: "POST",
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Could not unarchive this row";
    return { ok: false, error: detail };
  }
  return { ok: true, row: body as SentMailRow };
}

async function getAuthState(): Promise<AuthStateResponse> {
  const { access_token, refresh_token } = await getAuthStorage();
  if (!access_token) return { authenticated: false };

  let user = await fetchMe(access_token);
  if (!user && refresh_token) {
    const refreshed = await refreshTokens(refresh_token);
    if (refreshed) {
      await setAuthStorage(refreshed);
      user = await fetchMe(refreshed.access_token);
    }
  }

  if (!user) {
    await clearAuthStorage();
    return { authenticated: false };
  }
  await setAuthStorage({ user });
  return { authenticated: true, user };
}

async function login(email: string, password: string): Promise<LoginResponse> {
  const { status, body } = await fetchJson("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (status !== 200) {
    const detail = (body as { detail?: string } | undefined)?.detail ?? "Login failed";
    return { ok: false, error: detail };
  }

  const tokens = body as TokenPair;
  const user = await fetchMe(tokens.access_token);
  if (!user) {
    return { ok: false, error: "Logged in but could not load account details" };
  }
  await setAuthStorage({ ...tokens, user });
  return { ok: true, user };
}

async function logout(): Promise<LogoutResponse> {
  await clearAuthStorage();
  return { ok: true };
}

function handleMessage(message: ContentToBackgroundMessage) {
  switch (message.type) {
    case "GET_AUTH_STATE":
      return getAuthState();
    case "LOGIN":
      return login(message.email, message.password);
    case "LOGOUT":
      return logout();
    case "EXTRACT_POST":
      return extractPost(message);
    case "UPDATE_APPLICATION":
      return updateApplication(message);
    case "GET_PROFILES":
      return getProfiles();
    case "GET_PROFILE_DETAIL":
      return getProfileDetail(message);
    case "CLASSIFY_FIELDS":
      return classifyFields(message);
    case "DRAFT_EMAIL":
      return draftEmail(message);
    case "GMAIL_STATUS":
      return getGmailStatus();
    case "GMAIL_CONNECT":
      return connectGmail();
    case "GMAIL_DISCONNECT":
      return disconnectGmail();
    case "SEND_EMAIL":
      return sendEmail(message);
    case "LIST_APPLICATIONS":
      return listApplications();
    case "MARK_SENT":
      return markSent(message);
    case "MARK_REPLIED":
      return markReplied(message);
    case "GET_METRICS":
      return getMetrics();
    case "OPEN_WEB_APP":
      return openWebApp(message);
    case "MARK_ARCHIVED":
      return markArchived(message);
    case "MARK_UNARCHIVED":
      return markUnarchived(message);
    case "CHECK_DUPLICATE_RECIPIENT":
      return checkDuplicateRecipient(message);
    case "DELETE_APPLICATION":
      return deleteApplication(message);
    case "GET_SENT_MAIL_PAGE":
      return getSentMailPage(message);
    case "DRAFT_FOLLOWUP":
      return draftFollowup(message);
    case "SEND_FOLLOWUP":
      return sendFollowup(message);
    case "ARCHIVE_MAIL_ROW":
      return archiveMailRow(message);
    case "UNARCHIVE_MAIL_ROW":
      return unarchiveMailRow(message);
  }
}

chrome.runtime.onMessage.addListener((message: ContentToBackgroundMessage, _sender, sendResponse) => {
  handleMessage(message)
    .then(sendResponse)
    .catch((error) => {
      // Without this, a thrown error (e.g. the backend being unreachable) leaves sendResponse
      // uncalled and the content script's chrome.runtime.sendMessage promise pending forever —
      // the panel gets stuck showing "Loading…" with no way out short of reopening it.
      const detail = error instanceof Error ? error.message : "Something went wrong talking to the backend";
      sendResponse({ ok: false, error: detail, authenticated: false });
    });
  return true; // keep the message channel open for the async response above
});

async function toggleActiveTabPanel(): Promise<void> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return;
  const message: BackgroundToContentMessage = { type: "TOGGLE_PANEL" };
  try {
    await chrome.tabs.sendMessage(tab.id, message);
  } catch {
    // No content script listening on this tab yet — either it's not linkedin.com (where the
    // static content_scripts entry doesn't apply) or a fresh navigation wiped a prior on-demand
    // injection. Inject the same bundle on demand: the command/action-click that got us here is
    // itself the user gesture that makes `activeTab` grant temporary access to this one tab, which
    // `scripting.executeScript` then uses — no persistent host_permissions needed for arbitrary sites.
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      await chrome.tabs.sendMessage(tab.id, message);
    } catch {
      // Not injectable here (chrome://, the Web Store, etc.) — nothing to do.
    }
  }
}

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-panel") void toggleActiveTabPanel();
});

chrome.action.onClicked.addListener(() => void toggleActiveTabPanel());
