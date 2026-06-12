// 权限矩阵全角色真 UI 走查（permission-matrix-0610 · D37 验收证据采集，可独立重跑）。
//
// 对照业务方权威尺子（重构平台权限梳理-0609.docx + 平台系统角色菜单梳理v5.xlsx，
// 经 D55 裁决）验证三层：
//   1) 导航矩阵 5 角色 × 10 壳——可见即有权、无权不渲染（期望表硬编码作独立 oracle，
//      刻意不 import productShellNav.ts，避免「自己对自己」同义反复）；
//   2) 写按钮可见性——异议详情 提交/评价/归档 走 action gate（本轮修复回归）；
//   3) 两条业务流——受理两级（业务运营员受理→部门管理员审核，D55/P21）+
//      目录编制两级审核发布（操作员编制→部门审→平台审→运营员/管理员发布）。
// 证据截图落 .testing/acceptance/permission-matrix-0610/。
import { expect, test } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const SHOTS = '.testing/acceptance/permission-matrix-0610';

const ALL_NAV_LABELS = [
  '工作台', '找数据', '办申请', '领数据', '供数据',
  '查审计', '服务调用监控', '外部系统', '流程表单', '身份治理',
] as const;

// 独立 oracle：v5 菜单矩阵 + D55 §四 目标态（P17/P18/P13/P2/P3/P4/P8/P9 收权后）。
const NAV_MATRIX: Record<string, readonly string[]> = {
  // 部门操作员（做）：用数 4 壳 + 供数（在线编制 v5 §166）。
  ROLE_ORGAN_OPERATER: ['工作台', '找数据', '办申请', '领数据', '供数据'],
  // 部门管理员（审）：操作员面 + 服务调用监控只读；退审计日志（P9）。
  ROLE_ORGAN_MANAGER: ['工作台', '找数据', '办申请', '领数据', '供数据', '服务调用监控'],
  // 业务运营员（管/发布/受理）：退领数据（D53⑥/P13）、保查审计 + 服务调用监控。
  ROLE_BUSIAUDIT: ['工作台', '找数据', '办申请', '供数据', '查审计', '服务调用监控'],
  // 安全审计员（查，纯只读）：仅审计两面（P17/P18 退找数/领数）。
  ROLE_SECURITY_AUDIT: ['工作台', '查审计', '服务调用监控'],
  // 平台运维员（维）：后台四模块中的运维三面 + 服务调用监控（P2/P3/P4/P8）。
  ROLE_SYSTEM: ['工作台', '服务调用监控', '外部系统', '流程表单', '身份治理'],
};

