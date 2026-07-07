import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as profilesApi from "../api/profiles";
import * as resumesApi from "../api/resumes";
import { ApiError } from "../api/client";
import {
  emptyProfileDraft,
  type ProfileWriteRequest,
  type ResumeParsedData,
  type ResumeUploadResponse,
} from "../api/types";
import { AchievementsSection } from "../components/AchievementsSection";
import { CertificationsSection } from "../components/CertificationsSection";
import { EducationSection } from "../components/EducationSection";
import { ExperienceSection } from "../components/ExperienceSection";
import { LanguagesSection } from "../components/LanguagesSection";
import { PersonalInfoSection } from "../components/PersonalInfoSection";
import { ProjectsSection } from "../components/ProjectsSection";
import { ResumeUploadSection } from "../components/ResumeUploadSection";
import { SkillsSection } from "../components/SkillsSection";

// Only overwrite a draft field with a parsed one when the parser actually found something —
// never clobber something the user already typed with a blank/empty value from the parser.
function stripEmpty<T extends object>(obj: T): Partial<T> {
  const out: Partial<T> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    (out as Record<string, unknown>)[key] = value;
  }
  return out;
}

// The Resume Parser agent (A3) never returns target_job_title/is_default — those aren't inferable
// from a resume — so this only touches the fields it can produce. List-type sections are replaced
// wholesale rather than appended to, since re-uploading a resume is a "start over from this file"
// action, not a merge of two resumes.
function mergeParsedIntoDraft(draft: ProfileWriteRequest, parsed: ResumeParsedData): ProfileWriteRequest {
  return {
    ...draft,
    professional_summary: parsed.professional_summary || draft.professional_summary,
    personal_info: { ...draft.personal_info, ...stripEmpty(parsed.personal_info) },
    skills: parsed.skills.length > 0 ? parsed.skills : draft.skills,
    experiences: parsed.experiences.length > 0 ? parsed.experiences : draft.experiences,
    projects: parsed.projects.length > 0 ? parsed.projects : draft.projects,
    education: parsed.education.length > 0 ? parsed.education : draft.education,
    certifications: parsed.certifications.length > 0 ? parsed.certifications : draft.certifications,
    achievements: parsed.achievements.length > 0 ? parsed.achievements : draft.achievements,
    languages: parsed.languages.length > 0 ? parsed.languages : draft.languages,
  };
}

export function ProfileEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === "new" || id === undefined;
  const navigate = useNavigate();

  const [draft, setDraft] = useState<ProfileWriteRequest | null>(isNew ? emptyProfileDraft() : null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // A resume can only be uploaded against a profile row that already exists (backend FK). For a
  // brand-new profile this stays null until the user's first upload silently creates the row —
  // from then on, uploads and the final save both target this id instead of POSTing again.
  const [profileId, setProfileId] = useState<string | null>(isNew ? null : id ?? null);
  const [activeResume, setActiveResume] = useState<ResumeUploadResponse | null>(null);

  useEffect(() => {
    if (isNew || !id) return;
    profilesApi
      .getProfile(id)
      .then(setDraft)
      .catch(() => setError("Could not load this profile."));
    resumesApi
      .getActiveResume(id)
      .then(setActiveResume)
      .catch(() => setActiveResume(null)); // 404 = no resume uploaded yet, not an error
  }, [id, isNew]);

  async function handleUploadResume(file: File) {
    if (!draft) return;
    let targetId = profileId;
    if (!targetId) {
      if (!draft.target_job_title.trim()) {
        throw new Error("Enter a target job title before uploading a resume.");
      }
      const created = await profilesApi.createProfile(draft);
      targetId = created.id;
      setProfileId(created.id);
    }
    const result = await resumesApi.uploadResume(targetId, file);
    setActiveResume(result.resume);
    setDraft((prev) => (prev ? mergeParsedIntoDraft(prev, result.parsed) : prev));
  }

  async function handleSubmit() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      if (profileId) {
        await profilesApi.updateProfile(profileId, draft);
      } else {
        await profilesApi.createProfile(draft);
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

      <ResumeUploadSection
        existingResume={activeResume}
        canUpload={!!profileId || draft.target_job_title.trim().length > 0}
        disabledHint="Enter a target job title above to enable resume upload."
        onUpload={handleUploadResume}
      />

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
