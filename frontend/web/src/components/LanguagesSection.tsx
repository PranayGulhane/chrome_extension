import type { LanguageItem, LanguageProficiency } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";

const PROFICIENCIES: LanguageProficiency[] = ["native", "fluent", "professional", "intermediate", "basic"];

export function LanguagesSection({
  items,
  onChange,
}: {
  items: LanguageItem[];
  onChange: (next: LanguageItem[]) => void;
}) {
  function add() {
    onChange([...items, { language: "", proficiency: "professional", display_order: items.length }]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="row" key={i} style={{ marginBottom: 10, alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Language</label>
            <input value={item.language} onChange={(e) => onChange(updateAt(items, i, { language: e.target.value }))} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Proficiency</label>
            <select
              value={item.proficiency}
              onChange={(e) => onChange(updateAt(items, i, { proficiency: e.target.value as LanguageProficiency }))}
            >
              {PROFICIENCIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add language
      </button>
    </div>
  );
}
