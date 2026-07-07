import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as trackerApi from "../api/tracker";
import type { ApplicationResponse } from "../api/types";

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
      <div>{value}</div>
    </div>
  );
}

export function TrackerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [application, setApplication] = useState<ApplicationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    if (!id) return;
    trackerApi
      .getApplication(id)
      .then(setApplication)
      .catch(() => setError("Could not load this application."));
  }

  useEffect(refresh, [id]);

  async function handleMarkSent() {
    if (!id) return;
    setBusy(true);
    try {
      setApplication(await trackerApi.markSent(id));
    } catch {
      setError("Could not mark this as sent.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkReplied() {
    if (!id) return;
    setBusy(true);
    try {
      setApplication(await trackerApi.markReplied(id));
    } catch {
      setError("Could not mark this as replied.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleArchive() {
    if (!id || !application) return;
    setBusy(true);
    try {
      setApplication(
        application.is_archived ? await trackerApi.unarchiveApplication(id) : await trackerApi.archiveApplication(id),
      );
    } catch {
      setError("Could not update the archive state.");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="page"><p className="error-text">{error}</p></div>;
  if (!application) return <div className="page"><p className="muted">Loading…</p></div>;

  const canMarkSent =
    application.outreach_type !== null &&
    application.outreach_type !== "email" &&
    application.status !== "sent" &&
    application.status !== "replied";
  const canMarkReplied = application.status === "sent";

  return (
    <div className="page">
      <div className="section-title">
        <h2 style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {application.poster_name}
          <span className="badge">{application.status}</span>
          {application.outreach_type && <span className="badge">{application.outreach_type.replace(/_/g, " ")}</span>}
          {application.is_archived && <span className="badge">archived</span>}
        </h2>
        <Link to="/tracker" className="btn btn-secondary">
          Back to list
        </Link>
      </div>

      {application.was_truncated && (
        <p className="error-text" style={{ color: "#7a5b00" }}>
          Only partial post text was captured for this application.
        </p>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="field-grid">
          <Field label="Company" value={application.company} />
          <Field label="Job title" value={application.job_title} />
          <Field label="Seniority" value={application.seniority} />
          <Field label="Location" value={application.location} />
        </div>
        <div className="field-grid" style={{ marginTop: 12 }}>
          <Field label="Recipient email" value={application.parsed_email} />
          <Field label="Outreach note" value={application.outreach_note} />
          <Field label="Sent at" value={application.sent_at ? new Date(application.sent_at).toLocaleString() : null} />
          <Field label="Resume attached" value={application.resume_upload_id ? "yes" : null} />
        </div>
        {application.skills.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Field label="Skills" value={application.skills.join(", ")} />
          </div>
        )}
        {application.relevance_score !== null && (
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Relevance
            </div>
            <div>
              <span className="badge badge-success">{application.relevance_score}% match</span>
            </div>
            {application.relevance_reasoning && (
              <p className="muted" style={{ marginTop: 4 }}>
                {application.relevance_reasoning}
              </p>
            )}
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Poster
          </div>
          <a href={application.poster_profile_url} target="_blank" rel="noreferrer">
            {application.poster_profile_url}
          </a>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Post link
          </div>
          <a href={application.post_url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>
            {application.post_url}
          </a>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Post snippet
          </div>
          <p style={{ whiteSpace: "pre-wrap" }}>{application.post_snippet}</p>
        </div>
      </div>

      {application.drafted_email && (
        <>
          <h3 className="section-title">{application.outreach_type === "linkedin_dm" ? "Drafted DM" : "Drafted email"}</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {application.outreach_type !== "linkedin_dm" && (
              <Field label="Subject" value={application.drafted_email.subject} />
            )}
            <p style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
              {application.final_email_sent ?? application.drafted_email.body}
            </p>
          </div>
        </>
      )}

      <div className="item-actions">
        {canMarkSent && (
          <button className="btn btn-secondary" onClick={handleMarkSent} disabled={busy}>
            Mark as sent
          </button>
        )}
        {canMarkReplied && (
          <button className="btn btn-secondary" onClick={handleMarkReplied} disabled={busy}>
            Mark as replied
          </button>
        )}
        <button className="btn btn-secondary" onClick={handleToggleArchive} disabled={busy}>
          {application.is_archived ? "Unarchive" : "Archive"}
        </button>
      </div>
    </div>
  );
}
