// One input row per bullet, not a multi-line textarea — looks like an actual bullet list while
// editing, and each row is a single controlled value so there's no delimiter-parsing to fight
// (unlike the comma-separated preferred-locations bug: every keystroke here is already in its
// final, canonical form for that one row).
export function BulletListField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (lines: string[]) => void;
}) {
  function updateLine(i: number, text: string) {
    onChange(value.map((v, idx) => (idx === i ? text : v)));
  }
  function removeLine(i: number) {
    onChange(value.filter((_, idx) => idx !== i));
  }
  function addLine() {
    onChange([...value, ""]);
  }

  return (
    <div className="field">
      <label>{label}</label>
      {value.map((line, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <span aria-hidden="true">•</span>
          <input style={{ flex: 1 }} value={line} onChange={(e) => updateLine(i, e.target.value)} />
          <button className="btn btn-secondary" type="button" onClick={() => removeLine(i)}>
            Remove
          </button>
        </div>
      ))}
      <button className="link-button" type="button" onClick={addLine}>
        + Add {label.toLowerCase()} item
      </button>
    </div>
  );
}
