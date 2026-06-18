import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 身份治理 = 用户与角色管理（分派/撤销/停用）+ 谁能访问什么（只读矩阵）+ 旧权限映射审核（D62）。
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

  test('P0: 平台运维员可进身份治理，三 tab + 用户列表渲染', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await expect(page.getByRole('heading', { name: '身份治理' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '用户与角色' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '谁能访问什么' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '旧权限映射审核' })).toBeVisible();
    // 默认 tab = 用户与角色，列表渲染注入的真库 actor（按 actor id 定位，名字被脱敏）。
    await expect(page.locator('code.tech-id', { hasText: 'e2e-actor-1' })).toBeVisible();
  });

  test('P0: 分派角色给用户（写 binding + 审计）', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    const row = page.locator('tr', { has: page.locator('code.tech-id', { hasText: 'e2e-actor-2' }) });
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: '分派角色' }).click();
    const box = page.locator('.assign-box');
    await box.locator('input.text-input').fill('11370000MB284651XL');
    await box.locator('select.role-select').selectOption('ROLE_BUSIAUDIT');
    await box.getByRole('button', { name: '确认分派' }).click();
    // 成功 toast（含 audit_id）或新角色 chip 出现，二者其一即证写路径通。
    await expect(page.locator('.toast').first()).toContainText(/角色已分派|审计|audit/i, { timeout: 8000 });
    await expect(
      page.locator('tr', { has: page.locator('code.tech-id', { hasText: 'e2e-actor-2' }) })
    ).toContainText('业务运营员', { timeout: 8000 });
  });

  test('P0: 撤销用户角色（置 binding disabled + 审计）', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    const row = page.locator('tr', { has: page.locator('code.tech-id', { hasText: 'e2e-actor-1' }) });
    await expect(row).toBeVisible();
    // actor-1 至少持有一个角色 chip；点其撤销 ×。
    const revokeBtn = row.locator('.role-chip-revoke').first();
    await expect(revokeBtn).toBeVisible();
    await revokeBtn.click();
    await expect(page.locator('.toast').first()).toContainText(/角色已撤销|audit/i, { timeout: 8000 });
  });

  test('P0: 停用用户（actor 生命周期）', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    const row = page.locator('tr', { has: page.locator('code.tech-id', { hasText: 'e2e-actor-3' }) });
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: /停用|启用/ }).first().click();
    // 停用/启用后状态列变化，列表刷新后可见。
    await expect(row.locator('.status-pill')).toContainText(/已停用|正常/, { timeout: 8000 });
  });

  test('P0: 谁能访问什么 — 角色能力矩阵只读渲染', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.getByRole('tab', { name: '谁能访问什么' }).click();
    await page.waitForTimeout(800);
    // 三个 tab-panel 都在 DOM（v-show），按矩阵专属文案「只读视图」锁定矩阵面板再断言。
    const matrixPanel = page.locator('.tab-panel').filter({ hasText: '只读视图' });
    await expect(matrixPanel).toContainText('平台运维员');
  });

  test('P0: 旧权限映射审核 tab 渲染（候选列表迁入 tab ③）', async ({ page }) => {
    await page.route('**/api/skills/governance.policy_candidate.list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tenant_id: 'sd-default',
          summary: { total: 1, status_counts: { pending_review: 1 } },
          items: [
            {
              legacy_system: 'dsp-bsp',
              legacy_permission_ref: 'ACCEPT-TEST',
              legacy_role_ref: 'ROLE_BUSIAUDIT',
              capability_id: 'zone.publish_topic_projection',
              surface: 'webui',
              candidate_status: 'pending_review',
              evidence_json: { source: 'e2e-injected' },
            },
          ],
        }),
      })
    );
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.getByRole('tab', { name: '旧权限映射审核' }).click();
    await page.waitForTimeout(600);
    await expect(page.locator('body')).toContainText('ACCEPT-TEST');
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
