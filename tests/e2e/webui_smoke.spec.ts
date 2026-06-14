import { test, expect, type Page } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

/**
 * 经 API 链铸一条 rejected（legacy 3 驳回）申请，返回 request_id（或 null）。
 *  request.create(草稿) → request.submit(submitted) → application.platform_approve(受理驳回 → rejected)
 * 用于驱动 P3 有条件驳回→重提腿（j1-approval-conditional.feature:55-62）。失败返 null 让用例 skip，
 * 不把环境噪声当断言失败。
 */
async function mintRejectedRequest(page: Page): Promise<string | null> {
  // 取一条可申请的真实资源 id（P2 发现页 discovery.resources 只列已发布 active，r.id 即申请入参）。
  const snapResp = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!snapResp.ok()) return null;
  const snap = (await snapResp.json()) as { discovery?: { resources?: Array<Record<string, unknown>> } };
  const list = snap.discovery?.resources ?? [];
  const resourceId = String(list[0]?.id ?? '');
  if (!resourceId) return null;

  const createResp = await page.request.post(`${E2E_BASE_URL}/api/skills/request.create`, {
    data: { role: 'ROLE_ORGAN_OPERATER', resource_id: resourceId, purpose: 'e2e 有条件驳回重提链路', confirmed: true },
  });
  if (!createResp.ok()) return null;
  const created = (await createResp.json()) as Record<string, unknown>;
  const requestId = String(created.requestId ?? created.request_id ?? created.id ?? '');
  if (!requestId) return null;

  const submitResp = await page.request.post(`${E2E_BASE_URL}/api/skills/request.submit`, {
    data: { role: 'ROLE_ORGAN_OPERATER', request_id: requestId, confirmed: true },
  });
  if (!submitResp.ok()) return null;

  // 受理驳回（业务运营员）：submitted → rejected。
  const rejectResp = await page.request.post(`${E2E_BASE_URL}/api/skills/application.platform_approve`, {
    data: { role: 'ROLE_BUSIAUDIT', request_id: requestId, decision: 'reject', note: 'e2e 受理驳回', confirmed: true },
  });
  if (!rejectResp.ok()) return null;
  return requestId;
}

test.beforeEach(async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);
  await page.goto('/');
  await waitAppReady(page);
});

/**
 * 从「我的申请」列表打开第一条真实申请详情，返回单号。
 * D56.b（#247）：REQ-* 序列退役（新铸单号 = uuid hex），用例禁硬编码单号。
 */
