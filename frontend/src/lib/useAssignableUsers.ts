import { useQuery } from "@tanstack/react-query";

import { keys, users } from "@/api/resources";
import { useAuth } from "@/auth/context";
import { canEditIncidents } from "@/auth/roles";

/** Active Engineers and Admins: the people an incident can be assigned to. */
export function useAssignableUsers() {
  const { user } = useAuth();
  return useQuery({
    queryKey: keys.assignableUsers,
    queryFn: async () => {
      const page = await users.list({ is_active: "true", page_size: 100 });
      return page.results.filter((u) => u.role !== "viewer");
    },
    // Viewers can't assign, and the API doesn't let them list users.
    enabled: canEditIncidents(user),
    staleTime: 5 * 60_000,
  });
}
