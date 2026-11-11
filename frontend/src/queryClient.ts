import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/errors";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        // Retry network blips and 5xx (e.g. a replica restarting), never 4xx.
        retry: (failureCount, error) =>
          failureCount < 2 && !(error instanceof ApiError && error.status < 500),
      },
    },
  });
}
