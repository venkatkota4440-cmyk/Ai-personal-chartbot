import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { registerViaUi, uniqueEmail } from "./helpers";

test("tasks: create, complete, filter and delete", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("tasks"));
  await page.goto("/tasks");
  // Seeded demo data is present, so the view is never empty on day one.
  await expect(page.getByText("Milestone 2: build lookalike-domain checker")).toBeVisible();

  await page.getByRole("button", { name: "New task" }).click();
  await page.getByLabel("Title").fill("Buy milk");
  await page.getByLabel("Priority").selectOption("urgent");
  await page.getByRole("button", { name: "Add task", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task added." })).toBeVisible();

  await page.getByRole("button", { name: "Mark 'Buy milk' as done" }).click();
  await page.getByRole("radio", { name: "Done" }).click();
  await expect(page.getByText("Buy milk")).toBeVisible();

  await page.getByRole("radio", { name: "Open" }).click();
  await expect(page.getByText("Buy milk")).toHaveCount(0);

  await page.getByRole("radio", { name: "Done" }).click();
  await page.getByRole("button", { name: "Delete task: Buy milk" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Buy milk")).toHaveCount(0);
});

test("projects: ScamShield is seeded with milestone progress", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("projects"));
  await page.goto("/projects");
  const scamshield = page.getByRole("link", { name: /ScamShield AI/ });
  await expect(scamshield).toBeVisible();
  await expect(scamshield).toContainText("5 open");
  await expect(scamshield).toContainText("1 of 6 done");
});

test("automation: run a low-risk workflow and read its timeline", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("auto"));
  await page.goto("/automations");
  await page.getByRole("button", { name: /Daily Briefing/ }).click();

  await expect(page.getByRole("heading", { name: "Daily Briefing", level: 1 })).toBeVisible();
  // Every step's risk is shown, decided by the server.
  await expect(page.getByText("read tasks")).toBeVisible();
  await expect(page.getByText("Low risk").first()).toBeVisible();

  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Run finished successfully." })).toBeVisible();

  const timeline = page.getByRole("region", { name: "Run timeline" });
  await expect(timeline.getByText("1. read tasks")).toBeVisible();
  await expect(timeline.getByText("3. draft briefing")).toBeVisible();
  await expect(timeline.getByText("Done").first()).toBeVisible();
});

test("approval gate: a high-risk step stops, then runs once when approved", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("approve"));
  await page.goto("/automations");
  await page.getByRole("button", { name: /ScamShield Weekly Review/ }).click();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByRole("status").filter({ hasText: "needs your approval" })).toBeVisible();

  await page.goto("/approvals");
  const card = page.getByRole("article").filter({ hasText: "publish report" });
  await expect(card).toBeVisible();
  // The user sees the exact target and the consequence before deciding.
  await expect(card.getByRole("definition").filter({ hasText: "https://example.invalid/scamshield/weekly" }).first()).toBeVisible();
  await expect(card.getByText(/becomes visible at the target address/)).toBeVisible();
  await card.getByText("Show the exact data to be sent").click();
  await expect(card.getByText(/"type": "publish_report"/)).toBeVisible();

  await card.getByRole("button", { name: "Approve once" }).click();
  await expect(page.getByRole("status").filter({ hasText: "ran once and cannot run again" })).toBeVisible();

  // It is gone from the waiting list and cannot be approved twice.
  await expect(page.getByRole("article").filter({ hasText: "publish report" })).toHaveCount(0);
  await page.getByRole("radio", { name: "Done" }).click();
  await expect(page.getByText("Done once")).toBeVisible();
});

test("approval gate: rejecting stops the action", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("reject"));
  await page.goto("/automations");
  await page.getByRole("button", { name: /ScamShield Weekly Review/ }).click();
  await page.getByRole("button", { name: "Run now" }).click();
  await page.goto("/approvals");

  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByRole("status").filter({ hasText: "did not run" })).toBeVisible();

  await page.goto("/automations");
  await page.getByRole("button", { name: /ScamShield Weekly Review/ }).click();
  await expect(page.getByText("Partly done").first()).toBeVisible();
});

test("home shows approvals waiting and seeded work", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("home"));
  await page.goto("/automations");
  await page.getByRole("button", { name: /ScamShield Weekly Review/ }).click();
  await page.getByRole("button", { name: "Run now" }).click();

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Waiting for you" })).toBeVisible();
  await expect(page.getByText(/wants to run 'publish_report'/)).toBeVisible();
});

test("no serious accessibility violations on the new sections", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("axeauto"));
  for (const path of ["/tasks", "/projects", "/automations", "/approvals", "/notifications"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /Loading/ })).toHaveCount(0);
    await page.waitForTimeout(350);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  }
});
