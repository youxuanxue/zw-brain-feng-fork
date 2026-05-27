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
 * 「无权 = 不可见」共性回归。
 * 每个写按钮 × 2 role：授权角色应该看到，未授权角色按钮必须从 DOM 完全消失（不是 disabled，不是 hidden）。
 * 触发：用户在 [2026-05-27] 验收 walkthrough 中要求「请共性地考虑整体全局修复」。
 * 守护点：zw-brain-web/src/lib/pageAccess.ts:ACTION_ROLE_GATES + canPerformAction
 *         + 各 page.vue 写按钮 v-if="canPerformAction(...)"
 */

test.describe('权限不可见 共性回归', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('P4Credential 重新签发：OPERATER 不渲染 / MANAGER 可见', async ({ page }) => {
    const reqId = await firstDeliveryRequestId(page, 'granted');
    test.skip(!reqId, 'no granted delivery_task with credential');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: new RegExp(`${reqId}.*凭据`) })).toBeVisible();
    await expect(page.getByRole('button', { name: '重新签发' })).toHaveCount(0);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('button', { name: '重新签发' })).toBeVisible();
  });

  test('P2ResourceDetail 发起复用申请：OPERATER 可见 / MANAGER 不渲染', async ({ page }) => {
    // P2 shell 含 OPERATER/MANAGER/BUSIAUDIT/SECURITY_AUDIT；但 request.create 仅 OPERATER。
    // 从 snapshot.discovery.resources 直接取第一条真实 id（同 firstDeliveryRequestId 的 GET 路径，避开
    // page.request.post 在某些代理设置下被吞的边角情况）。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    test.skip(!snap.ok(), 'snapshot unavailable');
    const snapBody = (await snap.json()) as Record<string, unknown>;
    const discovery = (snapBody.discovery ?? {}) as Record<string, unknown>;
    const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
    const resId = String(resources[0]?.id ?? '');
    test.skip(!resId, 'no discovery.resources row to drive detail page');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    await expect(page.getByRole('button', { name: '发起复用申请' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    await expect(page.getByRole('button', { name: '发起复用申请' })).toHaveCount(0);
  });

  test('P3RequestDetail 补件/重新提交：OPERATER 可见 / MANAGER 不渲染', async ({ page }) => {
    // request-flow shell 含 OPERATER+MANAGER；request.submit 仅 OPERATER。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    test.skip(!snap.ok(), 'snapshot not reachable');
    const snapBody = (await snap.json()) as Record<string, unknown>;
    const reqs = (snapBody.requests ?? []) as Array<Record<string, unknown>>;
    const reqId = String(reqs[0]?.id ?? '');
    test.skip(!reqId, 'no request row available');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toHaveCount(0);
  });

  test('P5DemandMatchDetail 受理并起草申请：OPERATER 可见 / MANAGER 不渲染', async ({ page }) => {
    // P5 shell 含 OPERATER/MANAGER/BUSIAUDIT；request.create 仅 OPERATER。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    test.skip(!snap.ok(), 'snapshot not reachable');
    const snapBody = (await snap.json()) as Record<string, unknown>;
    const provider = (snapBody.provider ?? {}) as Record<string, unknown>;
    const matches = (provider.demand_matches ?? snapBody.demand_matches ?? []) as Array<Record<string, unknown>>;
    const dmId = String(matches[0]?.id ?? '');
    test.skip(!dmId, 'no demand_match row');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await expect(page.getByRole('button', { name: '受理并起草申请' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await expect(page.getByRole('button', { name: '受理并起草申请' })).toHaveCount(0);
  });

});
