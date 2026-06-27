import { test, expect, type APIRequestContext } from '@playwright/test';
import {
  firstDeliveryRequestId,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
  E2E_BASE_URL,
} from './helpers';

async function expectCredentialPage(page: import('@playwright/test').Page, reqId: string): Promise<void> {
  await expect(page.getByRole('heading', { name: /凭据/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(new RegExp(`编号\\s+.*${reqId.slice(-6)}`))).toBeVisible();
}

/**
 * 经 API 链**自铸**一条 need-fix（已退回补正）申请，返回 request_id（或 null 让用例 skip）。
 *   request.create(草稿, OPERATER) → request.submit(→ pending, OPERATER)
 *   → approval.review_decide(decision=return_for_fix, BUSIAUDIT → status=need-fix)
 * 用于驱动「补件 / 重新提交」action-gate 断言（need-fix 态下 OPERATER/MANAGER 可见、BUSIAUDIT 不渲染），
 * 不再假定 snapshot.requests[0] 是 need-fix 运行时单——干净 seed 的 requests[0] 是已暂停的导入单，
 * 会让 P3 详情页落到「在途/暂不可重提」分支、按钮不渲染 → 这条用例本属 seed-brittle。自供其前置消除脆性。
 *
 * 选 **无条件**（shareType≠有条件共享）资源：submit 后落 'pending'，return_for_fix 的前置正是
 * status∈{pending,summary-pending}（request_service.return_for_fix）。同资源已有在办申请会被
 * InvalidStateError 拦（重复跑 / 脏 DB），逐个候选试到成功；铸态走**无 cookie** 独立 APIRequestContext
 * 避开服务端 CSRF（dev 仅无 cookie 请求豁免）。
 */
async function mintNeedFixRequest(api: APIRequestContext): Promise<string | null> {
  const invoke = async (skill: string, data: Record<string, unknown>): Promise<Record<string, unknown>> => {
    const resp = await api.post(`${E2E_BASE_URL}/api/skills/${skill}`, { data });
    const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
    return (body.result ?? body) as Record<string, unknown>;
  };

  const snap = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!snap.ok()) return null;
  const snapBody = (await snap.json().catch(() => ({}))) as Record<string, unknown>;
  const discovery = (snapBody.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  // 无条件共享资源：submit→'pending'（有条件落 'submitted'，return_for_fix 前置不满足）。
  const unconditional = resources.filter((r) => String(r.shareType ?? '') !== '有条件共享');

  for (const r of unconditional.slice(0, 12)) {
    const resourceId = String(r.id ?? '');
    if (!resourceId) continue;
    const created = await invoke('request.create', {
      role: 'ROLE_ORGAN_OPERATER',
      resource_id: resourceId,
      purpose: 'e2e 权限不可见：need-fix 补件按钮 action-gate',
      confirmed: true,
    });
    const requestId = String(created.request_id ?? created.requestId ?? created.id ?? '');
    if (!requestId) continue; // 该资源已有在办申请 → 试下一个候选

    const submitted = await invoke('request.submit', {
      role: 'ROLE_ORGAN_OPERATER',
      request_id: requestId,
      confirmed: true,
    });
    if (String(submitted.status ?? '') !== 'pending') continue; // 非 pending（如有条件落 submitted）→ 换候选

    const returned = await invoke('approval.review_decide', {
      role: 'ROLE_BUSIAUDIT',
      request_id: requestId,
      decision: 'return_for_fix',
      confirmed: true,
    });
    if (String(returned.status ?? '') === 'need-fix') return requestId;
  }
  return null;
}

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
    // D55/P13·P18（反转 D53/F1）：领数据/凭据页归「部门操作员 + 部门管理员」，安全审计员退出领数据
    // （路由层重定向、已无此页）。重新签发(credential.issue) 仅 MANAGER+BUSIAUDIT → 同样能进此页的
    // 部门操作员（只读）应无此按钮，MANAGER 可见。这是当前角色模型下「同页 / 写按钮按权可见」的有效对照。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    const reqId = await firstDeliveryRequestId(page, 'granted');
    test.skip(!reqId, 'no granted delivery_task with credential');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expectCredentialPage(page, reqId);
    await expect(page.getByRole('button', { name: '重新签发' })).toHaveCount(0);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('button', { name: '重新签发' })).toBeVisible();
  });

  test('P2Discovery 页头文案：BUSIAUDIT 不出现「申请资源」字样', async ({ page }) => {
    // 找数据发现页对非申请人岗位（业务运营员=受理岗；request.create=OPERATER+MANAGER，D57④）
    // 主标题与导航同源为「找数据」；无权时不出现「申请资源」动作和「可申请资源」文案。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/discovery');
    await expect(page.getByRole('heading', { name: '找数据' })).toBeVisible();
    await expect(page.getByText('可申请资源')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '申请资源' })).toHaveCount(0);
  });

  test('P2ResourceDetail 申请资源：OPERATER/MANAGER 可见 / BUSIAUDIT 不渲染', async ({ page }) => {
    // P2 shell 含 OPERATER/MANAGER/BUSIAUDIT；request.create = OPERATER+MANAGER
    // （D57④ 管理员申请人身份照 v5 保留）；业务运营员（受理岗，已退申请人身份 D55/P7）不渲染。
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
    await expect(page.getByRole('button', { name: '发起申请' })).toBeVisible();

    // D57④ 双面验证正向半：管理员补回发起入口（后端 hierarchy 本就 200，收口前后端劈叉）。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    await expect(page.getByRole('button', { name: '发起申请' })).toBeVisible();

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    await expect(page.getByRole('button', { name: '发起申请' })).toHaveCount(0);
  });

  test('P3RequestDetail 补件/重新提交：OPERATER/MANAGER 可见 / BUSIAUDIT 不渲染', async ({ page, playwright }) => {
    // request-flow shell 含 OPERATER+MANAGER+BUSIAUDIT；request.submit = OPERATER+MANAGER（D57④）。
    // 「补件 / 重新提交」按钮仅在 need-fix（已退回补正）/ rejected 态渲染（P3RequestDetail.vue canResubmit）。
    // 自供前置：铸一条真实 need-fix 单驱动断言，不假定 requests[0] 是 need-fix（干净 seed 的 requests[0]
    // 是已暂停导入单 → 按钮本就不渲染，旧用例据此假定属 seed-brittle）。
    test.setTimeout(120_000);
    const api = await playwright.request.newContext();
    let reqId: string | null = null;
    try {
      reqId = await mintNeedFixRequest(api);
    } finally {
      await api.dispose();
    }
    test.skip(!reqId, '无法铸 need-fix 申请（缺无条件可申请资源或链路未通），跳过 action-gate 断言');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toBeVisible();

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/request-flow/request/${reqId}`);
    await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toHaveCount(0);
  });

  test('P5DemandMatchDetail 供需响应：MANAGER 可见 / OPERATER、BUSIAUDIT 不渲染', async ({ page }) => {
    // 供需响应是提供方部门管理员动作；申请方只登记和跟踪，业务运营员不替提供方响应。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
    test.skip(!snap.ok(), 'snapshot not reachable');
    const snapBody = (await snap.json()) as Record<string, unknown>;
    const provider = (snapBody.provider ?? {}) as Record<string, unknown>;
    const matches = (provider.demand_matches ?? snapBody.demand_matches ?? []) as Array<Record<string, unknown>>;
    const dmId = String(matches[0]?.id ?? '');
    test.skip(!dmId, 'no demand_match row');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await expect(page.getByRole('button', { name: '确认提供' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '受理并起草申请' })).toHaveCount(0);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await expect(page.getByRole('button', { name: '确认提供' })).toBeVisible();
    await expect(page.getByRole('button', { name: '驳回补正' })).toBeVisible();
    await expect(page.getByRole('button', { name: '拒绝提供' })).toBeVisible();

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/provider/inbox/demand-match/${dmId}`);
    await expect(page.getByRole('button', { name: '确认提供' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '受理并起草申请' })).toHaveCount(0);
  });

});
