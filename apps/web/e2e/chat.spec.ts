import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { registerViaUi, uniqueEmail } from "./helpers";

async function sendMessage(page: Page, text: string) {
  await page.getByLabel("Message", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

const log = (page: Page) => page.getByRole("log", { name: "Messages" });

test("chat: send, see an honest reply, and find it in history after reload", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("chat"));
  await page.goto("/chat");
  await expect(page.getByText("Start a conversation")).toBeVisible();

  await sendMessage(page, "Help me plan my week");
  await expect(page).toHaveURL(/\/chat\?c=/);
  await expect(log(page).getByText("Help me plan my week", { exact: true })).toBeVisible();
  await expect(log(page).getByText(/Demo mode: deterministic mock model/)).toBeVisible();
  await expect(log(page).getByText("Low confidence")).toBeVisible();

  await page.reload();
  await expect(log(page).getByText("Help me plan my week", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("link", { name: "Help me plan my week" })).toBeVisible();
});

test("memory: suggestion needs approval, then is disclosed when used", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("memory"));
  await page.goto("/chat");

  await sendMessage(page, "Remember that I prefer Python examples");
  const approve = page.getByRole("button", { name: /Approve memory: User said: I prefer Python examples/ });
  await expect(approve).toBeVisible();

  await sendMessage(page, "Show me Python examples for reading files");
  await expect(log(page).getByText("No memories used").last()).toBeVisible();

  await approve.click();
  await expect(approve).toBeHidden();
  await sendMessage(page, "More Python examples for writing files");
  const disclosure = log(page).getByText(/^Used 1 approved memory/);
  await expect(disclosure).toBeVisible();
  await disclosure.click();
  await expect(log(page).getByText("User said: I prefer Python examples")).toBeVisible();
});

test("memory off: nothing is suggested or used in that chat", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("memoff"));
  await page.goto("/chat");
  await page.getByRole("switch", { name: "Use memory in this chat" }).click();
  await expect(page.getByText("Memory is off: nothing read or suggested")).toBeVisible();

  await sendMessage(page, "Remember that I like tea");
  await expect(log(page).getByText(/Demo mode/)).toBeVisible();
  await expect(page.getByText("Suggested memory")).toHaveCount(0);
  await expect(log(page).getByText("No memories used")).toHaveCount(0);

  await page.goto("/memories");
  await page.getByRole("button", { name: /Suggested/ }).click();
  await expect(page.getByText("No suggestions waiting for review.")).toBeVisible();
});

test("memory page: add, edit, delete, and export", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("memmgr"));
  await page.goto("/memories");
  await expect(page.getByText("No approved memories", { exact: true })).toBeVisible();

  await page.getByLabel("Add a memory").fill("Works in IST timezone");
  await page.getByRole("button", { name: "Add memory" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Memory added." })).toBeVisible();

  await page.getByRole("button", { name: "Edit memory: Works in IST timezone" }).click();
  await page.getByLabel("Edit memory").fill("Works in IST, usually 10:00–19:00");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Works in IST, usually 10:00–19:00")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Works in IST, usually 10:00–19:00")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toBe("memories-export.json");

  await page.getByRole("button", { name: /Delete memory: Works in IST/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete memory" }).click();
  await expect(page.getByText("Memory deleted.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("No approved memories", { exact: true })).toBeVisible();
});

test("sensitive topics show a human review note", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("review"));
  await page.goto("/chat");
  await sendMessage(page, "Should I invest my savings in crypto?");
  await expect(log(page).getByText(/Human review needed: this touches on financial matters/)).toBeVisible();
});

test("no serious accessibility violations on chat and memory pages", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("axechat"));
  await page.goto("/chat");
  await sendMessage(page, "Remember that I prefer Python examples");
  await expect(page.getByText("Suggested memory")).toBeVisible();
  await page.waitForTimeout(400); // let entrance animations finish before measuring contrast
  for (const path of ["current", "/memories"]) {
    if (path !== "current") {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: "Memory", level: 1 })).toBeVisible();
      await page.waitForTimeout(400);
    }
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  }
});
