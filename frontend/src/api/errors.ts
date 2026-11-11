/** An error answer from the API, decoded from its {"error": {...}} envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field errors from a 400 validation response, as {field: [messages]}. */
  get fieldErrors(): Record<string, string[]> {
    if (this.code !== "validation_error" || !this.details || typeof this.details !== "object") {
      return {};
    }
    const out: Record<string, string[]> = {};
    for (const [field, value] of Object.entries(this.details as Record<string, unknown>)) {
      out[field] = Array.isArray(value) ? value.map(String) : [String(value)];
    }
    return out;
  }
}

/** The request never got an HTTP answer (offline, DNS, CORS, connection reset). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("Could not reach the OpsDesk API. Check your connection and try again.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // not JSON (e.g. a proxy's HTML error page)
  }
  const envelope = (body as { error?: { code?: string; message?: string; details?: unknown } })
    ?.error;
  return new ApiError(
    response.status,
    envelope?.code ?? `http_${response.status}`,
    envelope?.message ?? (response.statusText || `Request failed with status ${response.status}`),
    envelope?.details ?? null,
  );
}
