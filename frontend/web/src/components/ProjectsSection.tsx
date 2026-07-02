import type { ProjectItem } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";
import { BulletListField } from "./BulletListField";

export function ProjectsSection({
  items,
  onChange,
}: {
  items: ProjectItem[];
  onChange: (next: ProjectItem[]) => void;
}) {
  function add() {
    onChange([...items, { project_name: "", details: [], demo_url: "", github_url: "", display_order: items.length }]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
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
          <div className="row">
            <div className="field">
              <label>Demo URL</label>
              <input value={item.demo_url ?? ""} onChange={(e) => onChange(updateAt(items, i, { demo_url: e.target.value }))} />
            </div>
            <div className="field">
              <label>GitHub URL</label>
              <input
                value={item.github_url ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { github_url: e.target.value }))}
              />
            </div>
          </div>
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove project
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add personal project
      </button>
    </div>
  );
}
