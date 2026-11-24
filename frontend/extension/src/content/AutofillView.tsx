import { useEffect, useState } from "react";
import { autofillForm, isProfileFieldKey } from "./formFiller";
import type { AutofillResult, ClassifyUnmatchedFn, ProfileFieldKey } from "./formFiller";
import type {
  ClassifyFieldsResponse,
  ContentToBackgroundMessage,
  GetProfileDetailResponse,
  GetProfilesResponse,
  ProfileSummary,
} from "../shared/types";

// Batches whatever content/formFiller.ts's heuristics couldn't confidently classify off to the
// backend's small Field Classifier agent (POST /profiles/classify-fields via the background
// worker — content scripts never call the backend directly, see service-worker.ts). Lives here
// rather than in formFiller.ts so that module stays a pure DOM/matching module with no
// chrome.runtime or network concerns, consistent with how GET_PROFILE_DETAIL is already handled.
const classifyUnmatched: ClassifyUnmatchedFn = async (fields) => {
  const message: ContentToBackgroundMessage = { type: "CLASSIFY_FIELDS", fields };
  const response = (await chrome.runtime.sendMessage(message)) as ClassifyFieldsResponse;
  const results = new Map<number, ProfileFieldKey | null>();
  if (!response.ok) return results;
  for (const match of response.matches) {
    if (isProfileFieldKey(match.key)) results.set(match.index, match.key);
  }
  return results;
};

type AutofillState =
  | { kind: "idle" }
  | { kind: "filling" }
  | { kind: "result"; result: AutofillResult }
  | { kind: "error"; message: string };

export function AutofillView() {
  const [profiles, setProfiles] = useState<ProfileSummary[] | null>(null);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [state, setState] = useState<AutofillState>({ kind: "idle" });

  useEffect(() => {
    const message: ContentToBackgroundMessage = { type: "GET_PROFILES" };
    chrome.runtime.sendMessage(message).then((response: GetProfilesResponse) => {
      if (!response.ok) {
        setProfilesError(response.error);
        return;
      }
      setProfiles(response.profiles);
      const defaultProfile = response.profiles.find((p) => p.is_default) ?? response.profiles[0];
      if (defaultProfile) setSelectedProfileId(defaultProfile.id);
    });
  }, []);

  async function handleFill() {
    setState({ kind: "filling" });
    const message: ContentToBackgroundMessage = { type: "GET_PROFILE_DETAIL", profileId: selectedProfileId };
    const response = (await chrome.runtime.sendMessage(message)) as GetProfileDetailResponse;
    if (!response.ok) {
      setState({ kind: "error", message: response.error });
      return;
    }
    // Runs directly in this page's DOM. Matching is heuristic-first (free, instant); whatever's
    // left unclassified gets escalated, in one batched call, to the small LLM fallback above — see
    // formFiller.ts for the full layered pipeline.
    const result = await autofillForm(response.profile, classifyUnmatched);
    setState({ kind: "result", result });
  }

  return (
    <div>
      <p className="muted">
        Fills known fields (name, email, phone, current employer, etc.) on this page from your saved
        profile — including differently-worded versions of the same question (a small AI model
        helps recognize those). Filled fields are outlined green — review everything before you
        submit; nothing is ever submitted automatically. Open-ended questions are left untouched.
      </p>

      <div className="field" style={{ marginTop: 8 }}>
        <label>Profile to use</label>
        {profilesError && <p className="error-text">{profilesError}</p>}
        {profiles && profiles.length === 0 && (
          <p className="notice-text">No saved profiles yet — create one in the Web app first.</p>
        )}
        {profiles && profiles.length > 0 && (
          <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.target_job_title}
                {p.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      <button
        className="btn-primary"
        onClick={handleFill}
        disabled={state.kind === "filling" || !selectedProfileId}
        style={{ marginTop: 8 }}
      >
        {state.kind === "filling" ? "Filling…" : "Fill this page"}
      </button>

      {state.kind === "error" && <p className="error-text">{state.message}</p>}

      {state.kind === "result" && (
        <div style={{ marginTop: 12 }}>
          <p className="success-text">
            Filled {state.result.filled.length} of {state.result.total} recognized fields ({state.result.fieldsOnPage}{" "}
            fields found on this page).
          </p>
          {state.result.skipped.length > 0 && (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
              <p className="muted">Not filled (no matching value on this profile) — fill these in yourself:</p>
              {state.result.skipped.map((item, i) => (
                <span key={i} className="muted">
                  • {item.label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
