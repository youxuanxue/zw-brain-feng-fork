import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.beforeEach(async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);
  await page.goto('/');
  await waitAppReady(page);
});

test('P1 工作台装载 live 待办', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/workbench');
  await expect(page.locator('.p1-hero-title')).toContainText('待办');
});

test('P2 搜索即时筛选列表', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/discovery');
  const before = await page.locator('.res-card').count();
  expect(before).toBeGreaterThan(6);
  await page.locator('#p2-search').fill('营商环境');
  await page.waitForTimeout(500);
  const after = await page.locator('.res-card').count();
  expect(after).toBeLessThan(before);
  await expect(page.locator('.focus-head, .panel').first()).toContainText('命中');
});

test('P3 审批中申请点击补件给出中文提示', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow/request/REQ-2026-05-25-0002');
  await page.getByRole('button', { name: '补件 / 重新提交' }).click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).toContainText('暂不可重新提交');
  await expect(page.locator('body')).not.toContainText('resource_id');
});

test('P3 办共享申请页可达（我的申请视图）', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow');
  // 三视图重构：页标题统一「办共享申请」，需方默认落「我的申请」视图。
  await expect(page.getByRole('heading', { name: '办共享申请' })).toBeVisible();
  await expect(page.getByTestId('p3-view-mine')).toBeVisible();
});

test('P3 部门操作员查看在途申请不进审批页', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow');
  const viewBtn = page.getByRole('button', { name: '查看' }).first();
  await expect(viewBtn).toBeVisible();
  await viewBtn.click();
  await page.waitForTimeout(600);
  expect(page.url()).toMatch(/#\/request-flow\/request\//);
  await expect(page.getByRole('button', { name: '通过' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '补件 / 重新提交' })).toBeVisible();
});

test('P3 部门操作员直达审批路由会回到申请详情', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow/review/REQ-2026-05-25-0002');
  await page.waitForTimeout(600);
  expect(page.url()).toMatch(/#\/request-flow\/request\/REQ-2026-05-25-0002/);
  await expect(page.getByRole('button', { name: '通过' })).toHaveCount(0);
});

test('P3 部门管理员看待我办理（审批队列）', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/request-flow');
  // 三视图重构：审批角色见「待我办理」tab；点开后审批队列含去审批深链。
  await expect(page.getByTestId('p3-view-todo')).toBeVisible();
  await page.getByTestId('p3-view-todo').click();
  await expect(page.locator('a[href*="#/request-flow/review/"]').first()).toBeVisible();
});

test('P4 交付任务页可达', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/delivery-exchange');
  await expect(page.getByRole('heading', { name: '交付任务' })).toBeVisible();
  const body = await page.locator('#app-router').innerText();
  expect(body).not.toMatch(/\bgranted\b/i);
  expect(body).not.toMatch(/\bissued\b/i);
});

test('岗位切换：业务运营员无权进提供方页', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider');
  await page.waitForTimeout(1000);
  expect(page.url()).not.toMatch(/#\/provider/);
});

test('岗位切换：部门管理员可进提供方管理', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider');
  await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
});

test('P5 子路由：反向编目向导可点通', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/reverse-catalog');
  await expect(page.getByRole('heading', { name: '反向编目向导' })).toBeVisible();
});

test('P5 反向编目：部门管理员可生成字段建议', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/reverse-catalog');
  await page.locator('.gov-select').selectOption({ index: 1 });
  await page.getByRole('button', { name: '生成字段建议' }).click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).toContainText('字段建议已生成');
  await expect(page.locator('body')).not.toContainText('missing required input field');
});

test('P5 反向编目：业务运营员不显示创建草稿按钮', async ({ page }) => {
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/wizard/reverse-catalog');
  await page.locator('.gov-select').selectOption({ index: 1 });
  await expect(page.getByRole('button', { name: '创建反向编目草稿' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '生成字段建议' })).toBeVisible();
});

test('P3 撤回申请不再误调目录 withdraw', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow/request/REQ-2026-05-25-0002');
  await page.getByRole('button', { name: '撤回申请' }).click();
  await page.waitForTimeout(600);
  await expect(page.locator('body')).toContainText('暂不可撤回');
  await expect(page.locator('body')).not.toContainText('catalog_code');
});

test('P5 API 服务化向导提交不报缺字段', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/api-service');
  await page.locator('.gov-select').selectOption({ index: 1 });
  await page.getByRole('button', { name: '探测连通性' }).click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).not.toContainText('missing required input field');
});

test('P5 质量规则向导保存不报缺字段', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/quality-rule');
  await page.locator('.gov-select').selectOption({ index: 1 });
  await page.getByRole('button', { name: '保存质量规则' }).click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).not.toContainText('missing required input field');
});

test('P7 列表真接 topic.package.query 展示 sd-default 3 标杆', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/zones-pack');
  await page.waitForTimeout(800);
  await expect(page.getByText('医疗救助信息专题包')).toBeVisible();
  await expect(page.getByText('医保码信息专题包')).toBeVisible();
  await expect(page.getByText('异地就医专题包')).toBeVisible();
});

test('P7 订阅专题走 topic.package.subscribe', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/zones-pack');
  await page.getByRole('button', { name: '订阅专题' }).first().click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).toContainText('已订阅专题');
  await expect(page.locator('body')).not.toContainText('missing required input field');
  // V1 诚实回显：订阅后按钮变「已订阅」态
  await expect(page.getByRole('button', { name: '已订阅' }).first()).toBeVisible();
});

test('P7 专题详情真接 topic.package.query 渲染标杆', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/zones-pack/zone/tp-yiliao-jiuzhu');
  await expect(page.getByRole('heading', { name: '医疗救助信息专题包' })).toBeVisible();
  await expect(page.locator('body')).toContainText('包含目录');
  // 目录项诚实展示（纯文本，无链接）：目录尚未录入主表，无可达详情/检索入口
  await expect(page.locator('body')).toContainText('医疗救助信息');
  await expect(page.locator('body')).toContainText('目录详情与检索入口待 J1 目录主表录入后开放');
});
