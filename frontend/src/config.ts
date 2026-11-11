/**
 * Where the API lives. Runtime config (public/config.js) wins over the build-time
 * VITE_API_BASE_URL, so one build can be promoted through every environment.
 */
export function apiBaseUrl(): string {
  const runtime = typeof window !== "undefined" ? window.__OPSDESK_CONFIG__?.apiBaseUrl : undefined;
  const base = runtime || import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return base.replace(/\/+$/, "");
}
