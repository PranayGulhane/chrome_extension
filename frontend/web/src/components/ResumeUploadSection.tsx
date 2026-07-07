import { useRef, useState } from "react";
import type { ResumeUploadResponse } from "../api/types";

interface Props {
  existingResume: ResumeUploadResponse | null;
  canUpload: boolean;
  disabledHint?: string;
  onUpload: (file: File) => Promise<void>;
}

export function ResumeUploadSection({ existingResume, canUpload, disabledHint, onUpload }: Props) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await onUpload(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse this resume.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontWeight: 700 }}>Resume</div>
          {existingResume ? (
            <div className="muted">Active: {existingResume.original_filename}</div>
          ) : (
            <div className="muted">Upload a PDF resume to auto-fill the sections below.</div>
          )}
          {!canUpload && disabledHint && <div className="muted">{disabledHint}</div>}
        </div>
        <button
          className="btn btn-secondary"
          disabled={!canUpload || uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? "Parsing…" : existingResume ? "Replace resume" : "Upload resume"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={handleFileChange}
        />
      </div>
      {error && <p className="error-text" style={{ marginTop: 12, marginBottom: 0 }}>{error}</p>}
    </div>
  );
}
