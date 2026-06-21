// 受理/审核两级链路真 UI 点击穿透走查（Wave 1.5 验收证据采集；评审走查用，可独立重跑）。
// 链路：操作员发起有条件申请（API 铸单）→ 业务运营员受理 → 部门管理员审核通过 → 已授权。
// 受理/审核动作经审批详情深链 #/request-flow/review/:id（KEPT，决策组件双宿主之一）真 UI 点击。
// 另验：业务运营员（受理岗，退申请人身份）领数据无「我的申请/我的授权」视图；操作员工作台为「申请进度」语境。
// IA 重构（拆「办申请」）：受理/审核也可在工作台行内办理（workbench_todo_closure 覆盖）；本走查走深链宿主。
// 证据截图落 .testing/acceptance/wave15-two-stage-walkthrough/。
import { expect, test } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const SHOTS = '.testing/acceptance/wave15-two-stage-walkthrough';

test('两级链路：受理(业务运营员)→审核(部门管理员)→已授权', async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  // 0) 走查单由采证脚本预先在真实库铸好（有条件共享 shared_type=2、status=submitted、
  //    owner_org=会话方向所属部门），单号经 WALK_REQ_ID 传入——本 spec 只走真 UI 两级点击。
  const reqId = process.env.WALK_REQ_ID ?? '';
  test.skip(!reqId, '需 WALK_REQ_ID（预铸的有条件 submitted 单）');

  // 1) 业务运营员（受理岗）：D55③/D57 退申请人身份——领数据「我的申请/我的授权」视图对其不渲染。
  //    （列表根 #/request-flow 已重定向领数据；受理动作走下方审批详情深链宿主。）
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/delivery-exchange');
  await expect(page.getByTestId('p4-view-mine')).toHaveCount(0);
  await expect(page.getByTestId('p4-view-grants')).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/1-busiaudit-acceptance-workbench.png`, fullPage: true });

  // 2) 业务运营员受理（第一级）：进详情点「受理」。
  await gotoHash(page, `#/request-flow/review/${reqId}`);
  const acceptBtn = page.getByRole('button', { name: '受理', exact: true });
  await expect(acceptBtn).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/2-busiaudit-before-accept.png`, fullPage: true });
  await acceptBtn.click();
  await expect(page.locator('body')).toContainText(/已受理待审核|受理通过/, { timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/3-busiaudit-accepted.png`, fullPage: true });

  // 3) 部门管理员审核（第二级）：待我办理收到 → 详情点「审核通过」→ 已授权。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, `#/request-flow/review/${reqId}`);
  const deptBtn = page.getByRole('button', { name: '审核通过', exact: true });
  await expect(deptBtn).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/4-manager-before-review.png`, fullPage: true });
  await deptBtn.click();
  await expect(page.locator('body')).toContainText(/已授权|审核通过/, { timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/5-manager-granted.png`, fullPage: true });
});

test('操作员工作台为「申请进度」语境（非审批待办）', async ({ page }, testInfo) => {
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/workbench');
  await expect(page.locator('body')).toContainText('申请进度', { timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/6-operater-workbench-progress.png`, fullPage: true });
});
