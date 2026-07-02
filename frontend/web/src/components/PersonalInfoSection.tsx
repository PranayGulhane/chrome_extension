import { useState } from "react";
import type { PersonalInfo } from "../api/types";

export function PersonalInfoSection({
  value,
  onChange,
}: {
  value: PersonalInfo;
  onChange: (next: PersonalInfo) => void;
}) {
  function set<K extends keyof PersonalInfo>(key: K, val: PersonalInfo[K]) {
    onChange({ ...value, [key]: val });
  }

  // Local draft text, committed to the parsed array only on blur — same reasoning as
  // BulletListField: deriving the input's displayed value directly from a parsed array fights
  // every keystroke that isn't already in canonical form (e.g. a trailing comma with nothing
  // after it yet gets stripped immediately, so the comma visually never "sticks").
  const [locationsText, setLocationsText] = useState(value.preferred_work_locations.join(", "));

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row">
        <div className="field">
          <label>First name</label>
          <input value={value.first_name ?? ""} onChange={(e) => set("first_name", e.target.value)} />
        </div>
        <div className="field">
          <label>Last name</label>
          <input value={value.last_name ?? ""} onChange={(e) => set("last_name", e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>Professional headline</label>
        <input value={value.professional_headline ?? ""} onChange={(e) => set("professional_headline", e.target.value)} />
      </div>
      <div className="row">
        <div className="field">
          <label>Email</label>
          <input type="email" value={value.email ?? ""} onChange={(e) => set("email", e.target.value)} />
        </div>
        <div className="field">
          <label>Phone number</label>
          <input value={value.phone_number ?? ""} onChange={(e) => set("phone_number", e.target.value)} />
        </div>
      </div>
      <div className="row">
        <div className="field">
          <label>City</label>
          <input value={value.current_city ?? ""} onChange={(e) => set("current_city", e.target.value)} />
        </div>
        <div className="field">
          <label>State / Province</label>
          <input value={value.state_province ?? ""} onChange={(e) => set("state_province", e.target.value)} />
        </div>
        <div className="field">
          <label>Country</label>
          <input value={value.country ?? ""} onChange={(e) => set("country", e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>
          <input
            type="checkbox"
            checked={value.willing_to_relocate ?? false}
            onChange={(e) => set("willing_to_relocate", e.target.checked)}
            style={{ marginRight: 6 }}
          />
          Willing to relocate
        </label>
      </div>
      <div className="field">
        <label>Preferred work locations (comma separated)</label>
        <input
          value={locationsText}
          onChange={(e) => setLocationsText(e.target.value)}
          onBlur={() =>
            set(
              "preferred_work_locations",
              locationsText.split(",").map((s) => s.trim()).filter(Boolean),
            )
          }
        />
      </div>
      <div className="row">
        <div className="field">
          <label>LinkedIn URL</label>
          <input value={value.linkedin_url ?? ""} onChange={(e) => set("linkedin_url", e.target.value)} />
        </div>
        <div className="field">
          <label>GitHub URL</label>
          <input value={value.github_url ?? ""} onChange={(e) => set("github_url", e.target.value)} />
        </div>
      </div>
      <div className="row">
        <div className="field">
          <label>Portfolio website</label>
          <input value={value.portfolio_website ?? ""} onChange={(e) => set("portfolio_website", e.target.value)} />
        </div>
        <div className="field">
          <label>Personal website / blog</label>
          <input value={value.personal_website ?? ""} onChange={(e) => set("personal_website", e.target.value)} />
        </div>
      </div>
      <div className="row">
        <div className="field">
          <label>Date of birth</label>
          <input type="date" value={value.date_of_birth ?? ""} onChange={(e) => set("date_of_birth", e.target.value)} />
        </div>
        <div className="field">
          <label>Nationality</label>
          <input value={value.nationality ?? ""} onChange={(e) => set("nationality", e.target.value)} />
        </div>
        <div className="field">
          <label>Work authorization / visa status</label>
          <input value={value.work_authorization ?? ""} onChange={(e) => set("work_authorization", e.target.value)} />
        </div>
      </div>
    </div>
  );
}
