import { Link, Navigate, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function ProtectedLayout() {
  const { user, status, logout } = useAuth();
  const navigate = useNavigate();

  if (status === "loading") return null;
  if (!user) return <Navigate to="/login" replace />;

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div>
      <div className="topbar">
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <span className="brand">LinkedIn Job Outreach Assistant</span>
          <Link to="/profiles" className="muted">
            Profiles
          </Link>
          <Link to="/tracker" className="muted">
            Tracker
          </Link>
          <Link to="/metrics" className="muted">
            Usage
          </Link>
          {user.role === "admin" && (
            <Link to="/admin" className="muted">
              Admin
            </Link>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className="muted">
            {user.email} · <span className="badge">{user.role}</span>
          </span>
          <button className="btn btn-secondary" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </div>
      <Outlet />
    </div>
  );
}
