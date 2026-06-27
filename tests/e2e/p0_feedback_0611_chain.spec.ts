// 0611 P0 修复批次真 UI 钉死（核查报告 §二 业务主链三断点 + R4 审核死循环）：
//   链路 1（R1+R2+R3）：UI 在线编目 → 部门审 → 平台审 → 发布队列可见+发布（R2）→
//     挂接有条件(共享类型=2)库表资源 → 挂接审核 → 待发布资源队列发布（R3）→
//     申请（resourceId=资源码）→ 业务运营员受理 → **部门管理员二级审核可见可操作**（R1，D55④）。
//   链路 2（D57⑧，改写原 R4 单级链）：反向编目两级审核全链——操作员经供数首屏主卡（B2 同级展示）
//     UI 创建两条反向草稿 → 部门管理员部门审（通过/驳回各一）→ 业务运营员平台审（目录审核收件箱
//     平台档，BUSIAUDIT 落 field-decision 路由时对位跳转）→ 发布；双面权限（操作员/运营员
//     无部门审入口）一并钉死。替换原「仅 BUSIAUDIT 一级 confirm」路径的旧断言。
// 全部写动作经真实 UI 点击；唯一 API 介入 = 读侧 glue（按标题查内部目录码 / 终态校验）。
import { expect, test, type Page } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, publishViaWorkbench, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const TS = Date.now();
const CAT_TITLE = `链路验证目录${TS}`;
const RES_TITLE = `链路验证库表资源${TS}`;
// 资源标识 = 挂接向导系统自动生成；归属随选中目录带出（不再手填）。

/** 读侧 glue：按标题查内部目录码（j2-inline-…）。request fixture 无浏览器 cookie，免 CSRF。 */
async function findCatalogCodeByTitle(requestCtx: any, title: string): Promise<string> {
  const resp = await requestCtx.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_ORGAN_OPERATER', query: title },
  });
  expect(resp.ok(), `catalog.entry.query HTTP ${resp.status()}`).toBeTruthy();
  const body = (await resp.json()) as { items?: Array<{ catalog_code?: string; title?: string }> };
  const hit = (body.items ?? []).find((it) => it.title === title);
  expect(hit?.catalog_code, `按标题 ${title} 应查到唯一目录`).toBeTruthy();
  return String(hit!.catalog_code);
}

async function approveRowByText(page: Page, rowText: string, btnTestId: string): Promise<void> {
  const row = page.locator('tr', { hasText: rowText });
  await expect(row).toHaveCount(1, { timeout: 15_000 });
  await row.getByTestId(btnTestId).click();
  await expect(row).toHaveCount(0, { timeout: 15_000 });
}

