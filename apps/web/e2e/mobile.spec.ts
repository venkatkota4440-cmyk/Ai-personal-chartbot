import { expect, test } from "@playwright/test";

import { registerViaUi, uniqueEmail } from "./helpers";

test("mobile tab bar navigates and meets Apple's 44pt target size", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("mobile"));
  // The desktop source list is hidden on a phone; the tab bar replaces it.
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();

  const tabs = page.getByRole("navigation", { name: "Sections" });
  await expect(tabs).toBeVisible();

  const settings = tabs.getByRole("link", { name: "Settings" });
  const box = await settings.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);

  await settings.click();
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
  await expect(settings).toHaveAttribute("aria-current", "page");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});

test("mobile: the tab bar never covers the end of a page", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("mobilescroll"));
  await page.goto("/tasks");
  await page.getByRole("button", { name: "New task" }).click();
  await page.getByLabel("Title").fill("Reachable at the bottom");
  await page.getByRole("button", { name: "Add task", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Task added." })).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const lastRow = page.getByText("Reachable at the bottom");
  await expect(lastRow).toBeInViewport();
  const tabs = await page.getByRole("navigation", { name: "Sections" }).boundingBox();
  const row = await lastRow.boundingBox();
  expect((row?.y ?? 0) + (row?.height ?? 0)).toBeLessThanOrEqual(tabs?.y ?? 0);
});

test("mobile chat: send a message and open conversation history", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("mobilechat"));
  await page.goto("/chat");
  await page.getByLabel("Message", { exact: true }).fill("Plan my morning");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("log", { name: "Messages" }).getByText(/Demo mode/)).toBeVisible();

  await page.getByRole("button", { name: "Conversations" }).click();
  await expect(page.getByRole("dialog").getByRole("link", { name: "Plan my morning" })).toBeVisible();
});

test("mobile chat: a new memory suggestion is visible, not hidden behind the message box", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("mobilesuggest"));
  await page.goto("/chat");
  for (const text of ["First message to fill the screen", "Remember that I like short answers"]) {
    await page.getByLabel("Message", { exact: true }).fill(text);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    await expect(page.getByText("Assistant is replying…")).toHaveCount(0);
  }
  const approve = page.getByRole("button", { name: /Approve memory/ });
  await expect(approve).toBeInViewport();
  const composer = await page.getByLabel("Message", { exact: true }).boundingBox();
  const card = await approve.boundingBox();
  expect((card?.y ?? 0) + (card?.height ?? 0)).toBeLessThanOrEqual(composer?.y ?? 0);
});

test("mobile: long names and URLs stay inside the screen", async ({ page }) => {
  // A long email local part and a long target URL are the two values that can overflow a phone.
  await registerViaUi(page, `averylongaccountname${Date.now()}@example.com`);
  await page.goto("/automations");
  await page.getByRole("button", { name: /ScamShield Weekly Review/ }).click();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByRole("region", { name: "Run timeline" })).toBeVisible();

  for (const path of ["/", "/approvals"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(1);
  }
});
