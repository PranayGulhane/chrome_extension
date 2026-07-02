import type { AchievementItem } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";
import { BulletListField } from "./BulletListField";

export function AchievementsSection({
  items,
  onChange,
}: {
  items: AchievementItem[];
  onChange: (next: AchievementItem[]) => void;
}) {
  function add() {
    onChange([...items, { achievement_title: "", description: [], display_order: items.length }]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="repeatable-row" key={i}>
          <div className="row">
            <div className="field">
              <label>Achievement title</label>
              <input
                value={item.achievement_title}
                onChange={(e) => onChange(updateAt(items, i, { achievement_title: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Organization</label>
              <input
                value={item.organization ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { organization: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Date</label>
              <input
                type="date"
                value={item.date_achieved ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { date_achieved: e.target.value }))}
              />
            </div>
          </div>
          <BulletListField
            label="Description"
            value={item.description}
            onChange={(description) => onChange(updateAt(items, i, { description }))}
          />
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove achievement
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add achievement
      </button>
    </div>
  );
}
