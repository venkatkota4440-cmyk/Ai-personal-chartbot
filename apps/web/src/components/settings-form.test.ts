import type { UserSettings } from "@shared/types";
import { describe, expect, it } from "vitest";

import { diffSettings } from "@/components/settings-form";

const base: UserSettings = {
  timezone: "UTC",
  default_model: "mock-deterministic",
  available_models: ["mock-deterministic"],
  notify_run_succeeded: true,
  notify_run_failed: true,
  notify_approval_needed: true,
  message_retention_days: null,
};

describe("diffSettings", () => {
  it("returns an empty change when nothing changed", () => {
    expect(diffSettings(base, { ...base })).toEqual({});
  });

  it("includes only changed fields, including clearing retention to null", () => {
    const original = { ...base, message_retention_days: 30 };
    expect(diffSettings(original, { ...original, timezone: "Asia/Kolkata", message_retention_days: null })).toEqual({
      timezone: "Asia/Kolkata",
      message_retention_days: null,
    });
  });
});