// 铸态一律走**无 cookie** 的独立 APIRequestContext：带 cookie 的 page.request POST 会触发
// 服务端 CSRF 拦截（dev 仅无 cookie 请求豁免，同 curl 走查路径）。
async function invoke(
  api: import('@playwright/test').APIRequestContext,
  skill: string,
  data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/${skill}`, { data });
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  return (body.result ?? body) as Record<string, unknown>;
}

/** 状态词汇桥接（方案 B，j1-runtime-write-path-dual-track）后，运行时直提的有条件单
 *  直接落 'submitted' 进受理两级队列——本走查**自铸**直提单（刻意不传 shared_type，
 *  验证 access_policy 回源解析），不再依赖预铸/legacy 存量单。同资源已有在办申请会被
 *  拦（重复跑 / 脏 DB），逐个候选有条件资源试到成功；铸出非 submitted 即桥接回归，返
 *  特殊标记令断言失败而非静默 skip。 */
async function mintConditionalDirectSubmit(
  api: import('@playwright/test').APIRequestContext,
): Promise<{ reqId: string; status: string } | null> {
  const snap = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  const body = (await snap.json().catch(() => ({}))) as Record<string, unknown>;
  const discovery = (body.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  const conditional = resources.filter((r) => String(r.shareType ?? '') === '有条件共享');
  for (const r of conditional.slice(0, 12)) {
    const created = await invoke(api, 'application.resource.submit', {
      resource_id: String(r.id ?? ''),
      role: 'ROLE_ORGAN_OPERATER',
      confirmed: true,
      purpose: 'e2e 受理两级全链走查：有条件直提',
      query: 'e2e two-stage chain',
    });
    const reqId = String(created.request_id ?? '');
    if (reqId) return { reqId, status: String(created.status ?? '') };
  }
  return null;
}

test.describe('权限矩阵走查（permission-matrix-0610）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto(E2E_BASE_URL);
    await waitAppReady(page);
  });

  test('导航矩阵：5 角色 × 10 壳，可见即有权、无权不渲染', async ({ page }) => {
    test.setTimeout(180_000);
    for (const [role, visible] of Object.entries(NAV_MATRIX)) {
      await setRole(page, role);
      await gotoHash(page, '#/workbench');
      for (const label of ALL_NAV_LABELS) {
        const item = page.locator('.side-nav-item-label', { hasText: label });
        if (visible.includes(label)) {
          await expect(item, `${role} 应可见「${label}」`).toHaveCount(1);
        } else {
          await expect(item, `${role} 不应渲染「${label}」（无权=不可见）`).toHaveCount(0);
        }
      }
      await page.screenshot({ path: `${SHOTS}/nav-${role}.png`, fullPage: true });
    }
  });

  test('异议详情写按钮走 action gate：提交=申请方可见、运营员/审计员不渲染', async ({ page, playwright }) => {
    test.setTimeout(120_000);
    const api = await playwright.request.newContext();
    let objectionId = '';
    try {
      const q = await invoke(api, 'catalog.entry.query', {
        role: 'ROLE_ORGAN_OPERATER',
        limit: 1,
        confirmed: true,
      });
      const items = (q.items ?? []) as Array<Record<string, unknown>>;
      const code = String(items[0]?.catalog_code ?? '');
      test.skip(!code, '真实库无目录可挂异议');
      const created = await invoke(api, 'objection.case.create', {
        target_type: 'catalog',
        target_id: code,
        title: 'e2e 权限矩阵走查异议（draft）',
        role: 'ROLE_ORGAN_OPERATER',
        confirmed: true,
      });
      objectionId = String(created.id ?? '');
    } finally {
      await api.dispose();
    }
    test.skip(!objectionId, '铸 draft 异议失败');

    // 申请方（操作员）：draft 单可见「提交至平台」。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/request-flow/objection/${objectionId}`);
    await expect(page.getByRole('button', { name: '提交至平台' })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/objection-submit-OPERATER-visible.png`, fullPage: true });

    // 业务运营员：办受理不替人提交（objection.case.submit={OPERATER,MANAGER}）→ 按钮不渲染。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/request-flow/objection/${objectionId}`);
    await expect(page.locator('body')).toContainText(objectionId);
    await expect(page.getByRole('button', { name: '提交至平台' })).toHaveCount(0);
    await page.screenshot({ path: `${SHOTS}/objection-submit-BUSIAUDIT-invisible.png`, fullPage: true });

    // 安全审计员：request-flow shell 整面不可达（页级无权=不可见，路由层 bounce）。
    await setRole(page, 'ROLE_SECURITY_AUDIT');
    await gotoHash(page, `#/request-flow/objection/${objectionId}`);
    await expect(page.getByRole('button', { name: '提交至平台' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '归档关闭' })).toHaveCount(0);
  });

  test('业务流 1（D55/P21 受理两级全链）：自铸有条件直提单 → 运营员受理 → 管理员审核 → 已授权；操作员无审批按钮', async ({ page, playwright }) => {
    test.setTimeout(180_000);
    // 自铸（不依赖预铸/legacy 单）——方案 B 后直提即落 submitted。
    const api = await playwright.request.newContext();
    let minted: { reqId: string; status: string } | null = null;
    try {
      minted = await mintConditionalDirectSubmit(api);
    } finally {
      await api.dispose();
    }
    test.skip(!minted, '真实库无可用「有条件共享」资源（候选 12 个均有在办申请）');
    const { reqId, status } = minted!;
    // 桥接回归锚：直提即受理两级入口态（铸出 pending = 状态词汇双轨回潮，必须红）。
    expect(status, '有条件直提单应落 submitted（j1-runtime-write-path-dual-track 方案 B）').toBe('submitted');

    // 申请人（操作员）打开同一单：受理/审核按钮不渲染（状态机动作无权=不可见）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/request-flow/review/${reqId}`);
    await expect(page.getByRole('button', { name: '受理', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '审核通过', exact: true })).toHaveCount(0);

    // 第一级：业务运营员受理。断言以**按钮消失 + 状态文案**为准——不可断 body 含按钮自身
    // 文字（点击失败时按钮仍在，body 文案恒真 → 假绿，旧 spec 即栽在这里）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/request-flow/review/${reqId}`);
    const acceptBtn = page.getByRole('button', { name: '受理', exact: true });
    await expect(acceptBtn).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow1-busiaudit-before-accept.png`, fullPage: true });
    await acceptBtn.click();
    await expect(acceptBtn).toHaveCount(0, { timeout: 15_000 });
    await expect(page.locator('body')).toContainText('已受理待审核', { timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow1-busiaudit-accepted.png`, fullPage: true });

    // 第二级：部门管理员审核通过 → 已授权（dev 会话 org 经 ZW_BRAIN_DEV_IAM_BYPASS_ORG
    // 对齐资源提供方，R11 方向 guard 真放行——start-local.sh 已默认省大数据局）。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/request-flow/review/${reqId}`);
    const deptBtn = page.getByRole('button', { name: '审核通过', exact: true });
    await expect(deptBtn).toBeVisible({ timeout: 15_000 });
    await deptBtn.click();
    await expect(deptBtn).toHaveCount(0, { timeout: 15_000 });
    await expect(page.locator('body')).toContainText('已授权', { timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow1-manager-granted.png`, fullPage: true });
  });

  test('业务流 2（J2 目录两级审核发布）：部门审→平台审→发布卡仅发布岗可见', async ({ page, playwright }) => {
    test.setTimeout(180_000);
    // 自铸目录草稿并提审（操作员，API 铸态；两级审核与发布走真 UI）。
    const api = await playwright.request.newContext();
    const runTag = Date.now().toString(36);
    const code = `j2-inline-${runTag}-e2epm`;
    const title = `e2e 权限矩阵走查目录-${runTag}`;
    let minted = false;
    try {
      const created = await invoke(api, 'catalog.entry.create_draft', {
        catalog_code: code,
        title,
        owner_org_id: '11370000MB284651XL',
        region_code: '370100',
        // 基本信息必填全集（0611 口径确认单 §A：submit_review 对在线编制目录强校验）
        summary_json: {
          catalog_type: '业务目录',
          domain: '营商环境',
          source_system: 'e2e 权限矩阵来源系统',
          application_scenario: 'e2e 权限矩阵走查',
          resource_format: '0200',
          business_update_cycle: '2',
          data_update_cycle: '2',
          shared_way: 'api',
          shared_type: '1',
          open_type: '3',
          description: 'e2e 权限矩阵走查目录种子',
        },
        role: 'ROLE_ORGAN_OPERATER',
        confirmed: true,
      });
      const submitted = await invoke(api, 'catalog.entry.submit_review', {
        catalog_code: code,
        role: 'ROLE_ORGAN_OPERATER',
        confirmed: true,
      });
      minted = Boolean(created) && Boolean(submitted);
    } finally {
      await api.dispose();
    }
    test.skip(!minted, '铸目录草稿/提审失败');

    // 操作员：审核收件箱整页不可达（路由 override 仅 MANAGER/BUSIAUDIT）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider/inbox/catalog-review');
    await expect(page.getByTestId('catalog-review-approve-btn')).toHaveCount(0);

    // 第一级 部门审（部门管理员）：行内「通过」。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider/inbox/catalog-review');
    const deptRow = page.locator('tr', { hasText: title });
    await expect(deptRow.getByTestId('catalog-review-approve-btn')).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow2-manager-dept-review.png`, fullPage: true });
    await deptRow.getByTestId('catalog-review-approve-btn').click();
    await expect(deptRow).toHaveCount(0, { timeout: 15_000 });

    // 第二级 平台审（业务运营员）：同收件箱平台审视图「通过」。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider/inbox/catalog-review');
    const platRow = page.locator('tr', { hasText: title });
    await expect(platRow.getByTestId('catalog-review-approve-btn')).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow2-busiaudit-platform-review.png`, fullPage: true });
    await platRow.getByTestId('catalog-review-approve-btn').click();
    await expect(platRow).toHaveCount(0, { timeout: 15_000 });

    // 发布队列：发布卡仅发布岗（catalog.entry.publish={MANAGER,BUSIAUDIT}）可见；操作员不渲染。
    const publishCard = page.getByRole('region', { name: '待发布目录' });
    await gotoHash(page, '#/provider');
    await expect(publishCard).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOTS}/flow2-busiaudit-publish-card.png`, fullPage: true });
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider');
    await expect(publishCard).toHaveCount(0);
  });
});
