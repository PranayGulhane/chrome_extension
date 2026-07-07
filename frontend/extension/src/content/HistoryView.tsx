import { useEffect, useState } from "react";
import type {
  ApplicationDetail,
  ContentToBackgroundMessage,
  ListApplicationsResponse,
  MarkArchivedResponse,
  MarkRepliedResponse,
  MarkUnarchivedResponse,
} from "../shared/types";

export function HistoryView() {
  const [applications, setApplications] = useState<ApplicationDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    const message: ContentToBackgroundMessage = { type: "LIST_APPLICATIONS" };
    chrome.runtime.sendMessage(message).then((response: ListApplicationsResponse) => {
      if (response.ok) {
        setApplications(response.applications);
      } else {
        setError(response.error);
      }
    });
  }, []);

  function handleUpdated(applicationId: string, updated: ApplicationDetail) {
    setApplications((prev) => prev?.map((a) => (a.id === applicationId ? updated : a)) ?? prev);
  }

  if (error) return <p className="error-text">{error}</p>;
  if (applications === null) return <p className="muted">Loading…</p>;
  if (applications.length === 0) return <p className="muted">No applications yet — extract a post to get started.</p>;

  const visible = applications.filter((a) => showArchived || !a.is_archived);

  return (
    <div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10, fontSize: 13 }}>
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
        Show archived
      </label>

      {visible.length === 0 && <p className="muted">No applications to show.</p>}

      {visible.map((application) => (
        <div key={application.id}>
          <div
            className="list-row"
            style={application.is_archived ? { opacity: 0.6 } : undefined}
            onClick={() => setExpandedId(expandedId === application.id ? null : application.id)}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>{application.poster_name}</div>
              <div className="muted">
                {application.job_title ?? "—"}
                {application.company ? ` at ${application.company}` : ""}
              </div>
            </div>
            <span className="tag tag-status">{application.status}</span>
            {application.outreach_type && (
              <span className="tag tag-outreach">{application.outreach_type.replace(/_/g, " ")}</span>
            )}
            {application.relevance_score !== null && (
              <span className="tag tag-match">{application.relevance_score}%</span>
            )}
            {application.was_truncated && <span className="tag tag-warning">truncated</span>}
            {application.is_archived && <span className="tag tag-outreach">archived</span>}
          </div>
          {expandedId === application.id && (
            <HistoryDetail application={application} onUpdated={(updated) => handleUpdated(application.id, updated)} />
          )}
        </div>
      ))}
    </div>
  );
}

function HistoryDetail({
  application,
  onUpdated,
}: {
  application: ApplicationDetail;
  onUpdated: (updated: ApplicationDetail) => void;
}) {
  const [marking, setMarking] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleMarkReplied() {
    setMarking(true);
    setError(null);
    const message: ContentToBackgroundMessage = { type: "MARK_REPLIED", applicationId: application.id };
    const response = (await chrome.runtime.sendMessage(message)) as MarkRepliedResponse;
    setMarking(false);
    if (!response.ok) {
      setError(response.error);
      return;
    }
    onUpdated(response.application);
  }

  async function handleToggleArchive() {
    setArchiving(true);
    setError(null);
    const message: ContentToBackgroundMessage = application.is_archived
      ? { type: "MARK_UNARCHIVED", applicationId: application.id }
      : { type: "MARK_ARCHIVED", applicationId: application.id };
    const response = (await chrome.runtime.sendMessage(message)) as MarkArchivedResponse | MarkUnarchivedResponse;
    setArchiving(false);
    if (!response.ok) {
      setError(response.error);
      return;
    }
    onUpdated(response.application);
  }

  return (
    <div className="field" style={{ marginTop: 6, marginBottom: 10 }}>
      {application.was_truncated && <p className="notice-text">Only partial post text was captured.</p>}

      <div className="field-grid">
        <div className="field-grid-item">
          <label>Location</label>
          <div>{application.location ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Seniority</label>
          <div>{application.seniority ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Contact</label>
          <div>{application.parsed_email ?? application.outreach_note ?? "—"}</div>
        </div>
        <div className="field-grid-item">
          <label>Sent at</label>
          <div>{application.sent_at ? new Date(application.sent_at).toLocaleString() : "—"}</div>
        </div>
      </div>

      {application.drafted_email && (
        <div className="field">
          <label>Drafted message</label>
          <div className="muted" style={{ whiteSpace: "pre-wrap" }}>
            {application.final_email_sent ?? application.drafted_email.body}
          </div>
        </div>
      )}

      <div className="field">
        <label>Post link</label>
        <div className="muted" style={{ overflowWrap: "break-word" }}>
          <a href={application.post_url} target="_blank" rel="noreferrer">
            {application.post_url}
          </a>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div style={{ display: "flex", gap: 8 }}>
        {application.status === "sent" && (
          <button className="btn-secondary" onClick={handleMarkReplied} disabled={marking}>
            {marking ? "Saving…" : "Mark as replied"}
          </button>
        )}
        <button className="btn-secondary" onClick={handleToggleArchive} disabled={archiving}>
          {archiving ? "Saving…" : application.is_archived ? "Unarchive" : "Archive"}
        </button>
      </div>
    </div>
  );
}
