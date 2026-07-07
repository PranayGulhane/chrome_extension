import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function AdminRoute() {
  const { user, status } = useAuth();

  if (status === "loading") return null;
  if (user?.role !== "admin") return <Navigate to="/profiles" replace />;

  return <Outlet />;
}
