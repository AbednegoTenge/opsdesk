import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/context";
import { ROLE_LABELS, hasRole } from "@/auth/roles";

import { NAV_ITEMS } from "./navigation";

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  const items = NAV_ITEMS.filter((item) => !item.roles || hasRole(user, item.roles));

  async function handleLogout() {
    setSigningOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
          <span className="text-lg font-semibold text-indigo-600">OpsDesk</span>
          <nav aria-label="Main" className="flex flex-1 gap-1 overflow-x-auto">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          {user && (
            <div className="flex items-center gap-3">
              <div className="hidden text-right sm:block">
                <div className="text-sm font-medium text-slate-900">
                  {user.full_name || user.email}
                </div>
                <div className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</div>
              </div>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleLogout}
                disabled={signingOut}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
