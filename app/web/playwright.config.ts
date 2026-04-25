import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3020",
    trace: "on-first-retry"
  },
  webServer: [
    {
      command:
        "rm -rf ../../.tmp/e2e-projects && STUDIO_PROJECTS_ROOT=../../.tmp/e2e-projects $([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3) -m uvicorn studio_api.main:app --port 8010",
      cwd: "../api",
      url: "http://127.0.0.1:8010/health",
      reuseExistingServer: false,
      timeout: 120000
    },
    {
      command: "NEXT_PUBLIC_API_URL=http://127.0.0.1:8010 npm run dev -- --port 3020",
      url: "http://localhost:3020",
      reuseExistingServer: false,
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
