import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P3 供需对接浏览器入口', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('登记一条 demand 并可见阶段', async ({ page }) => {
    await gotoHash(page, '#/request-flow/supply-demand');
    await expect(page.getByRole('heading', { name: '找不到数据 · 登记需求' })).toBeVisible();
    const title = `E2E-demand-${Date.now()}`;
    await page.locator('#demand-title').fill(title);
    await page.getByRole('button', { name: '登记需求' }).click();
    await page.waitForTimeout(1200);
    await expect(page.locator('.focus-table tbody tr').first()).toBeVisible();
    await expect(page.locator('.focus-table')).toContainText('发现缺口');
  });
});
