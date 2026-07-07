import type { EducationItem } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";

export function EducationSection({
  items,
  onChange,
}: {
  items: EducationItem[];
  onChange: (next: EducationItem[]) => void;
}) {
  function add() {
    onChange([
      ...items,
      { degree: "", institution_name: "", field_of_study: "", display_order: items.length },
    ]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="repeatable-row" key={i}>
          <div className="row">
            <div className="field">
              <label>Degree</label>
              <input value={item.degree} onChange={(e) => onChange(updateAt(items, i, { degree: e.target.value }))} />
            </div>
            <div className="field">
              <label>Field of study</label>
              <input
                value={item.field_of_study ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { field_of_study: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Minor / specialization</label>
              <input value={item.minor ?? ""} onChange={(e) => onChange(updateAt(items, i, { minor: e.target.value }))} />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Institution</label>
              <input
                value={item.institution_name}
                onChange={(e) => onChange(updateAt(items, i, { institution_name: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>University / board</label>
              <input
                value={item.university_board ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { university_board: e.target.value }))}
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
                value={item.end_date ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { end_date: e.target.value }))}
              />
            </div>
            {/* Redundant once an end date is set — the end date already implies the graduation year. */}
            {!item.end_date && (
              <div className="field">
                <label>Graduation year</label>
                <input
                  type="number"
                  value={item.graduation_year ?? ""}
                  onChange={(e) => onChange(updateAt(items, i, { graduation_year: Number(e.target.value) || null }))}
                />
              </div>
            )}
          </div>
          <div className="row">
            <div className="field">
              <label>CGPA / GPA / Percentage</label>
              <input value={item.gpa ?? ""} onChange={(e) => onChange(updateAt(items, i, { gpa: e.target.value }))} />
            </div>
            <div className="field">
              <label>Honors / distinction</label>
              <input value={item.honors ?? ""} onChange={(e) => onChange(updateAt(items, i, { honors: e.target.value }))} />
            </div>
          </div>
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove education
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add education
      </button>
    </div>
  );
}
