import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('B1.2 外部系统模块 e2e（接入扩展中心容器已解体）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    page.on('dialog', (dialog) => dialog.accept());
    await page.goto('/');
    await waitAppReady(page);
    // D55/P2：外部系统模块归平台运维员独有，业务运营员退出（见末尾 OPERATER 无权用例同源守卫）。
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin');
  });

  test('外部系统模块页：系统表，一页到底无内部 tab', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '外部系统', exact: true })).toBeVisible();
    await expect(page.locator('.pkg-table tbody tr').first()).toBeVisible();
    // 瘦身：系统表只剩 外部系统/状态/信任级/操作 四列（无版本/技术编号列）。
    await expect(page.locator('.pkg-table thead th')).toHaveCount(4);
    // 容器解体：页内不再有 tablist（身份治理 / 流程表单 走左导航）。
    await expect(page.getByRole('tab')).toHaveCount(0);
  });

  test('左导航直达流程表单（独立模块）', async ({ page }) => {
    await page.getByRole('link', { name: '流程表单' }).click();
    await expect(page.getByRole('heading', { name: '流程与表单配置' })).toBeVisible();
  });

  test('信任级 disclaimer 可见', async ({ page }) => {
    await expect(page.getByText('内置信任级')).toBeVisible();
    await expect(page.getByText('不是同一字段')).toBeVisible();
  });

  test('OPERATER 无权进入 B1.2', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/integration-admin');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toMatch(/#\/integration-admin/);
  });
});

export const B12_E2E_PLACEHOLDER = {
  tabs: ['packages', 'matrix', 'engines'] as const,
};
