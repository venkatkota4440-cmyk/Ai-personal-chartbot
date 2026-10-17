import { expect, test } from "@playwright/test";

test("rotating a spoofed X-Forwarded-For header does not bypass the login rate limit", async ({ request }) => {
  const csrf = (await (await request.get("/api/auth/csrf")).json()) as { csrf_token: string };
  const statuses: number[] = [];
  for (let i = 0; i < 6; i += 1) {
    const response = await request.post("/api/auth/login", {
      headers: { "X-CSRF-Token": csrf.csrf_token, "X-Forwarded-For": `198.51.100.${i + 1}` },
      data: { email: "spoof-target@example.com", password: "wrong-password-123" },
    });
    statuses.push(response.status());
  }
  expect(statuses.slice(0, 5)).toEqual([401, 401, 401, 401, 401]);
  expect(statuses[5]).toBe(429);
});

test("state-changing API calls without a CSRF token are refused", async ({ request }) => {
  const response = await request.post("/api/auth/login", {
    data: { email: "nobody@example.com", password: "wrong-password-123" },
  });
  expect(response.status()).toBe(403);
  expect(((await response.json()) as { error: { category: string } }).error.category).toBe("csrf_failed");
});

test("the browser bundle contains no server-side configuration", async ({ page }) => {
  const scripts: string[] = [];
  page.on("response", async (response) => {
    if (response.url().endsWith(".js")) scripts.push(await response.text());
  });
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  const bundle = scripts.join("\n");
  expect(bundle).not.toContain("API_INTERNAL_URL");
  expect(bundle).not.toContain("127.0.0.1:8001");
  expect(bundle).not.toContain("SESSION_SECRET");
});