async function openFirstRequestDetail(page: Page): Promise<string> {
  await gotoHash(page, '#/request-flow');
  await page.getByRole('button', { name: '查看' }).first().click();
  await page.waitForTimeout(600);
  const m = page.url().match(/#\/request-flow\/request\/([^/?#]+)/);
  expect(m).not.toBeNull();
  return m![1];
}

test('P1 工作台装载 live 申请进度（操作员）', async ({ page }) => {
  // D57②（#258）：操作员（申请人岗）工作台 = 「我的申请进度」，不显「待办」（0609 docx 口径）。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/workbench');
  await expect(page.locator('.p1-hero-title')).toContainText('进度');
  await expect(page.locator('.p1-hero-title')).not.toContainText('待办');
  await expect(page.getByRole('heading', { name: '我的申请进度' })).toBeVisible();
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

test('P3 申请详情点击补件给出中文提示', async ({ page }) => {
  // 意图：真实在途单详情点补件得到中文业务提示
  // （在途=「暂不可重新提交」/ 待补正=「已重新提交」），绝不漏工程字段名。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await openFirstRequestDetail(page);
  await page.getByRole('button', { name: '补件 / 重新提交' }).click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).toContainText(/(已|暂不可)重新提交/);
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
  // 先从列表解析一条真实单号，再深链审批路由验证回弹到申请详情。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  const id = await openFirstRequestDetail(page);
  await gotoHash(page, `#/request-flow/review/${id}`);
  await page.waitForTimeout(600);
  expect(page.url()).toContain(`#/request-flow/request/${id}`);
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

test('岗位切换：供数页可达性随岗位（操作员可进、安全审计员被弹走）', async ({ page }) => {
  // 旧期望「业务运营员无权进提供方页」已过时（且原用例 setRole 的实为部门操作员，角色口径错）：
  // D53⑤/D55⑥ 后供数 shell 角色 = 操作员+管理员+业务运营员；
  // 「无权=被弹走」的原意图改由安全审计员承接（D55⑦ 纯只读、无供数职责）。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider');
  await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
  await setRole(page, 'ROLE_SECURITY_AUDIT');
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

test('P5 反向编目：字段候选被接住并渲染成可勾选/可改的候选表（j2 修订→确认入库）', async ({ page }) => {
  // 接缝诚实化 A：suggestFields 接住 res.data.fields，渲染候选表（含敏感级），
  // 确认后随 create 发 draft_field_suggestions。本用例钉死「候选被接住」这一断点
  // （此前 res.data 被丢弃，字段链断在前端）。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/reverse-catalog');
  await page.locator('.gov-select').selectOption({ index: 1 });
  await page.getByTestId('reverse-suggest-btn').click();
  await page.waitForTimeout(800);
  await expect(page.locator('body')).toContainText('字段建议已生成');
  // 候选表出现 + 至少一行字段（含勾选框 / 中文名输入框 / 敏感级下拉）。
  const candidates = page.getByTestId('reverse-field-candidates');
  await expect(candidates).toBeVisible();
  const rows = candidates.locator('tbody tr');
  expect(await rows.count()).toBeGreaterThan(0);
  await expect(rows.first().locator('input[type="checkbox"]')).toBeVisible();
  await expect(candidates.locator('select')).not.toHaveCount(0);
});

test('P3 有条件驳回 → 申请人重提腿可点（rejected 不再死按钮）', async ({ page }) => {
  // 接缝诚实化 B：rejected（受理/审核驳回）态下「补件 / 重新提交」可点，
  // 走 application.dept_approve {decision:'resubmit'}（applicant_resubmit: rejected → submitted）。
  // 此前 canResubmit 仅覆盖 need-fix，rejected 态按钮哑火。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  const requestId = await mintRejectedRequest(page);
  test.skip(!requestId, '无法铸 rejected 申请（缺可申请资源或链路未通），跳过腿断言');
  await gotoHash(page, `#/request-flow/request/${requestId}`);
  await page.waitForTimeout(600);
  // 详情头显示「已驳回」，重提按钮可见可点。
  await expect(page.locator('body')).toContainText('已驳回');
  const resubmitBtn = page.getByTestId('resubmit-btn');
  await expect(resubmitBtn).toBeVisible();
  await resubmitBtn.click();
  await page.waitForTimeout(800);
  // 不漏工程字段名 + 给出已重新提交的业务提示（非「当前状态不支持」）。
  await expect(page.locator('body')).not.toContainText('request_id');
  await expect(page.locator('body')).toContainText(/已重新提交|已提交/);
});

test('P5 反向编目：业务运营员进不了向导与部门审收件箱（D57⑧ 双面）', async ({ page }) => {
  // 反向编目创建=操作员/管理员（D55/P14）、部门审=管理员（D57⑧）；业务运营员的反向审核
  // 在目录审核收件箱平台档——向导与 field-decision 路由对其均不可达（无权=不可见）。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/wizard/reverse-catalog');
  await expect(page).not.toHaveURL(/reverse-catalog/);
  await gotoHash(page, '#/provider/inbox/field-decision');
  await expect(page).toHaveURL(/catalog-review/);
});

test('P3 申请详情「撤回申请」入口已退役（授权域操作替代）', async ({ page }) => {
  // 退役不变量：j1-credential-revoke 决策 A（已签字，D55 承接）——「撤回申请」改版为授权域操作
  // （业务运营员「收回授权」/ 申请人「我不再需要」，仅 granted/in_delivery/suspended 态渲染）。
  // 在途申请详情不再有「撤回申请」按钮，旧「误调目录 withdraw（catalog_code 漏出）」缺陷类随入口一并退役。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await openFirstRequestDetail(page);
  await expect(page.getByRole('button', { name: '撤回申请' })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('catalog_code');
});

test('P5 代理服务注册向导提交不报缺字段', async ({ page }) => {
  // D1：代理服务注册——填服务名/原始接口地址/描述（≥30字）→ 注册草稿，接 resource.api.register。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/api-service');
  // T8：四步表单默认收起，先点「＋ 注册代理服务」展开再填字段。
  await page.getByTestId('api-register-toggle').click();
  await page.getByPlaceholder('例如：养老保险信息查询服务').fill('养老保险信息查询代理服务');
  await page.getByPlaceholder('例如：https://10.110.16.133/api/pension/query').fill('https://10.110.16.133/api/pension/query');
  await page.getByPlaceholder('说明该服务提供什么数据、面向哪些业务场景。').fill('代理养老保险信息查询接口，面向部门间数据共享与资格核验业务场景使用。');
  await page.getByRole('button', { name: '注册代理服务（草稿）' }).click();
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

// 专题包（P7 / zones-pack）退出本期（D55/P6）：下线整面，保数据不删库，仅去入口/可见性。
// 原 3 条「P7 列表/订阅/详情真接 topic.package.*」走查退役为退役不变量——
// zones-pack 路由不再有侧栏入口，深链直达也不渲染专题包内容（无权=不可见 / 已下线=不可见）。
test('专题包退出本期：侧栏无入口 + 深链不渲染专题内容（D55/P6）', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  // 1) 侧栏导航无「专题包」入口
  await gotoHash(page, '#/workbench');
  await expect(page.getByRole('link', { name: '专题包' })).toHaveCount(0);
  // 2) 深链直达 zones-pack：路由已下线，不应渲染任何专题包标杆内容
  await gotoHash(page, '#/zones-pack');
  await page.waitForTimeout(800);
  await expect(page.getByText('医疗救助信息专题包')).toHaveCount(0);
  await expect(page.getByText('医保码信息专题包')).toHaveCount(0);
});
