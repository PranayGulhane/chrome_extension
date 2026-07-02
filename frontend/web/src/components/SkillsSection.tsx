import { useState } from "react";
import type { SkillItem } from "../api/types";

// Skills are edited grouped by section (category) — one section-name input, with the skills in
// that section listed underneath — matching the PRD's "Cloud -> AWS, GCP" model. The flat
// SkillItem[] the backend expects is just category+skill_name+display_order pairs, so sections
// only exist as a grouping *of that flat list* for editing purposes, not as their own entity.
//
// Section identity is a local-only key, not the category text itself — grouping purely by the
// current text would make two sections visually merge the instant their names happened to match
// mid-edit (e.g. typing a new section name that transiently collides with an existing one).
// Local state is seeded from `items` once and only pushed *out* via onChange, never re-derived
// from the prop afterward — same reasoning as BulletListField, to avoid fighting the user's typing.

interface Skill {
  key: string;
  skill_name: string;
}
interface Section {
  key: string;
  category: string;
  skills: Skill[];
}

function makeKey(): string {
  return Math.random().toString(36).slice(2);
}

function groupIntoSections(items: SkillItem[]): Section[] {
  const order: string[] = [];
  const byCategory = new Map<string, SkillItem[]>();
  for (const item of items) {
    if (!byCategory.has(item.category)) {
      order.push(item.category);
      byCategory.set(item.category, []);
    }
    byCategory.get(item.category)!.push(item);
  }
  if (order.length === 0) return [{ key: makeKey(), category: "", skills: [{ key: makeKey(), skill_name: "" }] }];
  return order.map((category) => ({
    key: makeKey(),
    category,
    skills: byCategory.get(category)!.map((s) => ({ key: makeKey(), skill_name: s.skill_name })),
  }));
}

function flattenSections(sections: Section[]): SkillItem[] {
  const flat: SkillItem[] = [];
  let displayOrder = 0;
  for (const section of sections) {
    for (const skill of section.skills) {
      flat.push({ category: section.category, skill_name: skill.skill_name, display_order: displayOrder++ });
    }
  }
  return flat;
}

export function SkillsSection({ items, onChange }: { items: SkillItem[]; onChange: (next: SkillItem[]) => void }) {
  const [sections, setSections] = useState<Section[]>(() => groupIntoSections(items));

  function commit(next: Section[]) {
    setSections(next);
    onChange(flattenSections(next));
  }

  function addSection() {
    commit([...sections, { key: makeKey(), category: "", skills: [{ key: makeKey(), skill_name: "" }] }]);
  }

  function removeSection(sectionIndex: number) {
    commit(sections.filter((_, i) => i !== sectionIndex));
  }

  function renameSection(sectionIndex: number, category: string) {
    commit(sections.map((s, i) => (i === sectionIndex ? { ...s, category } : s)));
  }

  function addSkill(sectionIndex: number) {
    commit(
      sections.map((s, i) => (i === sectionIndex ? { ...s, skills: [...s.skills, { key: makeKey(), skill_name: "" }] } : s)),
    );
  }

  function updateSkill(sectionIndex: number, skillIndex: number, skill_name: string) {
    commit(
      sections.map((s, i) =>
        i === sectionIndex ? { ...s, skills: s.skills.map((sk, j) => (j === skillIndex ? { ...sk, skill_name } : sk)) } : s,
      ),
    );
  }

  function removeSkill(sectionIndex: number, skillIndex: number) {
    commit(
      sections.map((s, i) => (i === sectionIndex ? { ...s, skills: s.skills.filter((_, j) => j !== skillIndex) } : s)),
    );
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {sections.map((section, si) => (
        <div className="repeatable-row" key={section.key}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div className="field" style={{ marginBottom: 0, flex: 1 }}>
              <label>Section name (e.g. Cloud)</label>
              <input value={section.category} onChange={(e) => renameSection(si, e.target.value)} />
            </div>
            <button className="btn btn-danger" type="button" onClick={() => removeSection(si)}>
              Remove section
            </button>
          </div>
          <div style={{ marginTop: 10 }}>
            {section.skills.map((skill, ski) => (
              <div key={skill.key} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span aria-hidden="true">•</span>
                <input
                  style={{ flex: 1 }}
                  placeholder="Skill (e.g. AWS)"
                  value={skill.skill_name}
                  onChange={(e) => updateSkill(si, ski, e.target.value)}
                />
                <button className="btn btn-secondary" type="button" onClick={() => removeSkill(si, ski)}>
                  Remove
                </button>
              </div>
            ))}
            <button className="link-button" type="button" onClick={() => addSkill(si)}>
              + Add skill
            </button>
          </div>
        </div>
      ))}
      <button className="link-button" type="button" onClick={addSection}>
        + Add section
      </button>
    </div>
  );
}
