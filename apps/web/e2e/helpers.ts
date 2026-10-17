import { expect, type Page } from "@playwright/test";

export const PASSWORD = "a-long-demo-passphrase";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

export async function registerViaUi(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  // The greeting shortens a long local part, so match only the opening of the name.
  await expect(page.getByRole("heading", { level: 1 })).toContainText(email.slice(0, 12));
}
