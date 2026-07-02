import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as profilesApi from "../api/profiles";
import { ApiError } from "../api/client";
import { emptyProfileDraft, type ProfileWriteRequest } from "../api/types";
import { AchievementsSection } from "../components/AchievementsSection";
import { CertificationsSection } from "../components/CertificationsSection";
import { EducationSection } from "../components/EducationSection";
import { ExperienceSection } from "../components/ExperienceSection";
import { LanguagesSection } from "../components/LanguagesSection";
import { PersonalInfoSection } from "../components/PersonalInfoSection";
import { ProjectsSection } from "../components/ProjectsSection";
import { SkillsSection } from "../components/SkillsSection";

export function ProfileEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === "new" || id === undefined;
  const navigate = useNavigate();

  const [draft, setDraft] = useState<ProfileWriteRequest | null>(isNew ? emptyProfileDraft() : null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew || !id) return;
    profilesApi
      .getProfile(id)
      .then(setDraft)
      .catch(() => setError("Could not load this profile."));
  }, [id, isNew]);

  async function handleSubmit() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      if (isNew) {
        await profilesApi.createProfile(draft);
      } else if (id) {
        await profilesApi.updateProfile(id, draft);
      }
      navigate("/profiles");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this profile.");
    } finally {
      setSaving(false);
    }
  }

  if (!draft) {
    return (
      <div className="page">
        {error ? <p className="error-text">{error}</p> : <p className="muted">Loading…</p>}
      </div>
    );
  }

  return (
    <div className="page">
      <div className="section-title">
        <h2>{isNew ? "New profile" : "Edit profile"}</h2>
        <div className="item-actions">
          <button className="btn btn-secondary" onClick={() => navigate("/profiles")}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={saving} onClick={handleSubmit}>
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <div className="field">
            <label>Target job title</label>
            <input
              value={draft.target_job_title}
              onChange={(e) => setDraft({ ...draft, target_job_title: e.target.value })}
            />
          </div>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={draft.is_default}
              onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
              style={{ marginRight: 6 }}
            />
            Default profile
          </label>
        </div>
        <div className="field">
          <label>Professional summary</label>
          <textarea
            rows={4}
            value={draft.professional_summary ?? ""}
            onChange={(e) => setDraft({ ...draft, professional_summary: e.target.value })}
          />
        </div>
      </div>

      <h3 className="section-title">Personal information</h3>
      <PersonalInfoSection value={draft.personal_info} onChange={(personal_info) => setDraft({ ...draft, personal_info })} />

      <h3 className="section-title">Technical skills</h3>
      <SkillsSection items={draft.skills} onChange={(skills) => setDraft({ ...draft, skills })} />

      <h3 className="section-title">Experience</h3>
      <ExperienceSection items={draft.experiences} onChange={(experiences) => setDraft({ ...draft, experiences })} />

      <h3 className="section-title">Personal projects</h3>
      <ProjectsSection items={draft.projects} onChange={(projects) => setDraft({ ...draft, projects })} />

      <h3 className="section-title">Education</h3>
      <EducationSection items={draft.education} onChange={(education) => setDraft({ ...draft, education })} />

      <h3 className="section-title">Certifications</h3>
      <CertificationsSection
        items={draft.certifications}
        onChange={(certifications) => setDraft({ ...draft, certifications })}
      />

      <h3 className="section-title">Achievements & awards</h3>
      <AchievementsSection items={draft.achievements} onChange={(achievements) => setDraft({ ...draft, achievements })} />

      <h3 className="section-title">Languages</h3>
      <LanguagesSection items={draft.languages} onChange={(languages) => setDraft({ ...draft, languages })} />

      <button className="btn btn-primary" disabled={saving} onClick={handleSubmit}>
        {saving ? "Saving…" : "Save profile"}
      </button>
    </div>
  );
}
