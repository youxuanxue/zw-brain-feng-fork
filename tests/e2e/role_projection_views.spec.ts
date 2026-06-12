import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 第四组：真实导入数据呈现规范化 + 角色投影拆分（客户试用反馈 11/14 + 截图实证）。
 *
 * 守护点：
 *   - 缺陷 1：P3「办共享申请」拆三视图（我的申请 / 待我办理 / 我的授权）；待我办理无权角色不渲染。
 *   - 缺陷 2：业务运营员工作台待办 = 待发布目录/资源 + 待受理申请/异议 + 待汇总需求（发布/受理/汇总
 *     真实职责；审核类属部门管理员、不入此台 — E2 / 0605 反馈 6.4#11 + D53）。
 *   - 缺陷 3：用途脏值（测试 / 167）不裸奔在需方视图；供方数据质量队列计数正确。
 *
 * 投影源：zw-brain-web/src/lib/{roleProjection,dataQuality}.ts + 后端 workbench_backlog_projection.py（待办语义机制单源）
 *        + 后端 discovery_snapshot_projection / provider_snapshot_projection。
 */

test.describe('角色投影三视图 + 数据呈现规范化', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('缺陷1 — 三视图分栏：我的申请/我的授权恒在；待我办理仅审批角色渲染', async ({ page }) => {
    // 操作员（纯需方）：有「我的申请」「我的授权」，无「待我办理」（无权=不可见）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/request-flow');
    await expect(page.getByTestId('p3-view-mine')).toBeVisible();
    await expect(page.getByTestId('p3-view-grants')).toBeVisible();
    await expect(page.getByTestId('p3-view-todo')).toHaveCount(0);

    // 部门管理员（审批人）：待我办理出现。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/request-flow');
    await expect(page.getByTestId('p3-view-todo')).toBeVisible();

    // 业务运营员（平台复核）：待我办理出现。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/request-flow');
    await expect(page.getByTestId('p3-view-todo')).toBeVisible();
  });

  test('缺陷1 — 我的申请 vs 我的授权数据分流（一视图回答一问题）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/request-flow');
    // 默认「我的申请」pane 可见，「我的授权」pane 隐藏。
    await expect(page.getByTestId('p3-pane-mine')).toBeVisible();
    // 切到「我的授权」。
    await page.getByTestId('p3-view-grants').click();
    await expect(page.getByTestId('p3-pane-grants')).toBeVisible();
  });

  test('缺陷3 — 脏用途值不裸奔在需方列表（测试/167 降级为「未填写用途」）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/request-flow');
    const minePane = page.getByTestId('p3-pane-mine');
    await expect(minePane).toBeVisible();
    // 「用途」是表格第 3 列；脏值在该列降级为「未填写用途」，原文不得出现。
    // （注意：脏串可能合法出现在「资源」名里——如「代理服务测试-1」——故只断言用途列。）
    const purposeCells = minePane.locator('tbody tr td:nth-child(3)');
    const purposeTexts = await purposeCells.allInnerTexts();
    const dirtyLiterals = ['测试', '169,167', '167'];
    for (const txt of purposeTexts) {
      const trimmed = txt.trim();
      for (const lit of dirtyLiterals) {
        // 用途列精确等于脏串 = 裸奔（降级后应是「未填写用途」或合法用途，绝不等于脏串）。
        expect(trimmed).not.toBe(lit);
      }
    }
    // 降级文案存在性：若后端有脏单，需方用途列应见「未填写用途」（截图实证集合非空时成立）。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    if (snap.ok()) {
      const body = (await snap.json()) as Record<string, unknown>;
      const reqs = (body.requests ?? []) as Array<Record<string, unknown>>;
      const dirtyInMine = reqs.filter(
        (r) => r.purposeDirty === true && r.status !== 'granted' && r.status !== 'effective',
      ).length;
      if (dirtyInMine > 0) {
        await expect(purposeCells.filter({ hasText: '未填写用途' }).first()).toBeVisible();
      }
    }
  });

  test('缺陷2 — 业务运营员工作台待办 = 待发布/待受理/待汇总（发布·受理·汇总职责，非审核错配）', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');
    // 业务运营员待办注册表类目（计数 0 的不渲染，故用「出现的都属正确类目」+「错配内容不出现」双断言）。
    const todoTitles = await page.locator('.p1-row-title').allInnerTexts();
    // 错配内容必须不在工作台待办出现：①工程黑话（业务方原话「不对路」示例）；
    // ②部门审核类（目录/资源部门审批属部门管理员职责，E2 已从业务运营员台移除——其待办
    // 统一以「待审核…」开头；D57⑧ 后业务运营员新增的「待平台审核目录」是平台审职责本职，
    // 不在错配之列，故黑名单收敛到「待审核」前缀而非泛「审核」字）。
    for (const wrong of ['ledger.entity.base.read', 'capability', 'projection', '待审核']) {
      expect(todoTitles.join(' ')).not.toContain(wrong);
    }
    // 出现的待办标题应落在业务运营员真实职责词表内（发布 / 受理 / 汇总 + 平台审，白话动宾）。
    // 机制单源 = 后端 workbench_backlog_projection（真实库现算）：待发布目录/资源、待受理申请/异议、
    // 待汇总需求（E2 / 0605 反馈 6.4#11 + D53）+ 待平台审核目录（D57⑧ 两级各自入账）。
    const allowed = ['待发布', '待受理', '待汇总', '待平台审核'];
    for (const title of todoTitles) {
      expect(allowed.some((a) => title.includes(a)), `工作台待办「${title}」应属发布/受理/汇总职责`).toBeTruthy();
    }
  });

  test('缺陷3 — 供方数据质量队列仅业务运营员可见（无权=不可见）', async ({ page }) => {
    // 操作员：数据质量队列不渲染。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider');
    await expect(page.getByTestId('data-quality-queue')).toHaveCount(0);

    // 业务运营员：数据质量队列渲染，计数与真实脏单一致（≥ 截图实证的脏单数）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider');
    const queue = page.getByTestId('data-quality-queue');
    await expect(queue).toBeVisible();
    const countText = await page.getByTestId('data-quality-count').innerText();
    const count = parseInt(countText.replace(/[^0-9]/g, ''), 10) || 0;
    // 截图实证脏值集合 ≥ 1（测试 / 167 / 169,167 / 空）。真实库非空时应 ≥ 1。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_BUSIAUDIT`);
    if (snap.ok()) {
      const body = (await snap.json()) as Record<string, unknown>;
      const reqs = (body.requests ?? []) as Array<Record<string, unknown>>;
      const dirty = reqs.filter((r) => r.purposeDirty === true).length;
      expect(count).toBe(dirty);
    }
  });
});
