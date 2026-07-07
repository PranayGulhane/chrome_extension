import type { CertificationItem } from "../api/types";
import { removeAt, updateAt } from "../utils/arrayEdit";

export function CertificationsSection({
  items,
  onChange,
}: {
  items: CertificationItem[];
  onChange: (next: CertificationItem[]) => void;
}) {
  function add() {
    onChange([...items, { certification_name: "", display_order: items.length }]);
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="repeatable-row" key={i}>
          <div className="row">
            <div className="field">
              <label>Certification name</label>
              <input
                value={item.certification_name}
                onChange={(e) => onChange(updateAt(items, i, { certification_name: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Issuing organization</label>
              <input
                value={item.issuing_organization ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { issuing_organization: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Issue date</label>
              <input
                type="date"
                value={item.issue_date ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { issue_date: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Expiry date</label>
              <input
                type="date"
                value={item.expiry_date ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { expiry_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Credential ID</label>
              <input
                value={item.credential_id ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { credential_id: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Credential URL</label>
              <input
                value={item.credential_url ?? ""}
                onChange={(e) => onChange(updateAt(items, i, { credential_url: e.target.value }))}
              />
            </div>
          </div>
          <button className="btn btn-danger" type="button" onClick={() => onChange(removeAt(items, i))}>
            Remove certification
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={add}>
        + Add certification
      </button>
    </div>
  );
}
