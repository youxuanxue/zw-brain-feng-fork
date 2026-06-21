import { test, expect } from '@playwright/test';
import { firstCatalogCode, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P3 J1 异议浏览器闭环', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('可从 P3 发起 catalog 异议并进入跟踪页', async ({ page, playwright }) => {
    // D11：target_id 必须存在于库内，禁止硬编码 fixture id；动态取第一条真实 catalog_code
    const api = await playwright.request.newContext();
    const code = await firstCatalogCode(api);
    await api.dispose();
    test.skip(!code, 'no catalog row available in DB to anchor objection');
    await gotoHash(page, '#/request-flow/objection/new');
    await expect(page.getByRole('heading', { name: '发起异议' })).toBeVisible();
    await page.locator('#title').fill('E2E 浏览器异议探针');
    await page.locator('#target').fill(code!);
    // 「创建异议」需 title+target+basis 三字段齐才启用，否则按钮 disabled
    await page.locator('#basis').fill('E2E 探针：字段与底册不一致');
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
