import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P3 J1 异议浏览器闭环', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('可从 P3 发起 catalog 异议并进入跟踪页', async ({ page }) => {
    await gotoHash(page, '#/request-flow/objection/new');
    await expect(page.getByRole('heading', { name: '发起异议' })).toBeVisible();
    await page.locator('#title').fill('E2E 浏览器异议探针');
    await page.locator('#target').fill('CAT-DEMO-001');
    await page.getByRole('button', { name: '创建异议' }).click();
    await expect(page).toHaveURL(/#\/request-flow\/objection\/[^/]+$/, { timeout: 10_000 });
    await expect(page.getByRole('heading', { name: '发起异议' })).not.toBeVisible();
    await expect(page.getByRole('button', { name: '提交至平台' })).toBeVisible();
  });

  test('异议列表页可达', async ({ page }) => {
    await gotoHash(page, '#/request-flow/objection');
    await expect(page.getByRole('heading', { name: '我的异议' })).toBeVisible();
    await expect(page.getByRole('link', { name: '发起异议' })).toBeVisible();
  });
});
