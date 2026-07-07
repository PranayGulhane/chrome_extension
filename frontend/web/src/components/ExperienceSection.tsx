import type { ExperienceItem, ExperienceProjectItem } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";
import { BulletListField } from "./BulletListField";

function ExperienceProjectsSubsection({
  items,
  onChange,
}: {
  items: ExperienceProjectItem[];
  onChange: (next: ExperienceProjectItem[]) => void;
}) {
  function add() {
    onChange([...items, { project_name: "", details: [], display_order: items.length }]);
  }

  return (
    <div style={{ marginTop: 10, paddingLeft: 14, borderLeft: "2px solid var(--border)" }}>
      <div className="muted" style={{ marginBottom: 8, fontWeight: 600 }}>
        Projects within this role
      </div>
      {items.map((item, i) => (
        <div className="repeatable-row" key={i}>
          <div className="field">
            <label>Project name</label>
            <input
              value={item.project_name}
              onChange={(e) => onChange(updateAt(items, i, { project_name: e.target.value }))}
            />
          </div>
          <BulletListField
            label="Details"
            value={item.details}
            onChange={(details) => onChange(updateAt(items, i, { details }))}
          />
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove project
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add project
      </button>
    </div>
  );
}

export function ExperienceSection({
  items,
  onChange,
}: {
  items: ExperienceItem[];
  onChange: (next: ExperienceItem[]) => void;
}) {
  function add() {
    onChange([
      ...items,
      {
        job_title: "",
        company_name: "",
        currently_working_here: false,
        responsibilities: [],
        display_order: items.length,
        projects: [],
      },
    ]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="repeatable-row" key={i}>
          <div className="row">
            <div className="field">
              <label>Job title</label>
              <input value={item.job_title} onChange={(e) => onChange(updateAt(items, i, { job_title: e.target.value }))} />
            </div>
            <div className="field">
              <label>Company</label>
              <input
                value={item.company_name}
                onChange={(e) => onChange(updateAt(items, i, { company_name: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Employment type</label>
              <input
                value={item.employment_type ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { employment_type: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Location</label>
              <input value={item.location ?? ""} onChange={(e) => onChange(updateAt(items, i, { location: e.target.value }))} />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Start date</label>
              <input
                type="date"
                value={item.start_date ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { start_date: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>End date</label>
              <input
                type="date"
                disabled={item.currently_working_here}
                value={item.end_date ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { end_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="field">
            <label>
              <input
                type="checkbox"
                checked={item.currently_working_here}
                onChange={(e) =>
                  onChange(updateAt(items, i, { currently_working_here: e.target.checked, end_date: null }))
                }
                style={{ marginRight: 6 }}
              />
              Currently working here
            </label>
          </div>
          <BulletListField
            label="Responsibilities"
            value={item.responsibilities}
            onChange={(responsibilities) => onChange(updateAt(items, i, { responsibilities }))}
          />
          <ExperienceProjectsSubsection
            items={item.projects}
            onChange={(projects) => onChange(updateAt(items, i, { projects }))}
          />
          <button className="btn btn-danger" type="button" style={{ marginTop: 12 }} onClick={() => onChange(removeAt(items, i))}>
            Remove experience
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add experience
      </button>
    </div>
  );
}
