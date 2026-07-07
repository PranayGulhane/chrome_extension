import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as profilesApi from "../api/profiles";
import type { ProfileResponse, SkillItem } from "../api/types";

function groupSkillsByCategory(skills: SkillItem[]): { category: string; skills: SkillItem[] }[] {
  const order: string[] = [];
  const byCategory = new Map<string, SkillItem[]>();
  for (const skill of skills) {
    if (!byCategory.has(skill.category)) {
      order.push(skill.category);
      byCategory.set(skill.category, []);
    }
    byCategory.get(skill.category)!.push(skill);
  }
  return order.map((category) => ({ category, skills: byCategory.get(category)! }));
}

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

export function ProfileViewPage() {
  const { id } = useParams<{ id: string }>();
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    profilesApi
      .getProfile(id)
      .then(setProfile)
      .catch(() => setError("Could not load this profile."));
  }, [id]);

  if (error) return <div className="page"><p className="error-text">{error}</p></div>;
  if (!profile) return <div className="page"><p className="muted">Loading…</p></div>;

  const { personal_info: p } = profile;
  const fullName = [p.first_name, p.last_name].filter(Boolean).join(" ");
  const location = [p.current_city, p.state_province, p.country].filter(Boolean).join(", ");
  const skillGroups = groupSkillsByCategory(profile.skills);

  return (
    <div className="page">
      <div className="section-title">
        <h2 style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {profile.target_job_title}
          {profile.is_default && <span className="badge">default</span>}
        </h2>
        <div className="item-actions">
          <Link to="/profiles" className="btn btn-secondary">
            Back to list
          </Link>
          <Link to={`/profiles/${profile.id}`} className="btn btn-primary">
            Edit
          </Link>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        {fullName && <h3 style={{ marginBottom: 4 }}>{fullName}</h3>}
        {p.professional_headline && <div className="muted" style={{ marginBottom: 12 }}>{p.professional_headline}</div>}
        <div className="field-grid">
          <Field label="Email" value={p.email} />
          <Field label="Phone" value={p.phone_number} />
          <Field label="Location" value={location} />
          <Field label="Work authorization" value={p.work_authorization} />
        </div>
        <div className="field-grid" style={{ marginTop: 12 }}>
          <Field label="LinkedIn" value={p.linkedin_url} />
          <Field label="GitHub" value={p.github_url} />
          <Field label="Portfolio" value={p.portfolio_website} />
          <Field label="Website" value={p.personal_website} />
        </div>
        {p.preferred_work_locations.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Field label="Preferred work locations" value={p.preferred_work_locations.join(", ")} />
          </div>
        )}
      </div>

      {profile.professional_summary && (
        <>
          <h3 className="section-title">Professional summary</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{profile.professional_summary}</p>
          </div>
        </>
      )}

      {skillGroups.length > 0 && (
        <>
          <h3 className="section-title">Technical skills</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {skillGroups.map((group) => (
              <div key={group.category} style={{ marginBottom: 10 }}>
                <strong>{group.category}</strong>
                <ul className="skill-grid">
                  {group.skills.map((skill, i) => (
                    <li key={i}>{skill.skill_name}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {profile.experiences.length > 0 && (
        <>
          <h3 className="section-title">Experience</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.experiences.map((exp, i) => (
              <div key={i} style={{ marginBottom: 18 }}>
                <div style={{ fontWeight: 700 }}>
                  {exp.job_title} · {exp.company_name}
                </div>
                <div className="muted">
                  {[exp.employment_type, exp.location].filter(Boolean).join(" · ")}
                  {(exp.start_date || exp.end_date) && (
                    <>
                      {" "}
                      ({exp.start_date ?? "?"} – {exp.currently_working_here ? "present" : exp.end_date ?? "?"})
                    </>
                  )}
                </div>
                {exp.responsibilities.length > 0 && (
                  <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
                    {exp.responsibilities.map((r, j) => (
                      <li key={j}>{r}</li>
                    ))}
                  </ul>
                )}
                {exp.projects.map((proj, j) => (
                  <div key={j} style={{ marginTop: 8, paddingLeft: 14, borderLeft: "2px solid var(--border)" }}>
                    <div style={{ fontWeight: 600 }}>{proj.project_name}</div>
                    <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                      {proj.details.map((d, k) => (
                        <li key={k}>{d}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {profile.projects.length > 0 && (
        <>
          <h3 className="section-title">Personal projects</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.projects.map((proj, i) => (
              <div key={i} style={{ marginBottom: 14 }}>
                <div style={{ fontWeight: 700 }}>{proj.project_name}</div>
                <div className="muted">{[proj.demo_url, proj.github_url].filter(Boolean).join(" · ")}</div>
                <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
                  {proj.details.map((d, j) => (
                    <li key={j}>{d}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {profile.education.length > 0 && (
        <>
          <h3 className="section-title">Education</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.education.map((edu, i) => (
              <div key={i} style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 700 }}>
                  {edu.degree}
                  {edu.field_of_study ? ` in ${edu.field_of_study}` : ""}
                </div>
                <div className="muted">
                  {edu.institution_name}
                  {edu.end_date ? ` · ${edu.end_date}` : edu.graduation_year ? ` · ${edu.graduation_year}` : ""}
                  {edu.gpa ? ` · GPA ${edu.gpa}` : ""}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {profile.certifications.length > 0 && (
        <>
          <h3 className="section-title">Certifications</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.certifications.map((cert, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{cert.certification_name}</div>
                <div className="muted">{[cert.issuing_organization, cert.issue_date].filter(Boolean).join(" · ")}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {profile.achievements.length > 0 && (
        <>
          <h3 className="section-title">Achievements & awards</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.achievements.map((a, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{a.achievement_title}</div>
                <div className="muted">{[a.organization, a.date_achieved].filter(Boolean).join(" · ")}</div>
                {a.description.length > 0 && (
                  <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                    {a.description.map((d, j) => (
                      <li key={j}>{d}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {profile.languages.length > 0 && (
        <>
          <h3 className="section-title">Languages</h3>
          <div className="card" style={{ marginBottom: 16 }}>
            {profile.languages.map((lang, i) => (
              <div key={i}>
                {lang.language} — <span className="muted">{lang.proficiency}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
