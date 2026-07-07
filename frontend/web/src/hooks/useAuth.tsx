import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import * as authApi from "../api/auth";
import type { AuthUser } from "../api/types";

interface AuthContextValue {
  user: AuthUser | null;
  status: "loading" | "ready";
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, inviteCode: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<"loading" | "ready">("loading");

  useEffect(() => {
    // Session lives in the httpOnly cookie set by the backend — on first load we just ask
    // /auth/me whether one exists, rather than trying to inspect it ourselves (we can't; that's
    // the point of httpOnly).
    authApi
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setStatus("ready"));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setUser(await authApi.login(email, password));
  }, []);

  const signup = useCallback(async (email: string, password: string, inviteCode: string) => {
    setUser(await authApi.signup(email, password, inviteCode));
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, status, login, signup, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
