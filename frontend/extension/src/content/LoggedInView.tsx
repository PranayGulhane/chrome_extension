import { useState } from "react";
import type { AuthUser, ContentToBackgroundMessage, LogoutResponse } from "../shared/types";

export function LoggedInView({ user, onLoggedOut }: { user: AuthUser; onLoggedOut: () => void }) {
  const [submitting, setSubmitting] = useState(false);

  async function handleLogout() {
    setSubmitting(true);
    const message: ContentToBackgroundMessage = { type: "LOGOUT" };
    await (chrome.runtime.sendMessage(message) as Promise<LogoutResponse>);
    setSubmitting(false);
    onLoggedOut();
  }

  return (
    <div>
      <div className="user-row">
        <span className="email">{user.email}</span>
        <span className="role">{user.role}</span>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>
        You're signed in. Post extraction, email drafting, Gmail sending, and the application
        tracker are being built out feature by feature — they'll show up here as they land.
      </p>
      <button className="btn-secondary" onClick={handleLogout} disabled={submitting}>
        {submitting ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
