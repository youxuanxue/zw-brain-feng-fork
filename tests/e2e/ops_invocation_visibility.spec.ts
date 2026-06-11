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
 *     故本 spec **自给自足**——setup 走真实 J1 流程（application.resource.submit 直提 →
 *     application.resource.review 业务运营员受理 approve → credential.issue 平台自签 AK-SELF）
 *     铸一个新单凭据，不依赖 seed 预置、不塞假数据。
 *   - canViewInvocations = canPerformAction('ops.service.invocation.query')，gate 注册为
 *     MANAGER + BUSIAUDIT + SECURITY_AUDIT + SYSTEM（与后端 policy set-equal，守卫强制）；
 *     申请人 OPERATER 不在集合（后端 403）。
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

  const post = async (slug: string, payload: Record<string, unknown>) => {
    const r = await api.post(`${E2E_BASE_URL}/api/skills/${slug}`, { data: payload });
    return (await r.json().catch(() => ({}))) as Record<string, unknown>;
  };

  // permission-matrix-0610 修：request.create 自 G2 起落「草稿」不进审批，改走
  // application.resource.submit 直提（落 pending 即进受理队列）；无条件 shared_type=1。
  // 同资源已有在办申请会被拦（重复跑 / 脏 DB），逐个候选资源试到成功。
  let reqId = '';
  for (const r of resources.slice(0, 12)) {
    const created = await post('application.resource.submit', {
      resource_id: String(r.id ?? ''),
      confirmed: true,
      role: 'ROLE_ORGAN_OPERATER',
      shared_type: 1,
      purpose: 'e2e ops 可见性验收：调用记录段权限走查',
      query: 'e2e ops 可见性验收',
    });
    const result = (created.result ?? created) as Record<string, unknown>;
    reqId = String(result.request_id ?? result.id ?? '');
    if (reqId) break;
  }
  if (!reqId) return null;

  // D55/P21：无条件共享受理即终 = 业务运营员（application.resource.review={BUSIAUDIT}）。
  // 原 role=MANAGER 自 D55 起 403 → 铸单永败 → 本 spec perma-skip（假 skip 曾遮蔽 gate 回归）。
  await post('application.resource.review', {
    request_id: reqId,
    decision: 'approve',
    confirmed: true,
    role: 'ROLE_BUSIAUDIT',
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

    // 授权岗位（部门管理员）：凭据页 + 「调用记录」段渲染。D55/P13·P18（反转 D53/F1）：领数据/凭据页
    // 收窄到「部门操作员 + 部门管理员」、安全审计员退出领数据。领数据可达两岗位中，仅部门管理员
    // 同时具备 ops.service.invocation.query（部门操作员后端 403）→ 唯一同时能进页 + 看「调用记录」段。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: credHeading })).toBeVisible();
    await expect(page.getByRole('heading', { name: '调用记录' })).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: `${shotDir}/ops-invocations-MANAGER-visible.png`, fullPage: true });

    // 申请人 OPERATER：D55 后可进领数据/凭据页，但无 ops.service.invocation.query（后端 403）→
    // 「调用记录」段须从 DOM 消失（段级 no-permission=invisible，非「可见但内含 403」）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: credHeading })).toBeVisible();
    await expect(page.getByRole('heading', { name: '调用记录' })).toHaveCount(0);
    await page.screenshot({ path: `${shotDir}/ops-invocations-OPERATER-section-invisible.png`, fullPage: true });

    // 安全审计员 SECURITY_AUDIT：D55/P18 退出领数据 → 凭据页整体路由层不可达（页级 no-permission=invisible）。
    await setRole(page, 'ROLE_SECURITY_AUDIT');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    await expect(page.getByRole('heading', { name: credHeading })).toHaveCount(0);
  });
});
