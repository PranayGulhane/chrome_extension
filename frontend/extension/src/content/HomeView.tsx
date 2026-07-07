import { useEffect, useState } from "react";
import { startSelectionMode, stopSelectionMode } from "./postExtraction";
import type { ExtractionOutcome } from "./postExtraction";
import type {
  ApplicationDetail,
  CheckDuplicateResponse,
  ContentToBackgroundMessage,
  DeleteApplicationResponse,
  DraftEmailResponse,
  ExtractPostResponse,
  GetProfilesResponse,
  GmailConnectResponse,
  GmailStatus,
  GmailStatusResponse,
  MarkSentResponse,
  PostExtractionResult,
  ProfileSummary,
  SendEmailResponse,
  UpdateApplicationResponse,
} from "../shared/types";

type OutreachChoice = "email" | "linkedin_dm" | "apply_via_link" | "reach_out_other";

type HomeState =
  | { kind: "idle" }
  | { kind: "notice"; message: string }
  | { kind: "loading" }
  | { kind: "result"; result: PostExtractionResult }
  | { kind: "error"; message: string };

export function HomeView() {
  const [state, setState] = useState<HomeState>({ kind: "idle" });

  useEffect(() => {
    // Selection mode only runs while idle/notice — paused during loading (so a second click can't
    // fire mid-request) and once a result is shown (resumed via "Select another post").
    if (state.kind !== "idle" && state.kind !== "notice") {
      stopSelectionMode();
      return undefined;
    }

    startSelectionMode((outcome: ExtractionOutcome) => {
      if (outcome.status === "extracted") {
        setState({ kind: "loading" });
        const message: ContentToBackgroundMessage = { type: "EXTRACT_POST", payload: outcome.data };
        chrome.runtime.sendMessage(message).then((response: ExtractPostResponse) => {
          setState(response.ok ? { kind: "result", result: response.result } : { kind: "error", message: response.error });
        });
        return;
      }
      if (outcome.status === "truncated") {
        setState({
          kind: "notice",
          message: 'This post looks truncated — click "…see more" on the post to expand it, then click the post again.',
        });
        return;
      }
      if (outcome.status === "throttled") {
        setState({ kind: "notice", message: "One moment — please wait a few seconds between selections." });
        return;
      }
      setState({ kind: "notice", message: "Couldn't read that post — try clicking directly on its text." });
    });

    return () => stopSelectionMode();
  }, [state.kind]);

  if (state.kind === "loading") {
    return <p className="muted">Analysing post…</p>;
  }

  if (state.kind === "result") {
    return <ExtractionResult result={state.result} onSelectAnother={() => setState({ kind: "idle" })} />;
  }

  if (state.kind === "error") {
    return (
      <div>
        <p className="error-text">{state.message}</p>
        <button className="btn-secondary" onClick={() => setState({ kind: "idle" })}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div>
      <p className="muted">Click a hiring post on the page to extract it.</p>
      {state.kind === "notice" && <p className="notice-text">{state.message}</p>}
    </div>
  );
}

function ExtractionResult({
  result,
  onSelectAnother,
}: {
  result: PostExtractionResult;
  onSelectAnother: () => void;
}) {
  const { application, is_hiring } = result;
  const [manualEmail, setManualEmail] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  const [savedEmail, setSavedEmail] = useState(application.parsed_email);
  const [emailError, setEmailError] = useState<string | null>(null);

  const [outreachType, setOutreachType] = useState(application.outreach_type);
  const [outreachNote, setOutreachNote] = useState(application.outreach_note);
  const [picker, setPicker] = useState<OutreachChoice | null>(null);

  const [postUrlInput, setPostUrlInput] = useState(application.post_url);
  const [savedPostUrl, setSavedPostUrl] = useState(application.post_url);
  const [savingLink, setSavingLink] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Feature 11: checked right after extraction (not at send time) so the user can decide whether
  // to bother drafting at all, before investing any effort — matches on poster_profile_url
  // (always known immediately) or parsed_email (once JD parsing finds one).
  const [duplicate, setDuplicate] = useState<{
    existing: ApplicationDetail;
    matchedVia: "email" | "poster_profile_url" | null;
  } | null>(null);
  const [showDuplicateDetail, setShowDuplicateDetail] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [discardError, setDiscardError] = useState<string | null>(null);

  useEffect(() => {
    async function checkDuplicate() {
      const message: ContentToBackgroundMessage = {
        type: "CHECK_DUPLICATE_RECIPIENT",
        applicationId: application.id,
      };
      const response = (await chrome.runtime.sendMessage(message)) as CheckDuplicateResponse;
      if (response.ok && response.is_duplicate && response.existing_application) {
        setDuplicate({ existing: response.existing_application, matchedVia: response.matched_via });
      }
    }
    void checkDuplicate();
  }, [application.id]);

  async function handleDiscard() {
    setDiscarding(true);
    setDiscardError(null);
    const message: ContentToBackgroundMessage = { type: "DELETE_APPLICATION", applicationId: application.id };
    const response = (await chrome.runtime.sendMessage(message)) as DeleteApplicationResponse;
    setDiscarding(false);
    if (!response.ok) {
      setDiscardError(response.error);
      return;
    }
    onSelectAnother();
  }

  async function handleSaveEmail(e: React.FormEvent) {
    e.preventDefault();
    setSavingEmail(true);
    setEmailError(null);
    const message: ContentToBackgroundMessage = {
      type: "UPDATE_APPLICATION",
      applicationId: application.id,
      email: manualEmail,
    };
    const response = (await chrome.runtime.sendMessage(message)) as UpdateApplicationResponse;
    setSavingEmail(false);
    if (response.ok) {
      setSavedEmail(response.application.parsed_email);
      setOutreachType(response.application.outreach_type);
    } else {
      setEmailError(response.error);
    }
  }

  const [savingOutreach, setSavingOutreach] = useState(false);
  const [outreachNoteInput, setOutreachNoteInput] = useState("");
  const [outreachError, setOutreachError] = useState<string | null>(null);

  async function handleSaveOutreach(choice: Exclude<OutreachChoice, "email">, note: string | null) {
    setSavingOutreach(true);
    setOutreachError(null);
    const message: ContentToBackgroundMessage = {
      type: "UPDATE_APPLICATION",
      applicationId: application.id,
      outreachType: choice,
      outreachNote: note ?? undefined,
    };
    const response = (await chrome.runtime.sendMessage(message)) as UpdateApplicationResponse;
    setSavingOutreach(false);
    if (response.ok) {
      setOutreachType(response.application.outreach_type);
      setOutreachNote(response.application.outreach_note);
    } else {
      setOutreachError(response.error);
    }
  }

  async function handleSaveLink(e: React.FormEvent) {
    e.preventDefault();
    setSavingLink(true);
    setLinkError(null);
    const message: ContentToBackgroundMessage = {
      type: "UPDATE_APPLICATION",
      applicationId: application.id,
      postUrl: postUrlInput,
    };
    const response = (await chrome.runtime.sendMessage(message)) as UpdateApplicationResponse;
    setSavingLink(false);
    if (response.ok) {
      setSavedPostUrl(response.application.post_url);
      setPostUrlInput(response.application.post_url);
    } else {
      setLinkError(response.error);
    }
  }

  return (
    <div>
      {!is_hiring && <p className="notice-text">This doesn't look like a hiring post — you can still proceed.</p>}
      {application.was_truncated && <p className="notice-text">Only partial post text was captured.</p>}

      {duplicate && (
        <div className="notice-text">
          <p style={{ margin: "0 0 8px" }}>
            You already contacted{" "}
            {duplicate.matchedVia === "poster_profile_url" ? (
              <strong>{duplicate.existing.poster_name}</strong>
            ) : (
              <strong>{duplicate.existing.parsed_email}</strong>
            )}
            {duplicate.existing.sent_at && ` on ${new Date(duplicate.existing.sent_at).toLocaleDateString()}`}
            {duplicate.matchedVia === "poster_profile_url" && duplicate.existing.company
              ? ` at ${duplicate.existing.company}`
              : ""}
            . Decide whether it's worth reaching out again before drafting.
          </p>
          {discardError && <p className="error-text">{discardError}</p>}
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn-secondary" onClick={() => setShowDuplicateDetail(true)}>
              View that application
            </button>
            <button className="btn-secondary" onClick={handleDiscard} disabled={discarding}>
              {discarding ? "Discarding…" : "Don't save this"}
            </button>
          </div>
        </div>
      )}

      {duplicate && showDuplicateDetail && (
        <div className="modal-overlay" onClick={() => setShowDuplicateDetail(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-card-header">
              <h3>{duplicate.existing.poster_name}</h3>
              <button onClick={() => setShowDuplicateDetail(false)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="field-grid">
              <div className="field-grid-item">
                <label>Company</label>
                <div>{duplicate.existing.company ?? "—"}</div>
              </div>
              <div className="field-grid-item">
                <label>Job title</label>
                <div>{duplicate.existing.job_title ?? "—"}</div>
              </div>
              <div className="field-grid-item">
                <label>Recipient email</label>
                <div>{duplicate.existing.parsed_email ?? "—"}</div>
              </div>
              <div className="field-grid-item">
                <label>Status</label>
                <div>{duplicate.existing.status}</div>
              </div>
              <div className="field-grid-item">
                <label>Sent at</label>
                <div>{duplicate.existing.sent_at ? new Date(duplicate.existing.sent_at).toLocaleString() : "—"}</div>
              </div>
            </div>
            <div className="field">
              <label>Poster profile</label>
              <div className="muted" style={{ overflowWrap: "break-word" }}>
                <a href={duplicate.existing.poster_profile_url} target="_blank" rel="noreferrer">
                  {duplicate.existing.poster_profile_url}
                </a>
              </div>
            </div>
            <div className="field">
              <label>Post link</label>
              <div className="muted" style={{ overflowWrap: "break-word" }}>
                <a href={duplicate.existing.post_url} target="_blank" rel="noreferrer">
                  {duplicate.existing.post_url}
                </a>
              </div>
            </div>
            {duplicate.existing.drafted_email && (
              <div className="field">
                <label>{duplicate.existing.outreach_type === "linkedin_dm" ? "Drafted DM" : "Drafted email"}</label>
                {duplicate.existing.outreach_type !== "linkedin_dm" && (
                  <div className="muted">Subject: {duplicate.existing.drafted_email.subject}</div>
                )}
                <div style={{ whiteSpace: "pre-wrap" }}>
                  {duplicate.existing.final_email_sent ?? duplicate.existing.drafted_email.body}
                </div>
              </div>
            )}
            <button className="btn-secondary" onClick={() => setShowDuplicateDetail(false)}>
              Close
            </button>
          </div>
        </div>
      )}

      {application.relevance_score !== null && (
        <div className="field">
          <label>Match with your profile</label>
          <div>
            <span className="tag tag-match">{application.relevance_score}%</span>
          </div>
          {application.relevance_reasoning && (
            <div className="muted" style={{ marginTop: 4 }}>
              {application.relevance_reasoning}
            </div>
          )}
        </div>
      )}

      <div className="field-grid">
        <div className="field-grid-item">
          <label>Job title</label>
          <div>{application.job_title ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Company</label>
          <div>{application.company ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Seniority</label>
          <div>{application.seniority ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Location</label>
          <div>{application.location ?? "—"}</div>
        </div>
      </div>

      {application.skills.length > 0 && (
        <div className="field">
          <label>Skills</label>
          <div>{application.skills.join(", ")}</div>
        </div>
      )}

      <div className="field">
        <label>Poster</label>
        <div>
          <a href={application.poster_profile_url} target="_blank" rel="noreferrer">
            {application.poster_name}
          </a>
          {application.poster_headline && <span className="muted"> — {application.poster_headline}</span>}
        </div>
      </div>

      <div className="field">
        <label>Post link</label>
        <div className="muted" style={{ overflowWrap: "break-word" }}>
          <a href={savedPostUrl} target="_blank" rel="noreferrer">
            {savedPostUrl}
          </a>
        </div>
      </div>
      <form onSubmit={handleSaveLink}>
        <div className="field">
          <label htmlFor="lja-post-link">
            Paste the post's actual link here to revisit it later (auto-filled with the search page otherwise)
          </label>
          <input
            id="lja-post-link"
            type="url"
            required
            value={postUrlInput}
            onChange={(e) => setPostUrlInput(e.target.value)}
          />
        </div>
        {linkError && <p className="error-text">{linkError}</p>}
        <button className="btn-secondary" type="submit" disabled={savingLink || postUrlInput === savedPostUrl}>
          {savingLink ? "Saving…" : "Save link"}
        </button>
      </form>

      {savedEmail && <p className="success-text">Contact email: {savedEmail}</p>}

      {!savedEmail && outreachType === null && picker === null && (
        <div className="field">
          <label>No email found in this post — how did they ask to be contacted?</label>
          <button className="btn-secondary" onClick={() => setPicker("email")} style={{ marginBottom: 6 }}>
            Enter an email manually
          </button>
          <button className="btn-secondary" onClick={() => setPicker("linkedin_dm")} style={{ marginBottom: 6 }}>
            They said "DM me"
          </button>
          <button className="btn-secondary" onClick={() => setPicker("apply_via_link")} style={{ marginBottom: 6 }}>
            There's an application link
          </button>
          <button className="btn-secondary" onClick={() => setPicker("reach_out_other")}>
            Reach out to someone else
          </button>
        </div>
      )}

      {!savedEmail && outreachType === null && picker === "email" && (
        <form onSubmit={handleSaveEmail}>
          <div className="field">
            <label htmlFor="lja-manual-email">Enter the contact email</label>
            <input
              id="lja-manual-email"
              type="email"
              required
              value={manualEmail}
              onChange={(e) => setManualEmail(e.target.value)}
            />
          </div>
          {emailError && <p className="error-text">{emailError}</p>}
          <button className="btn-primary" type="submit" disabled={savingEmail}>
            {savingEmail ? "Saving…" : "Save email"}
          </button>
        </form>
      )}

      {!savedEmail && outreachType === null && picker === "linkedin_dm" && (
        <div className="field">
          <p className="muted">
            We'll draft a short DM you can copy and send to{" "}
            <a href={application.poster_profile_url} target="_blank" rel="noreferrer">
              {application.poster_name}
            </a>{" "}
            on LinkedIn.
          </p>
          {outreachError && <p className="error-text">{outreachError}</p>}
          <button
            className="btn-primary"
            onClick={() => handleSaveOutreach("linkedin_dm", null)}
            disabled={savingOutreach}
          >
            {savingOutreach ? "Saving…" : "Confirm"}
          </button>
        </div>
      )}

      {!savedEmail && outreachType === null && (picker === "apply_via_link" || picker === "reach_out_other") && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSaveOutreach(picker, outreachNoteInput);
          }}
        >
          <div className="field">
            <label htmlFor="lja-outreach-note">
              {picker === "apply_via_link"
                ? "Paste the application URL"
                : "Who should be contacted instead? (name or profile URL)"}
            </label>
            <input
              id="lja-outreach-note"
              required
              value={outreachNoteInput}
              onChange={(e) => setOutreachNoteInput(e.target.value)}
            />
          </div>
          {outreachError && <p className="error-text">{outreachError}</p>}
          <button className="btn-primary" type="submit" disabled={savingOutreach}>
            {savingOutreach ? "Saving…" : "Save"}
          </button>
        </form>
      )}

      {!savedEmail && outreachType !== null && outreachType !== "email" && (
        <div className="field">
          <p className="notice-text">
            Outreach type: <strong>{outreachType.replace(/_/g, " ")}</strong>
            {outreachNote && <> — {outreachNote}</>}
          </p>
          {outreachType !== "linkedin_dm" && <MarkSentInline applicationId={application.id} />}
        </div>
      )}

      {(savedEmail || outreachType === "linkedin_dm") && (
        <DraftEmailSection
          applicationId={application.id}
          initialDraft={application.drafted_email}
          mode={outreachType === "linkedin_dm" ? "dm" : "email"}
        />
      )}

      <p className="muted" style={{ marginTop: 12 }}>
        Saved to your application history.
      </p>
      <button className="btn-secondary" onClick={onSelectAnother} style={{ marginTop: 8 }}>
        Select another post
      </button>
    </div>
  );
}

function DraftEmailSection({
  applicationId,
  initialDraft,
  mode,
}: {
  applicationId: string;
  initialDraft: { subject: string; body: string } | null;
  mode: "email" | "dm";
}) {
  const [profiles, setProfiles] = useState<ProfileSummary[] | null>(null);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState("");

  const [subject, setSubject] = useState(initialDraft?.subject ?? "");
  const [body, setBody] = useState(initialDraft?.body ?? "");
  const [savedSubject, setSavedSubject] = useState(initialDraft?.subject ?? "");
  const [savedBody, setSavedBody] = useState(initialDraft?.body ?? "");
  const [hasDraft, setHasDraft] = useState(initialDraft !== null);

  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    const message: ContentToBackgroundMessage = { type: "GET_PROFILES" };
    chrome.runtime.sendMessage(message).then((response: GetProfilesResponse) => {
      if (!response.ok) {
        setProfilesError(response.error);
        return;
      }
      setProfiles(response.profiles);
      const defaultProfile = response.profiles.find((p) => p.is_default) ?? response.profiles[0];
      if (defaultProfile) setSelectedProfileId(defaultProfile.id);
    });
  }, []);

  async function handleDraft() {
    setDrafting(true);
    setDraftError(null);
    const message: ContentToBackgroundMessage = {
      type: "DRAFT_EMAIL",
      applicationId,
      profileId: selectedProfileId,
    };
    const response = (await chrome.runtime.sendMessage(message)) as DraftEmailResponse;
    setDrafting(false);
    if (!response.ok) {
      setDraftError(response.error);
      return;
    }
    const draft = response.application.drafted_email;
    setSubject(draft?.subject ?? "");
    setBody(draft?.body ?? "");
    setSavedSubject(draft?.subject ?? "");
    setSavedBody(draft?.body ?? "");
    setHasDraft(draft !== null);
  }

  async function handleSaveChanges() {
    setSaving(true);
    setSaveError(null);
    const message: ContentToBackgroundMessage = {
      type: "UPDATE_APPLICATION",
      applicationId,
      draftedEmail: { subject, body },
    };
    const response = (await chrome.runtime.sendMessage(message)) as UpdateApplicationResponse;
    setSaving(false);
    if (!response.ok) {
      setSaveError(response.error);
      return;
    }
    setSavedSubject(subject);
    setSavedBody(body);
  }

  const isDirty = subject !== savedSubject || body !== savedBody;

  return (
    <div className="field" style={{ marginTop: 8 }}>
      <label>{mode === "dm" ? "Draft DM" : "Draft email"}</label>

      {profilesError && <p className="error-text">{profilesError}</p>}
      {profiles && profiles.length === 0 && (
        <p className="notice-text">No saved profiles yet — create one in the Web app before drafting.</p>
      )}
      {profiles && profiles.length > 0 && (
        <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.target_job_title}
              {p.is_default ? " (default)" : ""}
            </option>
          ))}
        </select>
      )}

      {draftError && <p className="error-text">{draftError}</p>}
      <button
        className="btn-secondary"
        onClick={handleDraft}
        disabled={drafting || !selectedProfileId}
        style={{ marginTop: 8 }}
      >
        {drafting ? "Drafting…" : hasDraft ? "Regenerate draft" : mode === "dm" ? "Draft DM" : "Draft email"}
      </button>

      {hasDraft && (
        <div style={{ marginTop: 10 }}>
          {mode === "email" && (
            <div className="field">
              <label htmlFor="lja-draft-subject">Subject</label>
              <input id="lja-draft-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
            </div>
          )}
          <div className="field">
            <label htmlFor="lja-draft-body">{mode === "dm" ? "Message" : "Body"}</label>
            <textarea
              id="lja-draft-body"
              rows={8}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          {saveError && <p className="error-text">{saveError}</p>}
          <button className="btn-primary" onClick={handleSaveChanges} disabled={saving || !isDirty}>
            {saving ? "Saving…" : "Save changes"}
          </button>

          {mode === "dm" ? (
            <DmActionsSection applicationId={applicationId} body={body} canAct={!isDirty} />
          ) : (
            <SendEmailSection applicationId={applicationId} canSend={!isDirty} />
          )}
        </div>
      )}
    </div>
  );
}

