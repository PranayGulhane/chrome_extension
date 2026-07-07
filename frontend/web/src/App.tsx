import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminRoute } from "./components/AdminRoute";
import { ProtectedLayout } from "./components/ProtectedLayout";
import { AuthProvider } from "./hooks/useAuth";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MetricsPage } from "./pages/MetricsPage";
import { ProfileEditorPage } from "./pages/ProfileEditorPage";
import { ProfileViewPage } from "./pages/ProfileViewPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { SignupPage } from "./pages/SignupPage";
import { TrackerDetailPage } from "./pages/TrackerDetailPage";
import { TrackerPage } from "./pages/TrackerPage";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/profiles" element={<ProfilesPage />} />
            <Route path="/profiles/:id/view" element={<ProfileViewPage />} />
            <Route path="/profiles/:id" element={<ProfileEditorPage />} />
            <Route path="/tracker" element={<TrackerPage />} />
            <Route path="/tracker/:id" element={<TrackerDetailPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route element={<AdminRoute />}>
              <Route path="/admin" element={<AdminDashboardPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/profiles" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
