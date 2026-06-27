import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 第四组：真实导入数据呈现规范化 + 角色投影拆分（客户试用反馈 11/14 + 截图实证）。
 *
 * 守护点：
 *   - 缺陷 1：消费方「我的数据」拆视图（我的申请 / 我的授权）；申请人岗位（操作员/管理员）恒在，
 *     受理岗（业务运营员）退申请人身份故不渲染。受理/审核「待我办理」已迁工作台行内办理
 *     （IA 重构拆「办申请」），故领数据页**无**审核待办 tab——该行为由 workbench_todo_closure 覆盖，
 *     本组只断言领数据无受理/审核 tab、不重测行内办理。
 *   - 缺陷 2：业务运营员工作台待办 = 待发布目录/资源 + 待受理申请/异议 + 平台审（发布/受理/平台审
 *     真实职责；审核类属部门管理员、不入此台 — E2 / 0605 反馈 6.4#11 + D53）。
 *   - 缺陷 3：用途脏值（测试 / 167）不裸奔在需方视图，也不伪装成供数据页待办。
 *
 * IA 重构（拆「办申请」）：消费方「我的申请 / 我的授权」由原 P3「办共享申请」列表页归并到
 *   领数据 P4Delivery（#/delivery-exchange，testid 由 p3-* 迁 p4-*）；列表根 #/request-flow 重定向至此。
 * 投影源：zw-brain-web/src/lib/{roleProjection,dataQuality}.ts + 后端 workbench_backlog_projection.py（待办语义机制单源）
 *        + 后端 discovery_snapshot_projection / provider_snapshot_projection。
 */

test.describe('角色投影三视图 + 数据呈现规范化', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('缺陷1 — 视图分栏：申请人岗位见我的申请/我的授权；受理岗退申请人身份不渲染；领数据无审核 tab', async ({ page }) => {
    // 操作员（申请人）：领数据见「我的申请」「我的授权」。受理/审核已迁工作台行内，本页无审核 tab。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByTestId('p4-view-mine')).toBeVisible();
    await expect(page.getByTestId('p4-view-grants')).toBeVisible();

    // 部门管理员（也是申请人，D55②领数据回归操作员+管理员）：同样见我的申请/我的授权。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByTestId('p4-view-mine')).toBeVisible();
    await expect(page.getByTestId('p4-view-grants')).toBeVisible();

    // 业务运营员（受理岗）：D55③/D57 退申请人身份——领数据「我的申请」「我的授权」对其不渲染
    //（无权=不可见）；其受理动作走工作台行内（workbench_todo_closure 覆盖，本页不出审核 tab）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByTestId('p4-view-mine')).toHaveCount(0);
    await expect(page.getByTestId('p4-view-grants')).toHaveCount(0);
  });

  test('缺陷1 — 我的申请 vs 我的授权数据分流（一视图回答一问题）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/delivery-exchange');
    // 默认「我的申请」pane 可见，「我的授权」pane 隐藏。
    await expect(page.getByTestId('p4-pane-mine')).toBeVisible();
    // 切到「我的授权」。
    await page.getByTestId('p4-view-grants').click();
    await expect(page.getByTestId('p4-pane-grants')).toBeVisible();
  });

  test('缺陷3 — 脏用途值不裸奔在需方列表（测试/167 降级为「未填写用途」）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/delivery-exchange');
    const minePane = page.getByTestId('p4-pane-mine');
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
    // 降级文案存在性：若**本人**有脏单，需方用途列应见「未填写用途」（截图实证集合非空时成立）。
    // 守门口径须与「我的申请」pane 实际过滤一致（roleProjection.myRequests = mine===true ∧ 非授权桶）：
    // 脏单若非本人发起（mine=false，如别部门入站待办 / 已撤回），不进本人 mine pane，不应据此断言
    // 该 pane 必现降级文案——否则 clean 库下「全部脏单皆 mine=false、本人 pane 为空」时假阳性。
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
    if (snap.ok()) {
      const body = (await snap.json()) as Record<string, unknown>;
      const reqs = (body.requests ?? []) as Array<Record<string, unknown>>;
      const dirtyInMine = reqs.filter(
        (r) =>
          r.purposeDirty === true &&
          r.mine === true &&
          r.status !== 'granted' &&
          r.status !== 'effective',
      ).length;
      if (dirtyInMine > 0) {
        await expect(purposeCells.filter({ hasText: '未填写用途' }).first()).toBeVisible();
      }
    }
  });

  test('缺陷2 — 业务运营员工作台待办 = 待发布/待受理/平台审（发布·受理职责，非审核错配）', async ({ page }) => {
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
    // 出现的待办标题应落在业务运营员真实职责词表内（发布 / 受理 / 转报 + 平台审，白话动宾）。
    // 机制单源 = 后端 workbench_backlog_projection（真实库现算）：待发布目录/资源、待受理申请/异议、
    // 待平台审核目录（D57⑧ 两级各自入账）+ 国家通道待转报（D50/C9）。
    const allowed = ['待发布', '待受理', '待平台审核', '待转报'];
    for (const title of todoTitles) {
      expect(allowed.some((a) => title.includes(a)), `工作台待办「${title}」应属发布/受理/转报职责`).toBeTruthy();
    }
  });

  test('缺陷3 — 供数据页不再渲染用途补全待办队列', async ({ page }) => {
    // 操作员：无此队列。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider');
    await expect(page.getByTestId('data-quality-queue')).toHaveCount(0);

    // 业务运营员：历史导入脏用途不再投成供数据页待办；用途补正应回到原申请链路或离线清洗。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider');
    await expect(page.getByTestId('data-quality-queue')).toHaveCount(0);
    await expect(page.getByText('待补全的申请用途')).toHaveCount(0);
  });
});
