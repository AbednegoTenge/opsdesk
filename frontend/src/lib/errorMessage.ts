import { ApiError, NetworkError } from "@/api/errors";

/** A sentence a person can act on, for any error the API client throws. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "You don't have permission to do that.";
    if (error.status === 404) return "Not found. It may have been deleted.";
    if (error.status === 429) return "Too many attempts. Wait a minute and try again.";
    if (error.status >= 500) return "The server had a problem. Try again shortly.";
    const fields = Object.entries(error.fieldErrors);
    if (fields.length) return fields.map(([f, m]) => `${f}: ${m.join(" ")}`).join(" ");
    return error.message;
  }
  if (error instanceof NetworkError) return error.message;
  return "Something went wrong.";
}
