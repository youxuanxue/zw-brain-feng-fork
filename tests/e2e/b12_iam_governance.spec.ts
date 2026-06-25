import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 身份治理 = 用户与角色管理（分派/撤销/停用）+ 谁能访问什么（只读矩阵）。
// 角色门 ROLE_SYSTEM 独占（D55/P4）。e2e 验真 UI 走查的渲染 + 写动作；非-bypass 越权安全
// 性质由 pytest（test_iam_role_governance / test_c1_read_authz_bypass）覆盖。
test.describe('B1.2 身份治理 — 角色分派与治理 (D62)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    page.on('dialog', (dialog) => {
      if (dialog.type() === 'prompt') void dialog.accept('e2e-acceptance');
      else void dialog.accept();
    });
    await page.goto('/');
    await waitAppReady(page);
  });

  test('P0: 平台运维员可进身份治理，两 tab + 用户列表渲染', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await expect(page.getByRole('heading', { name: '身份治理' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '用户与角色' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '谁能访问什么' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '旧权限映射审核' })).toHaveCount(0);
    // 默认 tab = 用户与角色，列表渲染真库 actor；用户名不再整行脱敏，机构展示可读名称而非裸编码。
    const firstRow = page.locator('tbody tr').filter({ has: page.getByRole('button', { name: '分派角色' }) }).first();
    await expect(firstRow).toBeVisible();
    const actorName = (await firstRow.locator('.actor-name').innerText()).trim();
    const orgName = (await firstRow.locator('.org-name').innerText()).trim();
    expect(actorName).not.toMatch(/^\*+$/);
    expect(orgName).toMatch(/[\u4e00-\u9fa5]/);
    await expect(page.locator('tbody')).not.toContainText('11370000MB284651XL');
  });

  test('P0: 分派并撤销用户角色（写 binding + 审计）', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    const row = page
      .locator('tbody tr')
      .filter({ has: page.getByRole('button', { name: '分派角色' }) })
      .filter({ hasText: '无角色' })
      .first();
    await expect(row).toBeVisible();
    const rowCode = (await row.locator('code.tech-id').innerText()).trim();
    await row.getByRole('button', { name: '分派角色' }).click();
    const box = page.locator('.assign-box');
    await box.getByTestId('iam-assign-org-picker').click();
    await page.getByTestId('iam-assign-org-picker-search').fill('省大数据局');
    await expect(page.getByTestId('iam-assign-org-picker-list')).toContainText('省大数据局', { timeout: 8000 });
    await page.getByTestId('iam-assign-org-picker-list').getByRole('button', { name: /省大数据局/ }).first().click();
    await box.locator('select.role-select').selectOption('ROLE_BUSIAUDIT');
    await box.getByRole('button', { name: '确认分派' }).click();
    // 成功 toast（含 audit_id）或新角色 chip 出现，二者其一即证写路径通。
    await expect(page.locator('.toast').first()).toContainText(/角色已分派|审计|audit/i, { timeout: 8000 });
    const targetRow = page.locator('tbody tr').filter({ hasText: rowCode }).first();
    await expect(targetRow).toContainText('业务运营员', { timeout: 8000 });
    const revokeBtn = targetRow.locator('.role-chip', { hasText: '业务运营员' }).locator('.role-chip-revoke').first();
    await expect(revokeBtn).toBeVisible();
    await revokeBtn.click();
    await expect(page.locator('.toast').first()).toContainText(/角色已撤销|audit/i, { timeout: 8000 });
    await expect(page.locator('tbody tr').filter({ hasText: rowCode }).first()).not.toContainText('业务运营员', {
      timeout: 8000,
    });
  });

  test('P0: 启停用户入口可用（actor 生命周期）', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    const row = page
      .locator('tbody tr')
      .filter({ has: page.getByRole('button', { name: /停用|启用/ }) })
      .filter({ has: page.locator('.status-pill').filter({ hasText: /已启用|已停用/ }) })
      .first();
    test.skip((await row.count()) === 0, '当前真库无 active/disabled actor；status.set 后端回归由 pytest 覆盖');
    await expect(row).toBeVisible();
    const before = (await row.locator('.status-pill').innerText()).trim();
    const expected = before === '已停用' ? '已启用' : '已停用';
    await row.getByRole('button', { name: /停用|启用/ }).first().click();
    await expect(row.locator('.status-pill')).toContainText(expected, { timeout: 8000 });
  });

  test('P0: 谁能访问什么 — 角色能力矩阵只读渲染', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.getByRole('tab', { name: '谁能访问什么' }).click();
    await page.waitForTimeout(800);
    // 两个 tab-panel 都在 DOM（v-show），按矩阵专属文案「只读视图」锁定矩阵面板再断言。
    const matrixPanel = page.locator('.tab-panel').filter({ hasText: '只读视图' });
    await expect(matrixPanel).toContainText('平台运维员');
  });

  test('P0: 平台运维员左导航有身份治理入口', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
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

  test('P0: 业务运营员无权进入身份治理（D55/P4 收权）', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toMatch(/#\/integration-admin\/iam-governance/);
  });
});
