import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import * as profilesApi from "../api/profiles";
import type { ProfileSummaryResponse } from "../api/types";

export function ProfilesPage() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<ProfileSummaryResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    try {
      setProfiles(await profilesApi.listProfiles());
    } catch {
      setError("Could not load profiles.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleSetDefault(id: string) {
    setBusyId(id);
    try {
      await profilesApi.setDefaultProfile(id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleClone(profile: ProfileSummaryResponse) {
    const targetJobTitle = window.prompt("Target job title for the cloned profile:", `${profile.target_job_title} (copy)`);
    if (!targetJobTitle) return;
    setBusyId(profile.id);
    try {
      const clone = await profilesApi.cloneProfile(profile.id, targetJobTitle);
      navigate(`/profiles/${clone.id}`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this profile? This cannot be undone.")) return;
    setBusyId(id);
    try {
      await profilesApi.deleteProfile(id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <div className="section-title">
        <h2>Your profiles</h2>
        <Link to="/profiles/new" className="btn btn-primary">
          + New profile
        </Link>
      </div>

      {error && <p className="error-text">{error}</p>}
      {profiles === null && !error && <p className="muted">Loading…</p>}
      {profiles?.length === 0 && (
        <p className="muted">No profiles yet. Create one to start drafting outreach emails.</p>
      )}

      {profiles?.map((profile) => (
        <div className="list-item" key={profile.id}>
          <div>
            <div style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              {profile.target_job_title}
              {profile.is_default && <span className="badge">default</span>}
            </div>
            {profile.professional_summary && <div className="muted">{profile.professional_summary}</div>}
          </div>
          <div className="item-actions">
            <Link to={`/profiles/${profile.id}/view`} className="btn btn-secondary">
              View
            </Link>
            {!profile.is_default && (
              <button
                className="btn btn-secondary"
                disabled={busyId === profile.id}
                onClick={() => handleSetDefault(profile.id)}
              >
                Set default
              </button>
            )}
            <button className="btn btn-secondary" disabled={busyId === profile.id} onClick={() => handleClone(profile)}>
              Clone
            </button>
            <Link to={`/profiles/${profile.id}`} className="btn btn-secondary">
              Edit
            </Link>
            <button className="btn btn-danger" disabled={busyId === profile.id} onClick={() => handleDelete(profile.id)}>
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
