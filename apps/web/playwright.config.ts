import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the real FastAPI backend (fresh SQLite database) and a production
 * build of the web app, on dedicated ports so they never touch your dev servers or data.
 */
const WEB_PORT = 3100;
const API_PORT = 8001;
const PYTHON = process.env.E2E_PYTHON ?? "../../.venv/bin/python";
const E2E_DB = process.env.E2E_DB ?? "/tmp/personal-ai-agent-e2e.db";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `rm -f ${E2E_DB} && ${PYTHON} -m alembic upgrade head && ${PYTHON} -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../api",
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      env: {
        APP_ENV: "development",
        DATABASE_URL: `sqlite:///${E2E_DB}`,
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
        LOG_LEVEL: "WARNING",
        // Each test registers a fresh account from the same IP; the production limit (10/hour) stays untested here
        // and is covered by the backend test suite instead.
        REGISTER_RATE_LIMIT_PER_HOUR: "1000",
      },
    },
    {
      command: `npx next build && npx next start --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}/login`,
      reuseExistingServer: false,
      timeout: 240_000,
      env: { NEXT_DIST_DIR: ".next-e2e", API_INTERNAL_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
