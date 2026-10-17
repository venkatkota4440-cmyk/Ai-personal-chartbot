import { describe, expect, it } from "vitest";

import { greetingFor, listTimeZones } from "@/lib/time";

describe("greetingFor", () => {
  const nineUtc = new Date("2026-10-16T09:00:00Z");

  it("uses the user's timezone, not the browser's", () => {
    expect(greetingFor(nineUtc, "UTC")).toBe("Good morning");
    // 09:00 UTC is 14:30 in Kolkata.
    expect(greetingFor(nineUtc, "Asia/Kolkata")).toBe("Good afternoon");
  });

  it("falls back safely for an invalid timezone", () => {
    expect(greetingFor(nineUtc, "Not/AZone")).toBe("Good morning");
  });
});

describe("listTimeZones", () => {
  it("always includes UTC", () => {
    expect(listTimeZones()).toContain("UTC");
  });

  it("keeps the user's saved timezone even if the browser uses another alias", () => {
    expect(listTimeZones("Asia/Kolkata")).toContain("Asia/Kolkata");
  });
});