function DmActionsSection({
  applicationId,
  body,
  canAct,
}: {
  applicationId: string;
  body: string;
  canAct: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(body);
    setCopied(true);
  }

  async function handleMarkSent() {
    setSending(true);
    setSendError(null);
    const message: ContentToBackgroundMessage = { type: "MARK_SENT", applicationId };
    const response = (await chrome.runtime.sendMessage(message)) as MarkSentResponse;
    setSending(false);
    if (!response.ok) {
      setSendError(response.error);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return <p className="success-text" style={{ marginTop: 10 }}>Marked as sent.</p>;
  }

  return (
    <div className="field" style={{ marginTop: 10 }}>
      <label>Send</label>
      {!canAct && <p className="notice-text">Save your edits above first.</p>}
      <button className="btn-secondary" onClick={handleCopy} disabled={!canAct} style={{ marginBottom: 6 }}>
        {copied ? "Copied!" : "Copy message"}
      </button>
      {sendError && <p className="error-text">{sendError}</p>}
      <button className="btn-primary" onClick={handleMarkSent} disabled={!canAct || sending}>
        {sending ? "Saving…" : "Mark as sent"}
      </button>
    </div>
  );
}

function MarkSentInline({ applicationId }: { applicationId: string }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleMarkSent() {
    setSending(true);
    setError(null);
    const message: ContentToBackgroundMessage = { type: "MARK_SENT", applicationId };
    const response = (await chrome.runtime.sendMessage(message)) as MarkSentResponse;
    setSending(false);
    if (!response.ok) {
      setError(response.error);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return <p className="success-text">Marked as sent.</p>;
  }

  return (
    <div>
      {error && <p className="error-text">{error}</p>}
      <button className="btn-secondary" onClick={handleMarkSent} disabled={sending}>
        {sending ? "Saving…" : "Mark as sent"}
      </button>
    </div>
  );
}

function SendEmailSection({ applicationId, canSend }: { applicationId: string; canSend: boolean }) {
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    void refreshStatus();
  }, []);

  async function refreshStatus() {
    setStatusError(null);
    const message: ContentToBackgroundMessage = { type: "GMAIL_STATUS" };
    const response = (await chrome.runtime.sendMessage(message)) as GmailStatusResponse;
    if (response.ok) {
      setStatus(response.status);
    } else {
      setStatusError(response.error);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setStatusError(null);
    const message: ContentToBackgroundMessage = { type: "GMAIL_CONNECT" };
    const response = (await chrome.runtime.sendMessage(message)) as GmailConnectResponse;
    setConnecting(false);
    if (!response.ok) setStatusError(response.error);
  }

  async function handleSend() {
    setSending(true);
    setSendError(null);
    const message: ContentToBackgroundMessage = { type: "SEND_EMAIL", applicationId };
    const response = (await chrome.runtime.sendMessage(message)) as SendEmailResponse;
    setSending(false);
    if (!response.ok) {
      setSendError(response.error);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return <p className="success-text" style={{ marginTop: 10 }}>Sent! Check your Gmail Sent folder.</p>;
  }

  return (
    <div className="field" style={{ marginTop: 10 }}>
      <label>Send</label>
      {statusError && <p className="error-text">{statusError}</p>}

      {status && !status.connected && (
        <>
          <p className="notice-text">Connect your Gmail account to send this email.</p>
          <button className="btn-secondary" onClick={handleConnect} disabled={connecting}>
            {connecting ? "Opening…" : "Connect Gmail"}
          </button>
          <button className="btn-secondary" onClick={refreshStatus} style={{ marginTop: 6 }}>
            I've connected — refresh
          </button>
        </>
      )}

      {status && status.connected && (
        <>
          <p className="muted">Sending from {status.gmail_address}</p>
          {!canSend && <p className="notice-text">Save your draft edits above before sending.</p>}
          {sendError && <p className="error-text">{sendError}</p>}
          <button className="btn-primary" onClick={handleSend} disabled={sending || !canSend}>
            {sending ? "Sending…" : "Send"}
          </button>
        </>
      )}
    </div>
  );
}
