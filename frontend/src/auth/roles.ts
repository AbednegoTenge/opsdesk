import type { Role, User } from "@/api/types";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  engineer: "Engineer",
  viewer: "Viewer",
};

/** Mirrors the API's permission classes. The API still enforces every rule. */
export function hasRole(user: User | null | undefined, roles: readonly Role[]): boolean {
  return !!user?.role && roles.includes(user.role);
}

export const isAdmin = (user: User | null | undefined) => hasRole(user, ["admin"]);
export const canEditIncidents = (user: User | null | undefined) =>
  hasRole(user, ["admin", "engineer"]);
