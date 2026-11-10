import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: 'cd ../backend && uv run uvicorn app.main:app --port 8000', url: 'http://localhost:8000/api/health', reuseExistingServer: true },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true },
    { command: 'npm --prefix ../frontend-reviewer run dev', url: 'http://localhost:5174', reuseExistingServer: true },
  ],
})
