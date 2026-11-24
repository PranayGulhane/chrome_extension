import { useState } from "react";
import { AutofillView } from "./AutofillView";
import { HistoryView } from "./HistoryView";
import { HomeView } from "./HomeView";
import { ManageGmailView } from "./ManageGmailView";
import { UsageView } from "./UsageView";
import type { AuthUser, ContentToBackgroundMessage, LogoutResponse, OpenWebAppResponse } from "../shared/types";

export function LoggedInView({ user, onLoggedOut }: { user: AuthUser; onLoggedOut: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState<"extract" | "history" | "usage" | "autofill" | "gmail">("extract");

  async function handleLogout() {
    setSubmitting(true);
    const message: ContentToBackgroundMessage = { type: "LOGOUT" };
    await (chrome.runtime.sendMessage(message) as Promise<LogoutResponse>);
    setSubmitting(false);
    onLoggedOut();
  }

  async function handleOpenWebApp() {
    const message: ContentToBackgroundMessage = { type: "OPEN_WEB_APP" };
    await (chrome.runtime.sendMessage(message) as Promise<OpenWebAppResponse>);
  }

  return (
    <div>
      <div className="user-row">
        <span className="email">{user.email}</span>
        <span className="role">{user.role}</span>
        <button className="link-button" onClick={handleOpenWebApp} style={{ alignSelf: "flex-start" }}>
          Open web app ↗
        </button>
      </div>
      <div className="tab-row">
        <button className={tab === "extract" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("extract")}>
          Extract
        </button>
        <button className={tab === "history" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("history")}>
          History
        </button>
        <button className={tab === "usage" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("usage")}>
          Usage
        </button>
        <button className={tab === "autofill" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("autofill")}>
          Autofill
        </button>
        <button className={tab === "gmail" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("gmail")}>
          Gmail
        </button>
      </div>
      {tab === "extract" && <HomeView />}
      {tab === "history" && <HistoryView />}
      {tab === "usage" && <UsageView />}
      {tab === "autofill" && <AutofillView />}
      {tab === "gmail" && <ManageGmailView />}
      <button className="btn-secondary" onClick={handleLogout} disabled={submitting} style={{ marginTop: 16 }}>
        {submitting ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
