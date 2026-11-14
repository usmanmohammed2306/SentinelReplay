import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60000,
  reporter: [
    ["list"],
    ["json", { outputFile: "../.local-controller/ui-validation/results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:18772",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  outputDir: "../.local-controller/ui-validation/test-output",
  webServer: [
    {
      command: "../.venv/bin/python ../scripts/serve_ui_fixture.py",
      url: "http://127.0.0.1:18771/healthz",
      reuseExistingServer: false,
      timeout: 90000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 2000 },
    },
    {
      command: "pnpm start --port 18772",
      url: "http://127.0.0.1:18772",
      reuseExistingServer: false,
      timeout: 60000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 2000 },
      env: {
        SENTINEL_API_URL: "http://127.0.0.1:18771",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
