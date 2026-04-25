import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3010",
    trace: "on-first-retry"
  },
  webServer: [
    {
      command: "python3 -m uvicorn studio_api.main:app --port 8000",
      cwd: "../api",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120000
    },
    {
      command: "npm run dev -- --port 3010",
      url: "http://localhost:3010",
      reuseExistingServer: true,
      timeout: 120000
    }
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
