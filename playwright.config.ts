import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.ZW_E2E_BASE_URL ?? 'http://127.0.0.1:8800';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: [
    'webui_smoke.spec.ts',
    'b11_compliance.spec.ts',
    'b12_intake.spec.ts',
    'nl_accelerator_live.spec.ts',
    'p5_b12_unlock.spec.ts',
    'j1_objection_browser.spec.ts',
    'j1_supply_demand_browser.spec.ts',
    'j1_catalog_drilldown.spec.ts',
    'j1_data_gap.spec.ts',
    'p4_delivery_detail.spec.ts',
    'p5_duplicate_warnings.spec.ts',
    'twin_browser_pages.spec.ts',
    'customer_acceptance_checklist.spec.ts',
    'b12_iam_governance.spec.ts',
    'permission_invisibility.spec.ts',
    'resource_schema_view.spec.ts',
    'j1_credential_revoke_monitoring.spec.ts',
    'ops_invocation_visibility.spec.ts',
    'national_channel.spec.ts',
  ],
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
