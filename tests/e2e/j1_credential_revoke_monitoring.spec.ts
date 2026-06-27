import { test, expect } from '@playwright/test';
import {
  firstDeliveryRequestId,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
  E2E_BASE_URL,
} from './helpers';

/**
 * SCOPE A/B e2e — j1-credential-revoke + j1-api-call-monitoring 渲染 + 角色不可见。
 *
 * A. P3 撤回 / 暂停授权（application.grant.revoke/suspend）：
 *    - 授权角色（后端 policy = 审批人 ROLE_ORGAN_MANAGER）对已授权申请 → 「收回授权」可见可点；
 *    - 非授权角色（申请人 ROLE_ORGAN_OPERATER）→ 「收回授权」从 DOM 完全消失（toHaveCount(0)）。
 * B. P4 调用记录表（ops.service.invocation.query）：凭据页能渲染「调用记录」段。
 * C. P5 供需响应：确认提供前必须填写或匹配关联资源（去写死 resource_id 后的诚实门控）。
 *
 * 守护点：
 *   zw-brain-web/src/lib/pageAccess.ts ACTION_ROLE_GATES（application.grant.revoke/suspend）
 *   + zw-brain-web/src/pages/P3RequestDetail.vue v-if=canPerformAction
 *   + P4Credential.vue 调用记录段 + P5DemandMatchDetail.vue 先匹配或填写关联资源再确认提供。
 */

/** 取第一条 granted / in_delivery 申请的 request_id（撤回/暂停只对已授权态渲染）。 */
async function firstGrantedRequestId(page: import('@playwright/test').Page): Promise<string | null> {
  const resp = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
  if (!resp.ok()) return null;
  const body = (await resp.json()) as Record<string, unknown>;
  const reqs = (body.requests ?? []) as Array<Record<string, unknown>>;
  for (const r of reqs) {
    const status = String(r.status ?? '');
    if (status === 'granted' || status === 'in_delivery' || status === 'suspended') {
      const id = String(r.id ?? '');
      if (id) return id;
    }
  }
  return null;
}

test.describe('J1 撤回/暂停授权 + 调用记录 渲染与角色不可见', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('P3 撤回/暂停角色矩阵（决策 A）：业务运营员收回/暂停 · 申请人「我不再需要」· 管理员不渲染', async ({ page }) => {
    const reqId = await firstGrantedRequestId(page);
    test.skip(!reqId, 'no granted/in_delivery request to drive revoke UI');

    // 部门管理员（MANAGER）— 决策 A 收回其撤回/暂停权，按钮必须从 DOM 完全消失。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    // 防陈旧快照 + 防数据可见性回归：先确认该角色真把申请加载出来（非「未找到该申请」），
    // 再断按钮。否则切角色后快照异步刷新未落定，会拿上个角色的缓存数据假绿（走查实证）。
    await expect(page.getByText('未找到该申请')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '收回授权' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '暂停授权' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '我不再需要' })).toHaveCount(0);

    // 业务运营员（BUSIAUDIT）— 合规收回 + 暂停可见（须能预载申请，见 web_snapshot_redaction._REQUEST）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByText('未找到该申请')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '收回授权' })).toBeVisible();

    // 申请人（OPERATER）— 主动放弃「我不再需要」可见；合规收回/暂停不渲染（属业务运营员）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByText('未找到该申请')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '我不再需要' })).toBeVisible();
    await expect(page.getByRole('button', { name: '收回授权' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '暂停授权' })).toHaveCount(0);
  });

  test('P4 调用记录段：授权岗位可见 / 申请人 OPERATER 不渲染（R-003 无权不可见）', async ({ page }) => {
    const reqId = await firstDeliveryRequestId(page, 'granted');
    test.skip(!reqId, 'no granted delivery_task with credential');

    // 申请人（OPERATER）无 ops.service.invocation.query 权限 → 整段「调用记录」不渲染。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: '调用记录' })).toHaveCount(0);

    // 审批人（MANAGER）有权 → 「调用记录」段渲染（数据可能为空，但段落须出现）。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: '调用记录' })).toBeVisible({ timeout: 10_000 });
  });

  test('P5 供需响应：未填写关联资源前不能确认提供（去写死 resource_id 诚实门控）', async ({ page }) => {
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
    test.skip(!snap.ok(), 'snapshot not reachable');
    const snapBody = (await snap.json()) as Record<string, unknown>;
    const provider = (snapBody.provider ?? {}) as Record<string, unknown>;
    const matches = (provider.demand_matches ?? snapBody.demand_matches ?? []) as Array<Record<string, unknown>>;
    const dmId = String(matches[0]?.id ?? '');
    test.skip(!dmId, 'no demand_match row');

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await page.locator('#response-note').fill('可提供，请先补关联资源编号');
    await page.getByRole('button', { name: '确认提供' }).click();
    await expect(page.locator('.toast-stack')).toContainText('请填写关联资源');
  });
});
