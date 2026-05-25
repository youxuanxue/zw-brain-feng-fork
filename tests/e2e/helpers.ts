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

/** 确保至少一条待发布目录；多轮 e2e 发布后队列为空时自动从 pending_review 补一条。 */
export async function ensurePublishQueue(page: Page): Promise<boolean> {
  const queueResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (queueResp.ok()) {
    const body = (await queueResp.json()) as { items?: unknown[] };
    if (body.items?.length) return true;
  }

  const pendingResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'pending_review', limit: 1 },
  });
  if (!pendingResp.ok()) return false;
  const pending = (await pendingResp.json()) as {
    items?: Array<{ catalog_code?: string; id?: string }>;
  };
  const code = pending.items?.[0]?.catalog_code ?? pending.items?.[0]?.id;
  if (!code) return false;

  const reviewResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.review`, {
    data: {
      role: 'ROLE_BUSIAUDIT',
      catalog_code: code,
      decision: 'approve',
      confirmed: true,
    },
  });
  if (!reviewResp.ok()) return false;

  const after = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (!after.ok()) return false;
  const afterBody = (await after.json()) as { items?: unknown[] };
  return Boolean(afterBody.items?.length);
}