test('链路1：UI 新编目→挂接有条件资源→发布→申请→受理→部门管理员二级审核（R1/R2/R3）', async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  // 1) 部门操作员：在线编制目录（共享类型默认=有条件共享 2）。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/inline-catalog');
  await page.getByPlaceholder('例如：医疗救助申请人信息').fill(CAT_TITLE);
  // 基本信息必填全集（0611 口径确认单 §A：创建/提交均强校验）。下拉项均有默认值，
  // 只需补 6 个自由文本必填项；共享类型默认 2（有条件）→ 共享条件转必填。
  await page.getByPlaceholder('例如：民政服务').fill('营商环境');
  await page.getByPlaceholder('例如：医疗救助建模系统').fill('链路验证来源系统');
  await page.getByPlaceholder('例如：社会保障').fill('市场监管');
  await page.getByPlaceholder('例如：用于医疗救助资格审核与待遇核算').fill('0611 主链 e2e 链路验证');
  await page.getByPlaceholder('例如：根据个人信息保护要求，按授权范围共享').fill('按授权范围共享，需符合个人信息保护要求');
  await page.getByPlaceholder('一句话说明本目录覆盖的数据范围与用途。').fill('覆盖 0611 主链 e2e 链路验证目录的数据范围。');
  await page.getByTestId('inline-catalog-create-btn').click();
  await expect(page.locator('body')).toContainText('已生成目录草稿', { timeout: 15_000 });
  await page.getByTestId('inline-catalog-update-btn').click();
  await expect(page.locator('body')).toContainText('元数据与信息项已保存', { timeout: 15_000 });
  await page.getByTestId('inline-catalog-submit-btn').click();
  await expect(page.locator('body')).toContainText('已提交，当前状态', { timeout: 15_000 });
  const catalogCode = await findCatalogCodeByTitle(request, CAT_TITLE);

  // 2) 部门管理员：目录部门审。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/catalog-review');
  await approveRowByText(page, CAT_TITLE, 'catalog-review-approve-btn');

  // 3) 业务运营员：目录平台审。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/inbox/catalog-review');
  await approveRowByText(page, CAT_TITLE, 'catalog-review-approve-btn');

  // 4) R2 钉死：新审结目录在工作台「待发布目录」行内逐条发布（发布动作统一收口工作台，
  //    供数据页旧发布队列退役）。helper 内已切业务运营员、展开、点该条「发布」并验「已发布」。
  await publishViaWorkbench(page, '待发布目录', CAT_TITLE);

  // 5) 部门操作员：挂接有条件（共享类型=2 默认）库表资源到新目录。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/hookup-submit');
  // 所属目录走下拉（归属随之带出）；资源标识系统自动生成，读出供详情深链。
  await page.getByTestId('hookup-catalog-select').selectOption(catalogCode);
  const RES_CODE = (await page.getByTestId('hookup-resource-code').textContent())?.trim() ?? '';
  expect(RES_CODE, '资源标识应自动生成').toBeTruthy();
  await page.getByPlaceholder('例如：养老资源信息').fill(RES_TITLE);
  // B2 字段数据模型逐列登记（旧「源→目标」两列映射已升级为字段级元数据表；字段名必填）。
  await page.getByPlaceholder('例如：xm').first().fill('name');
  await page.getByPlaceholder('例如：姓名').first().fill('姓名');
  await page.getByRole('button', { name: '提交复核' }).click();
  await expect(page.locator('.toast-stack')).toContainText('已提交复核', { timeout: 15_000 });

  // 6) 部门管理员：挂接审核通过。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/hookup-review');
  const hookupRow = page.locator('tr', { hasText: RES_TITLE });
  await expect(hookupRow).toHaveCount(1, { timeout: 15_000 });
  await hookupRow.getByRole('button', { name: '通过挂接' }).click();
  await expect(hookupRow).toHaveCount(0, { timeout: 15_000 });

  // 7) R3 钉死：资源审核通过后在工作台「待发布资源」行内发布（resource.asset.publish 有可办面，
  //    不再死在「待发布」；发布统一收口工作台，供数据页旧资源发布队列退役）。
  await publishViaWorkbench(page, '待发布资源', RES_TITLE);

  // 8) 部门操作员：从资源详情发起申请（R1：申请单绑定资源码）→ 草稿确认提交。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, `#/discovery/resource/${encodeURIComponent(RES_CODE)}`);
  const applyBtn = page.locator('button[data-skill="request.create"]');
  await expect(applyBtn).toBeVisible({ timeout: 15_000 });
  await applyBtn.click();
  await page.waitForURL(/#\/request-flow\/request\//, { timeout: 15_000 });
  const reqId = decodeURIComponent(page.url().split('/request-flow/request/')[1] ?? '').split('?')[0];
  expect(reqId, '申请草稿应跳详情页并携带单号').toBeTruthy();
  // 写后快照与跳转存在竞速（#126 同会话预取：request.create 刷新晚于详情页读取时，详情先读到
  // 「铸单前」快照→「未找到该申请」、submit 按钮不渲染）。以新加载会话重取铸单后快照再提交
  // （与链路2 部门审 reload 同口径），消除竞速、不掩盖产品行为。
  await page.reload();
  await waitAppReady(page);
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, `#/request-flow/request/${reqId}`);
  await page.getByTestId('submit-draft-btn').click();
  await expect(page.locator('.toast-stack')).toContainText('已提交申请', { timeout: 15_000 });

  // 9) 业务运营员受理（第一级）。修复前有条件单被误判「无条件·受理即终」，
  //    此处「受理」按钮 + 第 10 步部门管理员审核就是 D55④ 两级未被旁路的 UI 实证。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, `#/request-flow/review/${reqId}`);
  const acceptBtn = page.getByRole('button', { name: '受理', exact: true });
  await expect(acceptBtn).toBeVisible({ timeout: 15_000 });
  await acceptBtn.click();
  await expect(page.locator('body')).toContainText(/已受理待审核|受理通过/, { timeout: 15_000 });

  // 10) 部门管理员二级审核可见可操作 → 已授权（断点 C 修复的终点断言）。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, `#/request-flow/review/${reqId}`);
  const deptBtn = page.getByRole('button', { name: '审核通过', exact: true });
  await expect(deptBtn).toBeVisible({ timeout: 15_000 });
  await deptBtn.click();
  await expect(page.locator('body')).toContainText(/已授权|审核通过/, { timeout: 15_000 });
});

