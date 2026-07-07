import { useEffect, useState, useSyncExternalStore } from "react";
import { LoggedInView } from "./LoggedInView";
import { LoginView } from "./LoginView";
import { panelStore } from "./panelStore";
import type { AuthStateResponse, AuthUser, ContentToBackgroundMessage } from "../shared/types";

type AuthState = { status: "loading" } | { status: "unauthenticated" } | { status: "authenticated"; user: AuthUser };

export function App() {
  const visible = useSyncExternalStore(panelStore.subscribe, panelStore.getSnapshot);
  const [authState, setAuthState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    if (!visible) return;
    setAuthState({ status: "loading" });
    const message: ContentToBackgroundMessage = { type: "GET_AUTH_STATE" };
    chrome.runtime.sendMessage(message).then((response: AuthStateResponse) => {
      setAuthState(
        response.authenticated ? { status: "authenticated", user: response.user } : { status: "unauthenticated" },
      );
    });
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="panel">
      <div className="panel-header">
        <span>LinkedIn Job Outreach Assistant</span>
        <button aria-label="Close panel" onClick={() => panelStore.close()}>
          ×
        </button>
      </div>
      <div className="panel-body">
        {authState.status === "loading" && <p className="muted">Loading…</p>}
        {authState.status === "unauthenticated" && (
          <LoginView onLoggedIn={(user) => setAuthState({ status: "authenticated", user })} />
        )}
        {authState.status === "authenticated" && (
          <LoggedInView user={authState.user} onLoggedOut={() => setAuthState({ status: "unauthenticated" })} />
        )}
      </div>
    </div>
  );
}
