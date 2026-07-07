import { Fragment, useEffect, useState } from "react";
import * as adminUsersApi from "../api/adminUsers";
import * as invitesApi from "../api/invites";
import * as metricsApi from "../api/metrics";
import type { AdminOverviewResponse, AdminUserRow, InviteCodeResponse } from "../api/types";

export function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverviewResponse | null>(null);
  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [invites, setInvites] = useState<InviteCodeResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [newCodeExpiry, setNewCodeExpiry] = useState("");
  const [busyInviteId, setBusyInviteId] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editExpiry, setEditExpiry] = useState("");
  const [editNotes, setEditNotes] = useState("");

  function refresh() {
    metricsApi.getAdminOverview().then(setOverview).catch(() => setError("Could not load platform overview."));
    metricsApi.getAdminUsers().then(setUsers).catch(() => setError("Could not load per-user metrics."));
    invitesApi.listInviteCodes().then(setInvites).catch(() => setError("Could not load invite codes."));
  }

  useEffect(refresh, []);

  async function handleGenerateCode() {
    setGenerating(true);
    try {
      // <input type="date"> gives "YYYY-MM-DD" — treat it as end-of-day UTC so a code stays valid
      // for the whole day the admin picked, not from midnight.
      const expiresAt = newCodeExpiry ? `${newCodeExpiry}T23:59:59Z` : undefined;
      await invitesApi.createInviteCode(expiresAt);
      setNewCodeExpiry("");
      invitesApi.listInviteCodes().then(setInvites);
    } catch {
      setError("Could not generate an invite code.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleRevokeCode(id: string) {
    setBusyInviteId(id);
    try {
      await invitesApi.revokeInviteCode(id);
      invitesApi.listInviteCodes().then(setInvites);
    } catch {
      setError("Could not revoke this invite code.");
    } finally {
      setBusyInviteId(null);
    }
  }

  async function handleToggleUserAccess(row: AdminUserRow) {
    setBusyUserId(row.id);
    try {
      if (row.is_active) {
        await adminUsersApi.revokeUserAccess(row.id);
      } else {
        await adminUsersApi.restoreUserAccess(row.id);
      }
      metricsApi.getAdminUsers().then(setUsers);
    } catch {
      setError("Could not update this user's access.");
    } finally {
      setBusyUserId(null);
    }
  }

  function handleStartEditAccess(row: AdminUserRow) {
    setEditingUserId(row.id);
    setEditExpiry(row.access_expires_at ? row.access_expires_at.slice(0, 10) : "");
    setEditNotes(row.admin_notes ?? "");
  }

  async function handleSaveAccess(userId: string) {
    setBusyUserId(userId);
    try {
      await adminUsersApi.updateUserAccess(userId, {
        access_expires_at: editExpiry ? `${editExpiry}T23:59:59Z` : null,
        admin_notes: editNotes || null,
      });
      setEditingUserId(null);
      metricsApi.getAdminUsers().then(setUsers);
    } catch {
      setError("Could not save this user's access settings.");
    } finally {
      setBusyUserId(null);
    }
  }

  return (
    <div className="page">
      <div className="section-title">
        <h2>Admin dashboard</h2>
      </div>

      {error && <p className="error-text">{error}</p>}

      {overview && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="field-grid">
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  Total users
                </div>
                <div>{overview.total_users}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase" }}>
                  Signups today
                </div>
                <div>{overview.signups_today}</div>
              </div>
            </div>
          </div>

          <h3 className="section-title">Signups — last 14 days</h3>
          <div className="card" style={{ marginBottom: 16, overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Signups</th>
                </tr>
              </thead>
              <tbody>
                {overview.signups_last_14_days.map((row) => (
                  <tr key={row.date}>
                    <td>{row.date}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="section-title">Token spend — last 14 days</h3>
          <div className="card" style={{ marginBottom: 16, overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Input tokens</th>
                  <th>Output tokens</th>
                </tr>
              </thead>
              <tbody>
                {overview.token_spend_last_14_days.map((row) => (
                  <tr key={row.date}>
                    <td>{row.date}</td>
                    <td>{row.input_tokens}</td>
                    <td>{row.output_tokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="section-title">Agent breakdown</h3>
          <div className="card" style={{ marginBottom: 16, overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Calls</th>
                  <th>Avg latency (ms)</th>
                  <th>Input tokens</th>
                  <th>Output tokens</th>
                </tr>
              </thead>
              <tbody>
                {overview.agent_breakdown.map((row) => (
                  <tr key={row.agent_name}>
                    <td>{row.agent_name}</td>
                    <td>{row.call_count}</td>
                    <td>{row.avg_latency_ms.toFixed(0)}</td>
                    <td>{row.input_tokens}</td>
                    <td>{row.output_tokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="section-title">Per-user usage</h3>
      <div className="card" style={{ marginBottom: 16, overflowX: "auto" }}>
        {users === null ? (
          <p className="muted">Loading…</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Registered</th>
                <th>Last active</th>
                <th>Input tokens</th>
                <th>Output tokens</th>
                <th>Emails sent</th>
                <th>Status</th>
                <th>Access expires</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => (
                <Fragment key={row.id}>
                  <tr>
                    <td>{row.email}</td>
                    <td>{new Date(row.created_at).toLocaleDateString()}</td>
                    <td>{row.last_login_at ? new Date(row.last_login_at).toLocaleString() : "—"}</td>
                    <td>{row.input_tokens}</td>
                    <td>{row.output_tokens}</td>
                    <td>{row.emails_sent}</td>
                    <td>
                      <span className={row.is_active ? "badge badge-success" : "badge badge-warning"}>
                        {row.is_active ? "active" : "revoked"}
                      </span>
                    </td>
                    <td>{row.access_expires_at ? new Date(row.access_expires_at).toLocaleDateString() : "Never"}</td>
                    <td className="truncate" style={{ maxWidth: 160 }}>
                      {row.admin_notes || "—"}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          className={row.is_active ? "btn btn-danger" : "btn btn-secondary"}
                          onClick={() => handleToggleUserAccess(row)}
                          disabled={busyUserId === row.id}
                        >
                          {row.is_active ? "Revoke" : "Restore"}
                        </button>
                        <button className="btn btn-secondary" onClick={() => handleStartEditAccess(row)}>
                          Edit access
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editingUserId === row.id && (
                    <tr>
                      <td colSpan={10}>
                        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", padding: "8px 0" }}>
                          <label className="muted" style={{ fontSize: 12.5 }}>
                            Access expires (blank = unlimited)
                            <input
                              type="date"
                              value={editExpiry}
                              onChange={(e) => setEditExpiry(e.target.value)}
                              style={{ display: "block", marginTop: 4 }}
                            />
                          </label>
                          <label className="muted" style={{ fontSize: 12.5, flex: 1 }}>
                            Notes
                            <textarea
                              value={editNotes}
                              onChange={(e) => setEditNotes(e.target.value)}
                              rows={2}
                              style={{ display: "block", width: "100%", marginTop: 4 }}
                            />
                          </label>
                          <button
                            className="btn btn-primary"
                            onClick={() => handleSaveAccess(row.id)}
                            disabled={busyUserId === row.id}
                          >
                            {busyUserId === row.id ? "Saving…" : "Save"}
                          </button>
                          <button className="btn btn-secondary" onClick={() => setEditingUserId(null)}>
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section-title">
        <h3>Invite codes</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label className="muted" style={{ fontSize: 12.5 }}>
            Expires (optional)
            <input
              type="date"
              value={newCodeExpiry}
              onChange={(e) => setNewCodeExpiry(e.target.value)}
              style={{ marginLeft: 6 }}
            />
          </label>
          <button className="btn btn-primary" onClick={handleGenerateCode} disabled={generating}>
            {generating ? "Generating…" : "Generate code"}
          </button>
        </div>
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        {invites === null ? (
          <p className="muted">Loading…</p>
        ) : invites.length === 0 ? (
          <p className="muted">No invite codes yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Status</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Used by</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => {
                const now = Date.now();
                const isExpired = invite.expires_at !== null && new Date(invite.expires_at).getTime() < now;
                const isRevoked = invite.revoked_at !== null;
                const canRevoke = !invite.is_used && !isRevoked;
                let statusLabel = "unused";
                let statusClass = "badge badge-success";
                if (invite.is_used) {
                  statusLabel = "used";
                  statusClass = "badge";
                } else if (isRevoked) {
                  statusLabel = "revoked";
                  statusClass = "badge badge-warning";
                } else if (isExpired) {
                  statusLabel = "expired";
                  statusClass = "badge badge-warning";
                }
                return (
                  <tr key={invite.id}>
                    <td>{invite.code}</td>
                    <td>
                      <span className={statusClass}>{statusLabel}</span>
                    </td>
                    <td>{new Date(invite.created_at).toLocaleDateString()}</td>
                    <td>{invite.expires_at ? new Date(invite.expires_at).toLocaleDateString() : "Never"}</td>
                    <td>{invite.used_by_email ?? "—"}</td>
                    <td>
                      {canRevoke && (
                        <button
                          className="btn btn-danger"
                          onClick={() => handleRevokeCode(invite.id)}
                          disabled={busyInviteId === invite.id}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
