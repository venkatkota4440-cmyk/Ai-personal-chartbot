import type { ApiErrorBody, ErrorCategory, FieldError } from "@shared/types";

const CSRF_COOKIE = "paa_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly category: ErrorCategory,
    message: string,
    readonly fields: FieldError[] = [],
    readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function fetchCsrfToken(): Promise<string> {
  const response = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  if (!response.ok) throw await toApiError(response);
  const body = (await response.json()) as { csrf_token: string };
  return body.csrf_token;
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const { category, message, fields, request_id } = body.error;
    return new ApiError(response.status, category, message, fields ?? [], request_id);
  } catch {
    return new ApiError(response.status, "internal_error", "The server returned an unexpected response");
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Sent as Idempotency-Key, so a retried request cannot start a second automation run. */
  idempotencyKey?: string;
}

/**
 * Typed JSON fetch against our own origin. Adds the CSRF header on state-changing requests and
 * turns every failure, including network errors, into an ApiError so screens never fail silently.
 */
export async function api<T>(
  path: string,
  { method = "GET", body, signal, idempotencyKey }: RequestOptions = {},
): Promise<T> {
  const send = async (csrfToken: string | null): Promise<Response> => {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (csrfToken) headers[CSRF_HEADER] = csrfToken;
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    return fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
  };

  try {
    const needsCsrf = UNSAFE_METHODS.has(method);
    let token = needsCsrf ? (readCookie(CSRF_COOKIE) ?? (await fetchCsrfToken())) : null;
    let response = await send(token);

    // A stale token (e.g. after the server secret rotated) is refreshed once, then we give up.
    if (needsCsrf && response.status === 403) {
      const error = await toApiError(response.clone());
      if (error.category === "csrf_failed") {
        token = await fetchCsrfToken();
        response = await send(token);
      }
    }

    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
}

/** Only allow same-site relative redirects after sign-in (prevents open redirects). */
export function safeNextPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}
