import { execFileSync } from 'node:child_process';
import * as path from 'node:path';
import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

// C9 待转报队列样例（national-direct.feature §scenario 2「来自部门X 的申请国家级数据 A_7001」）。
const NATIONAL_APPLY_CODE = 'A_7001_E2E_NATIONAL';

/**
 * 造数：注入一条 channel_class=national 的 dept_approved 申请（待转报态）。无法经
 * in-memory request API 造出该状态组合（见 scripts/seed_national_escalate_fixture.py
 * 头注），故直接 upsert DB apply 记录。针对起栈所用的同一 ZW_BRAIN_DB_PATH。
 * 起栈侧已 export ZW_BRAIN_DB_PATH + ZW_BRAIN_PYTHON_BIN（worktree 指主仓 venv-py312）。
 */
function seedNationalEscalateFixture(): void {
  const repoRoot = path.resolve(__dirname, '..', '..');
  const py = process.env.ZW_BRAIN_PYTHON_BIN || path.join(repoRoot, '.venv', 'bin', 'python');
  const script = path.join(repoRoot, 'scripts', 'seed_national_escalate_fixture.py');
  execFileSync(py, [script], { stdio: 'pipe', env: process.env });
}

/**
 * 国家通道子旅程「角色门 + flag 门」真实 UI 回归（D50 / C7）。
 * 仿 permission_invisibility.spec.ts：DOM 存在性断言（toHaveCount(0) = 完全不渲染，
 * 不是 hidden/disabled）。承「无权 = 不可见」。
 *
 * 起栈前提：ZW_BRAIN_NATIONAL_CHANNEL_ENABLED=1（flag on、未配置 provisioned=false，
 * 即"已上线未接入"真实态）。flag 未开时本 suite skip（不假装）；flag-off→不渲染 面
 * 由 tests/test_national_channel_webui_snapshot.py + tests/test_page_access.py 单测覆盖。
 *
 * IA 重构（拆「办申请」）影响：原 P3「国家通道」tab + 待转报队列 + 转报按钮（p3-tab-national /
 *   p3-national-pane / p3-escalate-btn）随 P3RequestFlow.vue 列表页整面退役，本期**无新前端宿主**
 *   （escalate 后端 capability application.escalate_national 保留、角色门 canViewNationalChannel 保留）。
 *   故下列「P3 国家通道 tab」与「待转报队列」两条 UI 走查暂无可断言的真实 UI 面，honest skip（不假装）；
 *   该 UI 的重新归家是后续项（national-direct.feature 仍 Ready/未绿，本迁移不据此打绿）。flag-off→
 *   不渲染 与角色门由 test_national_channel_gate.py / test_national_channel_webui_snapshot.py 单测覆盖。
 *
 * 仍真跑的守护点（P5 国家扩展要素编制面在新 IA 下原样保留）：
 *   - P5 国家扩展要素入口：canCompileNationalExtElem(MANAGER+BUSIAUDIT) ∧ enabled
 *   - 未配置：P5 发布按钮 disabled，草拟可用
 */

async function nationalChannelEnabled(page: import('@playwright/test').Page): Promise<boolean> {
  const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_BUSIAUDIT`);
  if (!snap.ok()) return false;
  const body = (await snap.json()) as Record<string, unknown>;
  const webui = (body.webui ?? {}) as Record<string, unknown>;
  const nc = (webui.nationalChannel ?? {}) as Record<string, unknown>;
  return nc.enabled === true;
}

test.describe('国家通道 角色门 + flag 门', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('P3 国家通道 tab：BUSIAUDIT 可见 / OPERATER 不渲染', async ({ page }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开（起栈需 ZW_BRAIN_NATIONAL_CHANNEL_ENABLED=1）');
    // IA 重构后无 P3 国家通道 tab 前端宿主（见文件头）——本走查暂无可断言的真实 UI 面。
    // 角色门 canViewNationalChannel 仍由 test_national_channel_gate.py 单测覆盖（不假装有 UI）。
    test.skip(true, '国家通道 P3 tab 随拆「办申请」退役、无新前端宿主（IA 重构）；待 UI 重新归家后恢复');
  });

  test('P5 国家扩展要素入口：MANAGER 可见 / OPERATER 不渲染', async ({ page }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开');

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider');
    await expect(page.getByTestId('national-ext-elem-entry')).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider');
    await expect(page.getByTestId('national-ext-elem-entry')).toHaveCount(0);
  });

  test('P3 国家通道「待转报队列」：看得到 national 待转报单 + 点转报诚实 pending（C9）', async ({
    page,
  }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开');
    // IA 重构后无 P3「待转报队列」+ 转报按钮前端宿主（见文件头）——后端口径自证（snapshot.requests
    // 含该 national dept_approved 单）与 escalate 诚实 pending 由 test_national_escalate.py 单测覆盖；
    // 本走查暂无可点击的真实 UI 面，honest skip（不假装）。
    test.skip(true, '国家通道待转报队列/转报按钮随拆「办申请」退役、无新前端宿主（IA 重构）；待 UI 重新归家后恢复');
    void seedNationalEscalateFixture;
    void NATIONAL_APPLY_CODE;
  });

  test('未配置(provisioned=false)：P5 发布按钮置灰、草拟编制可达', async ({ page }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开');

    // 全程经真实 UI 驱动（写动作走 useActionStub，自带 CSRF token）：新建草稿 → 提交送审
    // → 业务部门审核通过 → 待主管部门审核（发布按钮渲染），再验未配置下 disabled。
    const code = `C_NAT_E2E_${Date.now()}`;
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider/national-ext-elem');

    // 草拟入口（新建草稿）可达。
    await expect(page.getByTestId('nat-ext-create-btn')).toBeVisible();
    await page.getByTestId('nat-ext-new-code').fill(code);
    await page.getByTestId('nat-ext-new-title').fill('国家扩展要素 e2e');
    await page.getByTestId('nat-ext-create-btn').click();

    const row = page.locator('tr', { hasText: code });
    await expect(row).toBeVisible();
    await row.getByTestId('nat-ext-submit-btn').click(); // 草稿 → 待业务部门审核
    await expect(row.getByTestId('nat-ext-business-review-btn')).toBeVisible();
    await row.getByTestId('nat-ext-business-review-btn').click(); // → 待主管部门审核

    // 发布按钮（主管审核并发布·同步国家平台）渲染、但未配置下置灰。
    const publishBtn = row.getByTestId('nat-ext-publish-btn');
    await expect(publishBtn).toBeVisible();
    await expect(publishBtn).toBeDisabled();
  });
});
