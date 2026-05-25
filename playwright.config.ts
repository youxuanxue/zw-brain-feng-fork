import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.ZW_E2E_BASE_URL ?? 'http://127.0.0.1:8800';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['webui_smoke.spec.ts', 'b11_compliance.spec.ts', 'nl_accelerator_live.spec.ts', 'p5_b12_unlock.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL,
    headless: process.env.ZW_E2E_HEADLESS !== '0',
    trace: 'on-first-retry',
    viewport: { width: 1440, height: 1024 },
    ignoreHTTPSErrors: true,
    launchOptions: {
      args: ['--no-proxy-server'],
    },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
