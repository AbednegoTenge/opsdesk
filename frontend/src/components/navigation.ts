import type { Role } from "@/api/types";

export type NavItem = { to: string; label: string; roles?: readonly Role[] };

/** Main navigation. Items with `roles` are hidden from everyone else. */
export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Dashboard" },
  { to: "/incidents", label: "Incidents" },
  { to: "/reports", label: "Reports", roles: ["admin", "engineer"] },
  { to: "/users", label: "Users", roles: ["admin"] },
  { to: "/settings/sla", label: "SLA policies", roles: ["admin"] },
];
