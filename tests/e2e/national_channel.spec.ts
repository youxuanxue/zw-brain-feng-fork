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
 * IA 重构（拆「办申请」）后，国家通道待转报归位工作台行内办理：BUSIAUDIT 在 #/workbench
 * 展开「国家通道待转报」聚合待办，逐条点「转报国家平台」；OPERATER 无该待办。flag-off→
 * 不渲染 与角色门由 test_national_channel_gate.py / test_national_channel_webui_snapshot.py 单测覆盖。
 *
 * 仍真跑的守护点（P5 国家扩展要素编制面在新 IA 下原样保留）：
 *   - P5 国家扩展要素入口：canCompileNationalExtElem(MANAGER+BUSIAUDIT) ∧ enabled
 *   - 未配置：P5 同步按钮 disabled，草拟与审核可用但停在待同步
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

  test('国家通道待转报工作台入口：BUSIAUDIT 可见 / OPERATER 不渲染', async ({ page }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开（起栈需 ZW_BRAIN_NATIONAL_CHANNEL_ENABLED=1）');
    seedNationalEscalateFixture();

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');
    await expect(page.getByTestId('workbench-todo').filter({ hasText: '国家通道待转报' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/workbench');
    await expect(page.getByTestId('workbench-todo').filter({ hasText: '国家通道待转报' })).toHaveCount(0);
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

  test('工作台国家通道「待转报队列」：看得到 national 待转报单 + 点转报诚实 pending（C9）', async ({
    page,
  }) => {
    test.skip(!(await nationalChannelEnabled(page)), '国家通道 flag 未开');
    seedNationalEscalateFixture();

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');
    const todo = page.getByTestId('workbench-todo').filter({ hasText: '国家通道待转报' });
    await expect(todo).toBeVisible();
    await todo.getByTestId('workbench-todo-expand').click();

    const item = todo.getByTestId('workbench-decision-item').filter({ hasText: NATIONAL_APPLY_CODE });
    await expect(item).toBeVisible();
    await item.getByTestId('workbench-todo-decision').filter({ hasText: '转报国家平台' }).click();
    await expect(page.locator('.toast-stack')).toContainText('国家通道待接入', { timeout: 15_000 });
  });

  test('未配置(provisioned=false)：P5 同步按钮置灰、草拟编制可达', async ({ page }) => {
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

    await expect(row.getByTestId('nat-ext-supervisor-review-btn')).toBeVisible();
    await row.getByTestId('nat-ext-supervisor-review-btn').click(); // → 待同步国家平台

    // 同步按钮渲染、但国家通道未就绪下置灰，不标记已同步国家平台。
    const publishBtn = row.getByTestId('nat-ext-publish-btn');
    await expect(publishBtn).toBeVisible();
    await expect(publishBtn).toBeDisabled();
  });
});