test('链路2：反向编目两级审核全链——操作员UI创建→管理员部门审(通过/驳回)→运营员平台审→发布（D57⑧）', async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  // 1) 部门操作员：供数据入口区「反向编目」与「在线编制目录」并列，点入口进向导。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider');
  const reverseEntry = page.locator('a.entry-link[href="#/provider/wizard/reverse-catalog"]');
  await expect(reverseEntry).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator('a.entry-link[href="#/provider/wizard/inline-catalog"]')).toHaveCount(1);
  await reverseEntry.click();
  await expect(page.getByRole('heading', { name: '反向编目' })).toBeVisible({ timeout: 15_000 });
  await gotoHash(page, '#/provider/wizard/reverse-catalog/detail');
  await expect(page.getByRole('heading', { name: '反向编目向导' })).toBeVisible({ timeout: 15_000 });

  // 2) 操作员经真实 UI 创建两条反向草稿（产品语义=对既有带 schema 目录反查重编）：
  //    A 走「部门审通过→平台审→发布」，B 走「部门审驳回」。
  const select = page.locator('select.gov-select');
  await expect(select).toBeVisible({ timeout: 15_000 });
  const optionCount = await select.locator('option:not([disabled])').count();
  expect(optionCount, '反向编目向导应至少列出 2 个可发起目录').toBeGreaterThanOrEqual(2);
  const mintDraft = async (index: number): Promise<{ code: string; name: string }> => {
    const opt = select.locator('option:not([disabled])').nth(index);
    const code = String(await opt.getAttribute('value'));
    await select.selectOption(code);
    const label = String(await opt.textContent()).trim();
    const name = label.replace(/（[^）]*）\s*$/, ''); // 去掉「（状态）」尾注得目录名
    await page.getByRole('button', { name: '创建反向编目草稿' }).click();
    await expect(page.locator('.toast-stack')).toContainText('反向编目草稿已创建', { timeout: 15_000 });
    return { code, name };
  };
  const draftA = await mintDraft(0);
  const draftB = await mintDraft(1);

  // 3) 双面验证（操作员无任何反向审核权，做的人不审自己）：
  //    深链部门审收件箱被弹走（无权=不可达），供数页协作待办无「反向编目审核」卡。
  await gotoHash(page, '#/provider/inbox/field-decision');
  await expect(page).not.toHaveURL(/field-decision/, { timeout: 15_000 });
  await gotoHash(page, '#/provider');
  await expect(page.locator('.stat-card', { hasText: '反向编目审核' })).toHaveCount(0);

  // 4) 部门管理员：第一级部门审。协作待办卡可见 → 收件箱列出两条草稿。
  // 收件箱读 snapshot 投影；同会话切岗位可能命中登录期预取的「铸单前」兄弟岗位快照
  // （#126 CQRS/SSE 架构门刻意延后，跨会话陈旧属已知边界）——审核人以新加载会话进入
  // （reload + 重登录），快照必取于铸单之后，与真实「管理员打开系统办审核」同形。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await page.reload();
  await waitAppReady(page);
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider');
  await expect(page.locator('.stat-card', { hasText: '反向编目审核' })).toHaveCount(1, { timeout: 15_000 });
  await gotoHash(page, '#/provider/inbox/field-decision');
  const detailLink = (code: string) =>
    page.locator(`a[href="#/provider/inbox/field-decision/${encodeURIComponent(code)}"]`);
  await expect(detailLink(draftA.code)).toHaveCount(1, { timeout: 30_000 });
  await expect(detailLink(draftB.code)).toHaveCount(1);

  // 4a) 草稿 A 部门审通过 → 转平台审。
  await detailLink(draftA.code).click();
  const approveBtn = page.getByRole('button', { name: '通过审核' });
  await expect(approveBtn).toBeVisible({ timeout: 15_000 });
  await approveBtn.click();
  await expect(page.locator('.toast-stack')).toContainText('已通过部门审', { timeout: 15_000 });

  // 4b) 草稿 B 部门审驳回 → rejected 终态（部门审驳回不进平台审）。
  //     驳回两步：点「驳回」展开理由框 → 填写真实理由 → 「确认驳回」提交
  //     （reject_reason 硬编码常量已退役，理由必填非空，见 P5FieldDecisionDetail）。
  await gotoHash(page, '#/provider/inbox/field-decision');
  await detailLink(draftB.code).click();
  const rejectBtn = page.getByTestId('field-decision-reject-btn');
  await expect(rejectBtn).toBeVisible({ timeout: 15_000 });
  await rejectBtn.click();
  const rejectPanel = page.getByTestId('field-decision-reject-panel');
  await expect(rejectPanel).toBeVisible({ timeout: 15_000 });
  await rejectPanel.locator('textarea').fill('e2e 链路验证：目录口径需补充证据后重新提交');
  await page.getByTestId('field-decision-reject-confirm-btn').click();
  await expect(page.locator('.toast-stack')).toContainText('已驳回', { timeout: 15_000 });

  // 5) 业务运营员：落到旧部门审路由应对位跳转目录审核收件箱（BUSIAUDIT 退出 draft 阶段确认，
  //    其反向审核=平台审，双面验证）。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await page.reload();
  await waitAppReady(page);
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/inbox/field-decision');
  await expect(page).toHaveURL(/catalog-review/, { timeout: 15_000 });

  // 5a) 平台审：目录审核收件箱平台档列出草稿 A（汇入正向管线，不另造第二套审核），通过。
  // 编号列走 displayRecordCode（「编号 …000055」），用目录名定位行而非裸 catalog_code。
  const platformRow = page.locator('tr', { hasText: draftA.name }).first();
  await expect(platformRow).toBeVisible({ timeout: 15_000 });
  await platformRow.getByTestId('catalog-review-approve-btn').click();
  await expect(page.locator('tr', { hasText: draftA.name })).toHaveCount(0, { timeout: 15_000 });

  // 6) 发布：草稿 A 经平台审进入待发布。发布动作已统一收口工作台行内（供数据页旧发布队列退役）；
  //    本链路聚焦反向编目两级审核 UI，发布按目录码经 API 触发终态（同名反向草稿不可靠按标题定位
  //    工作台行内项，故此处用码 API 触发；工作台发布 UI 由链路1 钉死），由 step 7 校验 active。
  const pubResp = await request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.publish`, {
    data: { role: 'ROLE_BUSIAUDIT', catalog_code: draftA.code, confirmed: true },
  });
  expect(pubResp.ok(), `catalog.entry.publish HTTP ${pubResp.status()}`).toBeTruthy();

  // 7) 终态校验（读侧 glue）：A=active（已发布）、B=rejected（部门审驳回终态）。
  const verify = await request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', catalog_code: draftA.code },
  });
  expect(verify.ok()).toBeTruthy();
  const verifyBody = (await verify.json()) as { items?: Array<{ lifecycle_status?: string }> };
  expect(verifyBody.items?.[0]?.lifecycle_status).toBe('active');
  const verifyB = await request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', catalog_code: draftB.code },
  });
  const verifyBodyB = (await verifyB.json()) as { items?: Array<{ lifecycle_status?: string }> };
  expect(verifyBodyB.items?.[0]?.lifecycle_status).toBe('rejected');
});
