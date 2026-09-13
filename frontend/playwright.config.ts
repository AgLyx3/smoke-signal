import { defineConfig, devices } from "@playwright/test";

// Runs against a deployed or locally served app; it does not start a server.
//   E2E_BASE_URL=http://localhost:3100 npm run test:e2e     (after `vercel dev -L --listen 3100`)
//   npm run test:e2e                                        (production URL)
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://smoke-signal.vercel.app",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
