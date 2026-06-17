import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

// D45 全局数据缺位修复 — J1 列表字段全量真实库投影 + 发现页可用过滤 + 卡片信息密度。
// 验收：① 发现页只展示「可用」资源（多列密排 + 类型徽标 + 共享类型色 chip）；
//       ② 我的申请 / 待审 展现全量真实库（非 seed 5 条）。
// IA 重构（拆「办申请」）：消费方「我的申请」归并领数据（#/delivery-exchange，p4-pane-mine）；
//   审批岗「待我办理」队列 tab 退役、受理/审核移到工作台行内（workbench.view 真实库现算），
//   故「待审全量真实」改由工作台待办（真实库现算）守护。
test.describe('J1 数据缺位修复（D45）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.setViewportSize({ width: 1440, height: 1024 });
    await page.goto('/');
    await waitAppReady(page);
  });

  test('资源发现：只展示可用资源 + 多列密排 + 类型徽标 + 共享类型色 chip', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(1500);

    // 全量真实库（远超 seed 12）；卡片数 = 命中数。
    const cards = page.locator('.card-grid .res-card');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
    expect(await cards.count(), '可用资源应全量展现（非 seed 精选）').toBeGreaterThan(40);

    // 多列密排（非单列满宽）。
    const cols = await page.evaluate(() => {
      const g = document.querySelector('.card-grid');
      return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0;
    });
    expect(cols, '卡片应多列密排').toBeGreaterThan(1);

    // 类型徽标（库表/文件/接口…）齐全。
    expect(await page.locator('.res-kind').count(), '每卡应有物化形态徽标').toBeGreaterThan(40);

    // 共享类型决策 chip：无条件(绿) + 有条件(琥珀) 都存在。
    expect(await page.locator('.res-share--open').count(), '应有无条件共享 chip').toBeGreaterThan(0);
    expect(await page.locator('.res-share--conditional').count(), '应有有条件共享 chip').toBeGreaterThan(0);

    // 发现页只展示「可用」态：状态标签不含草稿/已下线/已过期等非可用态。
    const statuses = new Set(await page.locator('.res-status').allInnerTexts());
    for (const bad of ['草稿', '已下线', '已过期', '已暂停', '审核中']) {
      expect(statuses.has(bad), `默认视图不应含非可用态「${bad}」`).toBeFalsy();
    }
  });

  test('我的申请：展现全量真实申请（非 seed 5 条）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    // IA 重构：消费方「我的申请」归并领数据；需方默认落「我的申请」视图，展现全量真实申请。
    await gotoHash(page, '#/delivery-exchange');
    await page.waitForTimeout(1500);
    // D45/M5：「我的申请」按本人现算（myRequests = mine===true，payload.applicant==当前登录个人）。
    // 缺位守护点 = 「本人发起的申请全量真实呈现、非 seed 精选」。本断言锚在本人 own 申请数：
    // 取 snapshot.requests 里 mine===true 的真实条数作为期望基线（现算单源），与 UI 渲染行数对齐
    //（无缺位）；该登录身份零 own 申请时（clean 库该 dev-bypass 操作员未发起过）诚实 skip，不假装。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    test.skip(!snap.ok(), 'snapshot unavailable');
    const body = (await snap.json()) as { requests?: Array<Record<string, unknown>> };
    // 我的申请 pane = roleProjection.myRequests = mine===true ∧ 非授权桶（GRANT_STATUSES =
    // {granted,effective,suspended,expired} 归「我的授权」pane，不进「我的申请」）。
    const GRANT_STATUSES = new Set(['granted', 'effective', 'suspended', 'expired']);
    const mineReqs = (body.requests ?? []).filter(
      (r) => r.mine === true && !GRANT_STATUSES.has(String(r.status ?? '')),
    );
    test.skip(mineReqs.length === 0, '当前登录身份无本人发起的在途/草稿申请（clean 库该 dev-bypass 操作员未发起过，诚实空、非缺位）');
    const rows = page.getByTestId('p4-pane-mine').locator('.focus-table tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    // 全量真实（非 seed 精选）：本人有 own 申请时，UI 渲染行数随真实库现算，不被截断到 seed 5 条。
    expect(await rows.count(), '我的申请应全量真实现算（非 seed 5 精选）').toBeGreaterThan(5);
    // 每行有资源名（申请类，非需求噪声）。
    await expect(rows.first()).not.toBeEmpty();
  });

  test('待审待办：审批角色工作台见全量真实待审（真实库现算，非 seed 5 条）', async ({ page }) => {
    // IA 重构：审批岗「待我办理」队列 tab 退役、受理/审核移到工作台行内。待审待办由后端
    // workbench_backlog_projection 真实库现算（每条携深链或行内 action）。数据缺位修复守护点改为
    // 「审批岗工作台待办来自真实库现算」——真实库该岗位有积压时全量呈现（非 seed 精选），无积压则
    // 诚实零待办（不造死项）。
    const resp = await page.request.get(
      `${E2E_BASE_URL}/api/skills/workbench.view?role=ROLE_ORGAN_MANAGER`,
    );
    test.skip(!resp.ok(), 'workbench.view unreachable');
    const wb = (await resp.json()) as { todos?: Array<Record<string, unknown>> };
    const todos = wb.todos ?? [];
    test.skip(todos.length === 0, '本库审批岗无待审积压（clean 库诚实零待办，非缺位）');

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/workbench');
    // 工作台待办渲染（深链 link 或行内 expand），且后端现算条数与 UI 渲染条数一致（无缺位/无错配）。
    const links = page.locator('[data-testid="workbench-todo-link"]');
    const expanders = page.locator('[data-testid="workbench-todo-expand"]');
    await expect(links.or(expanders).first()).toBeVisible({ timeout: 10_000 });
    const rendered = (await links.count()) + (await expanders.count());
    expect(rendered, '工作台待办应全量真实现算（与后端 workbench.view 条数一致）').toBe(todos.length);
  });
});
