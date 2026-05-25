import { test, expect } from '@playwright/test';
import { E2E_BASE_URL, ensurePublishQueue, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P5 发布重复率提醒', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    const ready = await ensurePublishQueue(page);
    if (!ready) testInfo.skip(true, 'cannot seed approved_pending_publish queue');
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider');
  });

  test('catalog.entry.publish 响应含 duplicate_warnings 字段', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
    const publishBtn = page.getByTestId('publish-catalog-btn').first();
    await expect(publishBtn).toBeVisible({ timeout: 15_000 });
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/skills/catalog.entry.publish') && r.ok(),
    );
    await publishBtn.click();
    const resp = await respPromise;
    const body = (await resp.json()) as Record<string, unknown>;
    const inner = (body.result ?? body) as Record<string, unknown>;
    expect(Array.isArray(inner.duplicate_warnings)).toBe(true);
  });
});
