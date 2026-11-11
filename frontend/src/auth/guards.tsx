import { Navigate, Outlet, useLocation } from "react-router-dom";

import type { Role } from "@/api/types";
import { FullPageMessage } from "@/components/FullPageMessage";
import { Spinner } from "@/components/Spinner";

import { useAuth } from "./context";
import { hasRole } from "./roles";

/** Renders child routes only for a signed-in user; otherwise sends them to /login. */
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <FullPageMessage title="Loading OpsDesk">
        <Spinner />
      </FullPageMessage>
    );
  }
  if (status === "unavailable") {
    return (
      <FullPageMessage title="Sign-in is temporarily unavailable">
        <p>The OpsDesk API could not be reached. Your session is safe.</p>
        <button type="button" className="btn-primary mt-4" onClick={retry}>
          Try again
        </button>
      </FullPageMessage>
    );
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

/** Renders child routes only for the given roles; others see a 403 page. */
export function RequireRole({ roles }: { roles: readonly Role[] }) {
  const { user } = useAuth();
  if (!hasRole(user, roles)) {
    return (
      <FullPageMessage title="You don't have access to this page" embedded>
        <p>Ask an Admin if you need it.</p>
      </FullPageMessage>
    );
  }
  return <Outlet />;
}
