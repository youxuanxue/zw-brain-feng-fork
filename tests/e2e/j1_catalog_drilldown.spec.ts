import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// J1 目录→资源钻取：目录浏览 → 点目录 → 目录详情（列资源）→ 点资源 → 资源详情。
test.describe('J1 目录→资源钻取', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('目录浏览页列真目录 + 每行可钻取', async ({ page }) => {
    await gotoHash(page, '#/discovery/catalog-browse');
    await expect(page.getByRole('heading', { name: '目录浏览' })).toBeVisible();
    const drillLink = page.getByRole('link', { name: '查看目录资源' }).first();
    await expect(drillLink).toBeVisible({ timeout: 10_000 });
    await expect(drillLink).toHaveAttribute('href', /#\/discovery\/catalog\//);
  });

  test('点目录 → 目录详情页（真实库目录展示其下资源）', async ({ page }) => {
    await gotoHash(page, '#/discovery/catalog-browse');
    await page.getByRole('link', { name: '查看目录资源' }).first().click();
    await page.waitForTimeout(800);
    expect(page.url()).toMatch(/#\/discovery\/catalog\//);
    // 详情页 header 显示「N 个关联资源」或「该目录暂无关联资源」，两者皆诚实
    await expect(page.locator('body')).toContainText(/关联资源/);
  });

  test('医保目录（F9）→ 诚实空列表', async ({ page }) => {
    // 医疗救助信息：basic-element 目录，主表可检索但挂 0 资源
    await gotoHash(page, '#/discovery/catalog/basic-elem:0b26783950004ed882ec9309fae73310');
    await page.waitForTimeout(800);
    await expect(page.locator('body')).toContainText('该目录暂无关联资源');
  });
});
