import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { auth, refreshSession } from "@/api/client";
import { session } from "@/api/session";
import type { User } from "@/api/types";

import { AuthContext, type AuthContextValue, type AuthStatus } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(session.get()?.user ?? null);
  const [attempt, setAttempt] = useState(0);

  // Keep React state in step with the session, which the API client can end on its own
  // (for example when a refresh is rejected mid-request).
  useEffect(
    () =>
      session.subscribe((next) => {
        setUser(next?.user ?? null);
        if (next) {
          setStatus("authenticated");
        } else {
          setStatus((prev) => (prev === "loading" ? prev : "anonymous"));
          queryClient.clear();
        }
      }),
    [queryClient],
  );

  // Restore the session from the refresh cookie on first load (and on "Try again").
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    refreshSession()
      .then((restored) => {
        if (!cancelled) setStatus(restored ? "authenticated" : "anonymous");
      })
      .catch(() => {
        if (!cancelled) setStatus("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const login = useCallback(async (email: string, password: string) => {
    await auth.login(email, password);
  }, []);

  const logout = useCallback(async () => {
    await auth.logout();
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, logout, retry }),
    [status, user, login, logout, retry],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
