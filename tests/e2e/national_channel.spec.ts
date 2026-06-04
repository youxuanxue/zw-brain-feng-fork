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
 * 守护点：
 *   - P3 国家通道 tab：requestFlowRoles.canViewNationalChannel(仅 BUSIAUDIT) ∧ nationalChannel.enabled
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

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/request-flow');
    await expect(page.getByTestId('p3-tab-national')).toBeVisible();
    // 主流程入口 = 「我的申请」视图 tab（三视图重构后；国家通道为独立 tab 共存）。
    await expect(page.getByTestId('p3-view-mine')).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/request-flow');
    await expect(page.getByTestId('p3-tab-national')).toHaveCount(0);
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

    // 造一条 channel_class=national 的 dept_approved 待转报申请（真实 DB apply 记录）。
    seedNationalEscalateFixture();

    // 后端口径自证：snapshot.requests 含该单且 channelClass=='national' / status=='dept_approved'。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_BUSIAUDIT`);
    expect(snap.ok()).toBeTruthy();
    const body = (await snap.json()) as { requests?: Array<Record<string, unknown>> };
    const seeded = (body.requests ?? []).find((r) => String(r.id ?? '') === NATIONAL_APPLY_CODE);
    expect(seeded, '造数申请应进入 snapshot.requests').toBeTruthy();
    expect(String(seeded?.channelClass ?? '')).toBe('national');
    expect(String(seeded?.status ?? '')).toBe('dept_approved');

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/request-flow');

    // 切到「国家通道」tab，待转报队列里看得到该单（不再因 own-items 为空而点不到）。
    await page.getByTestId('p3-tab-national').click();
    const pane = page.getByTestId('p3-national-pane');
    await expect(pane).toBeVisible();
    const row = pane.locator('tr', { hasText: NATIONAL_APPLY_CODE });
    await expect(row, '国家通道待转报队列应含该 national dept_approved 单').toBeVisible();

    // 点「审核通过 + 转报国家平台」→ 未配置(provisioned=false)下诚实 pending（非 404/非报错），
    // 计算态 overlay 显「国家通道转报中」。
    await row.getByTestId('p3-escalate-btn').click();
    await expect(
      row.locator('.status-pill.warn'),
      '转报后行内显示计算态「国家通道转报中」（诚实 pending、非报错）',
    ).toHaveText(/国家通道转报中/);
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
