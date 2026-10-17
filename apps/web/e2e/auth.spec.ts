import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { PASSWORD, registerViaUi, uniqueEmail } from "./helpers";

test("unauthenticated visitors are sent to sign in, keeping the destination", async ({ page }) => {
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("register, see the home view, sign out, and sign back in", async ({ page }) => {
  const email = uniqueEmail("owner");
  await registerViaUi(page, email);

  const nav = page.getByRole("navigation", { name: "Main" });
  for (const label of ["Chat", "Tasks", "Projects", "Automations", "Approvals", "Files", "Settings"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
  // The seeded demo data means the home view is never an empty shell.
  await expect(page.getByRole("heading", { name: "Today's priorities" })).toBeVisible();
  await expect(page.getByText("ScamShield AI")).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("definitely-the-wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect" })).toBeVisible();

  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
});

test("registration validates the password before calling the server", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail("short"));
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Use at least 12 characters")).toBeVisible();
  await expect(page).toHaveURL(/\/register/);
});

test("settings persist after reload", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("settings"));
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }).click();

  await page.getByLabel("Timezone").selectOption("Europe/Berlin");
  await page.getByLabel("Conversation messages").selectOption("30");
  await page.getByRole("switch", { name: "Run succeeded" }).click();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Settings saved." })).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Timezone")).toHaveValue("Europe/Berlin");
  await expect(page.getByLabel("Conversation messages")).toHaveValue("30");
  await expect(page.getByRole("switch", { name: "Run succeeded" })).toHaveAttribute("aria-checked", "false");
});

test("upcoming sections say honestly that they are not built yet", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("honest"));
  await page.goto("/files");
  await expect(page.getByText("Not available yet — planned for M6")).toBeVisible();
});

test("keyboard users can skip to content and see focus", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("keyboard"));
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  const outline = await skip.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});

test("reduced-motion preference disables animations", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const duration = await page
    .locator("main > div")
    .first()
    .evaluate((el) => getComputedStyle(el).animationDuration);
  expect(parseFloat(duration)).toBeLessThan(0.01);
});

for (const path of ["/login", "/register"]) {
  test(`no serious accessibility violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });
}

test("no serious accessibility violations on home and settings", async ({ page }) => {
  await registerViaUi(page, uniqueEmail("axe"));
  for (const path of ["/", "/settings"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /Loading|Checking/ })).toHaveCount(0);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  }
});
