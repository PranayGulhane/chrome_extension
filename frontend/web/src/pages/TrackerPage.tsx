import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as trackerApi from "../api/tracker";
import type { ApplicationResponse } from "../api/types";

export function TrackerPage() {
  const [applications, setApplications] = useState<ApplicationResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    trackerApi
      .listApplications()
      .then(setApplications)
      .catch(() => setError("Could not load your application history."));
  }, []);

  const visible = applications?.filter((a) => showArchived || !a.is_archived);

  return (
    <div className="page">
      <div className="section-title">
        <h2>Application tracker</h2>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13.5 }}>
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
        Show archived
      </label>

      {error && <p className="error-text">{error}</p>}
      {applications === null && !error && <p className="muted">Loading…</p>}
      {applications?.length === 0 && (
        <p className="muted">No applications yet — extract a post from the extension to get started.</p>
      )}
      {applications && applications.length > 0 && visible?.length === 0 && (
        <p className="muted">No applications to show.</p>
      )}

      {visible?.map((application) => (
        <Link
          to={`/tracker/${application.id}`}
          className="list-item"
          key={application.id}
          style={{ textDecoration: "none", color: "inherit", opacity: application.is_archived ? 0.6 : 1 }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700 }} className="truncate">
              {application.poster_name}
            </div>
            <div className="muted truncate">
              {application.job_title ?? "—"}
              {application.company ? ` at ${application.company}` : ""}
            </div>
          </div>
          <div className="item-actions" style={{ gap: 6 }}>
            <span className="badge">{application.status}</span>
            {application.outreach_type && (
              <span className="badge">{application.outreach_type.replace(/_/g, " ")}</span>
            )}
            {application.relevance_score !== null && (
              <span className="badge badge-success">{application.relevance_score}% match</span>
            )}
            {application.was_truncated && <span className="badge badge-warning">truncated</span>}
            {application.is_archived && <span className="badge">archived</span>}
          </div>
        </Link>
      ))}
    </div>
  );
}
