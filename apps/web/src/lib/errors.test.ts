import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import { messageWasSaved, toApiError } from "@/lib/errors";

describe("messageWasSaved", () => {
  it("is true only for AI failures, which happen after the message is stored", () => {
    expect(messageWasSaved(new ApiError(503, "ai_unavailable", "x"))).toBe(true);
    expect(messageWasSaved(new ApiError(502, "ai_invalid_output", "x"))).toBe(true);
    expect(messageWasSaved(new ApiError(429, "rate_limited", "x"))).toBe(false);
    expect(messageWasSaved(new ApiError(422, "validation_error", "x"))).toBe(false);
    expect(messageWasSaved(new ApiError(0, "network_error", "x"))).toBe(false);
  });

  it("wraps unknown errors", () => {
    expect(toApiError(new Error("boom")).category).toBe("internal_error");
  });
});
