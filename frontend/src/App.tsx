import { Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "@/auth/guards";
import { AppLayout } from "@/components/AppLayout";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PlaceholderPage } from "@/pages/PlaceholderPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route
            index
            element={
              <PlaceholderPage
                title="Dashboard"
                description="Open incidents, SLA status and trends will appear here."
              />
            }
          />
          <Route
            path="incidents/*"
            element={
              <PlaceholderPage
                title="Incidents"
                description="Search, filter and manage incidents here."
              />
            }
          />
          <Route element={<RequireRole roles={["admin", "engineer"]} />}>
            <Route
              path="reports"
              element={
                <PlaceholderPage title="Reports" description="Daily and weekly incident reports." />
              }
            />
          </Route>
          <Route element={<RequireRole roles={["admin"]} />}>
            <Route
              path="users"
              element={
                <PlaceholderPage title="Users" description="Manage accounts and roles here." />
              }
            />
            <Route
              path="settings/sla"
              element={
                <PlaceholderPage
                  title="SLA policies"
                  description="Response and resolution targets per priority."
                />
              }
            />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
