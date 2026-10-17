import { describe, expect, it } from "vitest";

import { isActive, NAV_ITEMS, TAB_ITEMS } from "@/components/shell/nav-items";

describe("navigation", () => {
  it("keeps the PRD sections in order in the sidebar", () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      "Home",
      "Chat",
      "Tasks",
      "Projects",
      "Automations",
      "Approvals",
      "Files",
      "Notifications",
      "Settings",
    ]);
  });

  it("keeps the tab bar to five items, as Apple's guidelines require", () => {
    expect(TAB_ITEMS).toHaveLength(5);
    expect(TAB_ITEMS.every((tab) => NAV_ITEMS.some((item) => item.href === tab.href))).toBe(true);
  });

  it("highlights the parent tab for pages reached from inside a section", () => {
    expect(isActive("/projects", "/tasks")).toBe(true);
    expect(isActive("/automations", "/approvals")).toBe(true);
    expect(isActive("/notifications", "/settings")).toBe(true);
  });

  it("matches nested routes but not prefixes of other words", () => {
    expect(isActive("/tasks/123", "/tasks")).toBe(true);
    expect(isActive("/tasksx", "/tasks")).toBe(false);
    expect(isActive("/settings", "/")).toBe(false);
    expect(isActive("/", "/")).toBe(true);
  });

  it("highlights Chat while managing memory", () => {
    expect(isActive("/memories", "/chat")).toBe(true);
  });
});
