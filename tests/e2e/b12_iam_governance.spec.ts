import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('B1.2 身份治理验收 (#109)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    page.on('dialog', (dialog) => {
      if (dialog.type() === 'prompt') void dialog.accept('e2e-acceptance');
      else void dialog.accept();
    });
    await page.goto('/');
    await waitAppReady(page);
  });

  test('P0: 业务运营员可进身份治理且列表 live', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await expect(page.getByRole('heading', { name: '身份治理' })).toBeVisible();
    await expect(page.getByText('映射候选列表')).toBeVisible();
    await expect(page.locator('.data-source-badge')).toContainText(/实时数据|演示数据/);
    await expect(page.locator('body')).toContainText('ACCEPT-TEST');
  });

  test('P0: 接入中心有身份治理入口', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin');
    await expect(page.getByRole('link', { name: '身份治理' })).toBeVisible();
    await page.getByRole('link', { name: '身份治理' }).click();
    await page.waitForTimeout(800);
    expect(page.url()).toMatch(/#\/integration-admin\/iam-governance/);
  });

  test('P0: 部门操作员无权进入身份治理', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toMatch(/#\/integration-admin\/iam-governance/);
  });

  test('P0: 待审核筛选 + 驳回所选', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.locator('.filter-row select.role-select').selectOption('pending_review');
    await page.waitForTimeout(1200);
    await expect(page.locator('body')).toContainText('ACCEPT-TEST-002');
    const row = page.locator('tr', { hasText: 'ACCEPT-TEST-002' });
    await row.locator('input[type="checkbox"]').check();
    await page.getByRole('button', { name: '驳回所选' }).click();
    await page.waitForTimeout(1500);
    await expect(page.locator('body')).toContainText('已驳回');
  });

  test('P0: fixture 模式禁用审核按钮', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await page.route('**/api/skills/governance.policy_candidate.list**', (route) =>
      route.fulfill({ status: 503, body: '{"error":"down"}' })
    );
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.waitForTimeout(1200);
    await expect(page.locator('body')).toContainText('后端暂不可达');
    await expect(page.getByRole('button', { name: '批准并写入策略' })).toBeDisabled();
  });

  test('P1: 岗位切换 toast 含中文岗位名', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider');
    await page.selectOption('#role-switch', 'ROLE_ORGAN_OPERATER');
    await page.waitForTimeout(1200);
    await expect(page.locator('.toast').first()).toContainText(/已切换岗位|部门操作员/);
  });
});
