import { defineConfig, devices } from '@playwright/test'

// End-to-end tests run against the composed stack through Caddy over HTTPS
// (`docker compose up`). Caddy's local CA is not trusted by the browsers, so
// certificate errors are ignored for this local origin only.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost',
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, testIgnore: /visual\.spec\.ts/ },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] }, testIgnore: /visual\.spec\.ts/ },
    // UX-14: screenshot baselines depend on the platform's font rendering, so they run
    // on their own (`pnpm e2e:visual`), not in `pnpm e2e` or CI.
    { name: 'visual', use: { ...devices['Desktop Chrome'] }, testMatch: /visual\.spec\.ts/ },
  ],
})
