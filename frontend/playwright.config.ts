import { defineConfig, devices } from '@playwright/test'

// The end-to-end test drives the panel of the stack in infra/docker-compose.e2e.yml, which must be
// up and seeded first (its header says how). It starts nothing itself: the stack is several
// containers and the AI stand-in, not a dev server.
const ci = Boolean(process.env.CI)

export default defineConfig({
  testDir: './e2e',
  // One report flows through one worker queue: the tests run one at a time.
  workers: 1,
  fullyParallel: false,
  forbidOnly: ci,
  // A retry only to record the trace of the failure; a test that passes on it is still a flake to fix.
  retries: ci ? 1 : 0,
  reporter: ci ? [['list'], ['html', { open: 'never' }]] : 'list',
  // Two trips through the worker (extraction, then the PDF and its email) plus the browser steps.
  timeout: 180_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:18080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure'
  },
  projects: [
    {
      name: 'chromium',
      // English panel, the company's clock (the seeded company's timezone).
      use: { ...devices['Desktop Chrome'], locale: 'en-US', timezoneId: 'Europe/Madrid' }
    }
  ]
})
