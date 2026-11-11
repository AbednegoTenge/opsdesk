import { createContext, useContext } from "react";

import type { User } from "@/api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous" | "unavailable";

export type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
