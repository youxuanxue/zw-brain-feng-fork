import type { Page, TestInfo } from '@playwright/test';

export const E2E_BASE_URL = process.env.ZW_E2E_BASE_URL ?? 'http://127.0.0.1:8800';

/** Skip suite when REST+WebUI stack is not up (CI should start scripts/start-local.sh first). */
export async function skipUnlessBackend(page: Page, testInfo: TestInfo): Promise<void> {
  try {
    const resp = await page.request.get(`${E2E_BASE_URL}/`);
    if (!resp.ok()) {
      testInfo.skip(true, `backend not reachable: HTTP ${resp.status()}`);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    testInfo.skip(true, `backend not reachable: ${msg}`);
  }
}

export async function waitAppReady(page: Page): Promise<void> {
  await page.waitForSelector('.boot-banner', { timeout: 20_000 });
  await page.waitForSelector('.user-menu-button, .header-auth-link', { timeout: 20_000 });
  await page.waitForSelector('#role-switch', { timeout: 30_000 });
}

export async function setRole(page: Page, role: string): Promise<void> {
  await page.waitForSelector('#role-switch', { timeout: 20_000 });
  await page.selectOption('#role-switch', role);
  await page.waitForTimeout(1200);
}

export async function gotoHash(page: Page, hash: string): Promise<void> {
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
  await page.waitForTimeout(800);
}
