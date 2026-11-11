import { Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "@/auth/guards";
import { AppLayout } from "@/components/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { ReportDetailPage } from "@/pages/ReportDetailPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SlaPoliciesPage } from "@/pages/admin/SlaPoliciesPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import { IncidentDetailPage } from "@/pages/incidents/IncidentDetailPage";
import { IncidentsPage } from "@/pages/incidents/IncidentsPage";
import { NewIncidentPage } from "@/pages/incidents/NewIncidentPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/:id" element={<IncidentDetailPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route element={<RequireRole roles={["admin", "engineer"]} />}>
            <Route path="incidents/new" element={<NewIncidentPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="reports/:id" element={<ReportDetailPage />} />
          </Route>
          <Route element={<RequireRole roles={["admin"]} />}>
            <Route path="users" element={<UsersPage />} />
            <Route path="settings/sla" element={<SlaPoliciesPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
