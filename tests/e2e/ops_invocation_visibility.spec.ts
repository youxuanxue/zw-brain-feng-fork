import { test, expect } from '@playwright/test';
import {
  E2E_BASE_URL,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
} from './helpers';

/**
 * ops-service-invocation「调用记录」段 no-permission=invisible e2e（真浏览器）。
 *
 * 背景：该能力（ops.service.invocation.query）的唯一前端面是 P4Credential.vue 的
 * 「调用记录」段，受 `v-if="hasCredential && canViewInvocations"` 双门：
 *   - hasCredential：该申请须有已签发凭据；real-only 导入单 D47 诚实化为 not_issued，
 *     故本 spec **自给自足**——setup 走真实 J1 流程（request.create → application.resource.review
 *     approve → credential.issue 平台自签 AK-SELF）铸一个新单凭据，不依赖 seed 预置、不塞假数据。
 *   - canViewInvocations = canPerformAction('ops.service.invocation.query')，仅
 *     MANAGER + BUSIAUDIT + SECURITY_AUDIT；与后端 policy 同源（OPERATER 后端 403）。
 *
 * 断言：授权岗位「调用记录」段渲染；申请人 OPERATER 整段从 DOM 消失（toHaveCount(0)，
 * 非「可见但禁用」、非「可见点后 403」）。
 *
 * 守护点：zw-brain-web/src/pages/P4Credential.vue
 *         + zw-brain-web/src/lib/pageAccess.ts canPerformAction('ops.service.invocation.query')。
 */

type APIRequestContext = import('@playwright/test').APIRequestContext;

/**
 * 走真实 J1 流程铸一个已签发凭据的新单，返回 request_id（失败返 null → 测试 skip 不伪绿）。
 * 必须用**无浏览器 session cookie** 的独立 APIRequestContext：带 cookie 的 page.request POST
 * 会触发服务端 CSRF 拦截（dev 无 cookie 请求才豁免，同 curl 走查路径）。
 */
async function mintIssuedCredential(api: APIRequestContext): Promise<string | null> {
  const snap = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!snap.ok()) return null;
  const body = (await snap.json()) as Record<string, unknown>;
  const discovery = (body.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  const resourceId = String(resources[0]?.id ?? '');
  if (!resourceId) return null;

  const post = async (slug: string, payload: Record<string, unknown>) => {
    const r = await api.post(`${E2E_BASE_URL}/api/skills/${slug}`, { data: payload });
    return (await r.json().catch(() => ({}))) as Record<string, unknown>;
  };

  const created = await post('request.create', {
    resource_id: resourceId,
    confirmed: true,
    role: 'ROLE_ORGAN_OPERATER',
    query: 'e2e ops 可见性验收',
  });
  const result = (created.result ?? created) as Record<string, unknown>;
  const reqId = String(result.request_id ?? result.id ?? '');
  if (!reqId) return null;

  await post('application.resource.review', {
    request_id: reqId,
    decision: 'approve',
    confirmed: true,
    role: 'ROLE_ORGAN_MANAGER',
  });
  await post('credential.issue', {
    request_id: reqId,
    confirmed: true,
    role: 'ROLE_ORGAN_MANAGER',
  });

  const q = await api.get(
    `${E2E_BASE_URL}/api/skills/credential.query?role=ROLE_ORGAN_MANAGER&request_id=${reqId}`,
  );
  const qb = (await q.json().catch(() => ({}))) as Record<string, unknown>;
  if (qb.status !== 'issued') return null;
  return reqId;
}

test.describe('ops-service-invocation 调用记录段 no-permission=invisible', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('授权岗位渲染「调用记录」段 / 申请人 OPERATER 整段不渲染', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    let reqId: string | null = null;
    try {
      reqId = await mintIssuedCredential(api);
    } finally {
      await api.dispose();
    }
    test.skip(!reqId, 'could not mint an issued credential via the real J1 flow');

    const credHeading = new RegExp(`${reqId}.*凭据`);

    const shotDir = process.env.ZW_E2E_SHOT_DIR || '/tmp/zw-e2e-shots';

    // 授权岗位：凭据页加载 + 「调用记录」段渲染。
    // D53⑥（F1/6.4#15）：领数据/凭据页收窄到「部门管理员 + 安全审计」——BUSIAUDIT（业务运营员）
    // 已无该场景、路由层不可达，从授权岗位集合移除。
    for (const role of ['ROLE_ORGAN_MANAGER', 'ROLE_SECURITY_AUDIT']) {
      await setRole(page, role);
      await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
      await expect(page.getByRole('heading', { name: credHeading })).toBeVisible();
      await expect(page.getByRole('heading', { name: '调用记录' })).toBeVisible({ timeout: 10_000 });
      if (role === 'ROLE_ORGAN_MANAGER') {
        await page.screenshot({ path: `${shotDir}/ops-invocations-MANAGER-visible.png`, fullPage: true });
      }
    }

    // 申请人 OPERATER：D53⑥ 后经部门管理员承接、不再进入领数据——凭据页 +「调用记录」段
    // 对其整体不可达（路由层重定向，比页内 v-if 更强；「无权=不可见」在更外层兑现）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: credHeading })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '调用记录' })).toHaveCount(0);
    await page.screenshot({ path: `${shotDir}/ops-invocations-OPERATER-invisible.png`, fullPage: true });
  });
});
