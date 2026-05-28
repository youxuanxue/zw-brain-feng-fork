import { test, expect } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

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

  test('P0: 业务运营员可进身份治理且列表渲染候选', async ({ page }) => {
    // 自包含：注入确定性 list 响应，断言不依赖生产库恰好 seed 了某条候选。
    // 真实后端数据流由 pytest 集成套 + 「待审核筛选」用例覆盖；本用例只验渲染路径。
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
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await expect(page.getByRole('heading', { name: '身份治理' })).toBeVisible();
    await expect(page.getByText('映射候选列表')).toBeVisible();
    await expect(page.locator('.data-source-badge')).toContainText('实时数据');
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
    // 状态修改后的幂等性：动态取当前列表里的第一条 pending_review，禁止硬编码 ACCEPT-TEST-002
    // （上轮 run 把它 reject 掉后，再 run 就找不到 → 死循环卡死）。每轮拿当前第一条就行。
    const listResp = await page.request.post(`${E2E_BASE_URL}/api/skills/governance.policy_candidate.list`, {
      data: {
        role: 'ROLE_BUSIAUDIT',
        confirmed: true,
        limit: 5,
        candidate_status: 'pending_review',
      },
    });
    test.skip(!listResp.ok(), 'governance.policy_candidate.list not reachable');
    const body = (await listResp.json()) as { items?: Array<{ legacy_permission_ref?: string }> };
    const targetRef = body.items?.[0]?.legacy_permission_ref;
    test.skip(!targetRef, 'no pending_review policy_candidate available to reject');

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.locator('.filter-row select.role-select').selectOption('pending_review');
    await page.waitForTimeout(1200);
    await expect(page.locator('body')).toContainText(targetRef!);
    const row = page.locator('tr', { hasText: targetRef! });
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
