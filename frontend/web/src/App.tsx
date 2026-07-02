import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ProtectedLayout } from "./components/ProtectedLayout";
import { AuthProvider } from "./hooks/useAuth";
import { LoginPage } from "./pages/LoginPage";
import { ProfileEditorPage } from "./pages/ProfileEditorPage";
import { ProfileViewPage } from "./pages/ProfileViewPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { SignupPage } from "./pages/SignupPage";

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
          </Route>
          <Route path="*" element={<Navigate to="/profiles" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
