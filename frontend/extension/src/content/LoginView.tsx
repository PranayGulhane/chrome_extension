import { useState } from "react";
import type { AuthUser, ContentToBackgroundMessage, LoginResponse } from "../shared/types";

export function LoginView({ onLoggedIn }: { onLoggedIn: (user: AuthUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const message: ContentToBackgroundMessage = { type: "LOGIN", email, password };
    const response = (await chrome.runtime.sendMessage(message)) as LoginResponse;
    setSubmitting(false);
    if (response.ok) {
      onLoggedIn(response.user);
    } else {
      setError(response.error);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="lja-email">Email</label>
        <input
          id="lja-email"
          type="email"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="lja-password">Password</label>
        <input
          id="lja-password"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {error && <p className="error-text">{error}</p>}
      <button className="btn-primary" type="submit" disabled={submitting}>
        {submitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
