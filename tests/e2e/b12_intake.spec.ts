import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('B1.2 接入扩展中心 e2e', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    page.on('dialog', (dialog) => dialog.accept());
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin');
  });

  test('3 tab 切换与 aria-selected 同步', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '接入扩展中心' })).toBeVisible();
    for (const label of ['能力接入', '开放范围', '流程与表单配置'] as const) {
      await page.getByRole('tab', { name: label }).click();
      await expect(page.getByRole('tab', { name: label })).toHaveAttribute('aria-selected', 'true');
    }
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
