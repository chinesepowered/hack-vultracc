import { defineConfig } from "@playwright/test";

// E2E checks run against the mock (VITE_MOCK=1) dev server by default.
// Set E2E_BASE_URL to point them at a running build instead (mock builds only: the flow starts a close).
const base = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5174";

export default defineConfig({
  testDir: "e2e",
  timeout: 150_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: base,
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : undefined,
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "VITE_MOCK=1 pnpm exec vite --port 5174 --strictPort --host 127.0.0.1",
        url: base,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
