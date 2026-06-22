import { expect, test, type Page } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, skipUnlessBackend, waitAppReady } from './helpers';

async function roleOptions(page: Page): Promise<string[]> {
  await page.waitForSelector('#role-switch', { timeout: 20_000 });
  return page.locator('#role-switch option').evaluateAll((opts) =>
    opts.map((opt) => (opt as HTMLOptionElement).value)
  );
}

async function switchRole(page: Page, role: string): Promise<void> {
  await expect(page.locator('#role-switch')).toBeEnabled({ timeout: 20_000 });
  await page.selectOption('#role-switch', role);
  await expect(page.locator('#role-switch')).toHaveValue(role);
  await expect(page.locator('#role-switch')).toBeEnabled({ timeout: 20_000 });
}

async function clearToasts(page: Page): Promise<void> {
  for (let i = 0; i < 6; i += 1) {
    const first = page.locator('.toast').first();
    if (!(await first.isVisible().catch(() => false))) break;
    await first.click({ force: true });
  }
  await expect(page.locator('.toast')).toHaveCount(0);
}

async function shellMetrics(page: Page): Promise<{
  clientWidth: number;
  scrollWidth: number;
  navHeight: number;
  toastOverlapsRoleSwitch: boolean;
  toastOverlapsHero: boolean;
}> {
  return page.evaluate(() => {
    const overlap = (a: DOMRect | null, b: DOMRect | null) => Boolean(
      a && b && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
    );
    const rect = (sel: string) => document.querySelector(sel)?.getBoundingClientRect() ?? null;
    const toast = rect('.toast-stack');
    const role = rect('#role-switch');
    const hero = rect('#app-router .page-hero, #app-router .p1-hero, #app-router h1');
    return {
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      navHeight: rect('.side-nav')?.height ?? 0,
      toastOverlapsRoleSwitch: overlap(toast, role),
      toastOverlapsHero: overlap(toast, hero),
    };
  });
}

test.describe('试用体验壳层', () => {
  test('连续切岗与路由拒绝只保留一条可读 toast', async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto(E2E_BASE_URL);
    await waitAppReady(page);

    const options = await roleOptions(page);
    test.skip(
      !options.includes('ROLE_SYSTEM') || !options.includes('ROLE_ORGAN_MANAGER') || !options.includes('ROLE_BUSIAUDIT'),
      '当前会话没有覆盖壳层体验回归所需的多岗位',
    );

    await switchRole(page, 'ROLE_SYSTEM');
    await clearToasts(page);

    await gotoHash(page, '#/provider');
    await expect(page).not.toHaveURL(/#\/provider/);
    await expect(page.locator('.toast')).toHaveCount(1);
    await expect(page.locator('.toast').first()).toContainText(/无权访问|可用入口/);

    await switchRole(page, 'ROLE_ORGAN_MANAGER');
    await expect(page.locator('.toast')).toHaveCount(1);
    await expect(page.locator('.toast').first()).toContainText(/已切换岗位|部门管理员/);

    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
    await switchRole(page, 'ROLE_BUSIAUDIT');
    await switchRole(page, 'ROLE_ORGAN_MANAGER');
    await switchRole(page, 'ROLE_SYSTEM');

    await expect(page.locator('.toast')).toHaveCount(1);
    await expect(page.locator('.toast').first()).toContainText(/已切换岗位|无权停留|可用入口/);

    const metrics = await shellMetrics(page);
    expect(metrics.toastOverlapsRoleSwitch).toBeFalsy();
    expect(metrics.toastOverlapsHero).toBeFalsy();
  });

  test('390x844 移动端首屏不横向溢出，导航不挤压主内容', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await skipUnlessBackend(page, testInfo);
    await page.goto(E2E_BASE_URL);
    await waitAppReady(page);

    const options = await roleOptions(page);
    test.skip(
      !options.includes('ROLE_SYSTEM') || !options.includes('ROLE_ORGAN_MANAGER'),
      '当前会话没有覆盖移动端切岗体验所需的岗位',
    );

    await switchRole(page, 'ROLE_ORGAN_MANAGER');
    await clearToasts(page);
    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();

    const before = await shellMetrics(page);
    expect(before.scrollWidth).toBeLessThanOrEqual(before.clientWidth);
    expect(before.navHeight).toBeLessThanOrEqual(72);

    await switchRole(page, 'ROLE_SYSTEM');
    await expect(page.locator('.toast')).toHaveCount(1);
    const after = await shellMetrics(page);
    expect(after.scrollWidth).toBeLessThanOrEqual(after.clientWidth);
    expect(after.toastOverlapsRoleSwitch).toBeFalsy();
    expect(after.toastOverlapsHero).toBeFalsy();
  });

  test('未登录冷启动只允许认证探测 401，不抢跑业务 API', async ({ page }) => {
    const sessionStatuses: number[] = [];
    const businessApiRequests: string[] = [];

    await page.route('**/auth/iaf/session', async (route) => {
      sessionStatuses.push(401);
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'iaf_auth_error', detail: 'not authenticated' }),
      });
    });
    await page.route('**/auth/iaf/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ configured: true, development_iam_bypass_enabled: false }),
      });
    });
    await page.route('**/api/**', async (route) => {
      businessApiRequests.push(route.request().url());
      await route.fulfill({
        status: 418,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'business_api_called_before_auth_bootstrap' }),
      });
    });

    await page.goto(`${E2E_BASE_URL}/#/workbench`);
    await expect(page.getByRole('heading', { name: '登录政务数据大脑' })).toBeVisible();
    await page.waitForTimeout(500);

    expect(sessionStatuses).toContain(401);
    expect(businessApiRequests).toEqual([]);
  });
});
