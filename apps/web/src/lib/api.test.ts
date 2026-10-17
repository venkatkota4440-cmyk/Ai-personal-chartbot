import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, safeNextPath } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("safeNextPath", () => {
  it.each([
    [null, "/"],
    ["/settings", "/settings"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["settings", "/"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });
});

describe("api", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    document.cookie = "paa_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("sends the CSRF cookie value as a header on state-changing requests", async () => {
    document.cookie = "paa_csrf=nonce.sig";
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    await api("/api/settings", { method: "PATCH", body: { timezone: "UTC" } });
    const init = fetchMock.mock.calls[0]?.[1];
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("nonce.sig");
    expect(init?.credentials).toBe("same-origin");
  });

  it("does not send a CSRF header on GET", async () => {
    document.cookie = "paa_csrf=nonce.sig";
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await api("/api/auth/me");
    const init = fetchMock.mock.calls[0]?.[1];
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });

  it("fetches a CSRF token first when the cookie is missing", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { csrf_token: "fresh.token" }))
      .mockResolvedValueOnce(jsonResponse(201, { id: "u1" }));
    await api("/api/auth/register", { method: "POST", body: {} });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/csrf");
    const init = fetchMock.mock.calls[1]?.[1];
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("fresh.token");
  });

  it("turns structured API errors into ApiError with fields", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(422, {
        error: {
          category: "validation_error",
          message: "Request validation failed",
          request_id: "req-1",
          fields: [{ field: "timezone", message: "Unknown timezone" }],
        },
      }),
    );
    const error = await api("/api/settings").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).category).toBe("validation_error");
    expect((error as ApiError).fields[0]?.field).toBe("timezone");
    expect((error as ApiError).requestId).toBe("req-1");
  });

  it("reports network failures instead of failing silently", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const error = await api("/api/health").catch((e: unknown) => e);
    expect((error as ApiError).category).toBe("network_error");
    expect((error as ApiError).status).toBe(0);
  });

  it("retries once with a fresh token after a CSRF failure", async () => {
    document.cookie = "paa_csrf=stale.token";
    fetchMock
      .mockResolvedValueOnce(jsonResponse(403, { error: { category: "csrf_failed", message: "x", request_id: null } }))
      .mockResolvedValueOnce(jsonResponse(200, { csrf_token: "new.token" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    await expect(api("/api/settings", { method: "PATCH", body: {} })).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
