import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P4 交付任务详情', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    // D53⑥（F1/6.4#15）：交付回执收窄到「部门管理员」——P4 交付页归 MANAGER，OPERATER 路由层重定向。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
  });

  test('点击任务编号进入详情非占位', async ({ page }) => {
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByRole('heading', { name: '交付任务' })).toBeVisible();
    const firstLink = page.locator('.focus-table tbody tr a').first();
    await expect(firstLink).toBeVisible();
    await firstLink.click();
    await page.waitForTimeout(800);
    await expect(page.locator('.focus-detail')).toBeVisible();
    await expect(page.getByRole('heading', { name: /交付任务/ })).toBeVisible();
    await expect(page.getByText('功能建设中')).toHaveCount(0);
  });
});
