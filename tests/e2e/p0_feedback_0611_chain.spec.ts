// 0611 P0 修复批次真 UI 钉死（核查报告 §二 业务主链三断点 + R4 审核死循环）：
//   链路 1（R1+R2+R3）：UI 在线编目 → 部门审 → 平台审 → 发布队列可见+发布（R2）→
//     挂接有条件(共享类型=2)库表资源 → 挂接审核 → 待发布资源队列发布（R3）→
//     申请（resourceId=资源码）→ 业务运营员受理 → **部门管理员二级审核可见可操作**（R1，D55④）。
//   链路 2（R4）：反向编目审核收件箱只列可办草稿（source=reverse ∧ lifecycle=draft），
//     行内「通过审核」真能通过（修复前列 pending_review 全集、行行 409）。
// 全部写动作经真实 UI 点击；唯一 API 介入 = 读侧 glue（按标题查内部目录码）与
// 链路 2 的反向草稿预铸（precondition，与 wave15 预铸单同模式）。
import { expect, test, type Page } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const TS = Date.now();
const ORG = '11370000MB284651XL';
const CAT_TITLE = `链路验证目录${TS}`;
const RES_CODE = `res-e2e-0611-${TS}`;
const RES_TITLE = `链路验证库表资源${TS}`;

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

  // 4) R2 钉死：新审结目录必须出现在发布队列（修复前 limit:5 + 目录码升序截断 → 永不可见）。
  await gotoHash(page, '#/provider');
  const catQueue = page.locator('section[aria-label="待发布目录"]');
  const catRow = catQueue.locator('li.publish-row', { hasText: CAT_TITLE });
  await expect(catRow).toHaveCount(1, { timeout: 15_000 });
  await catRow.getByTestId('publish-catalog-btn').click();
  await expect(catQueue.locator('li.publish-row', { hasText: CAT_TITLE })).toHaveCount(0, { timeout: 15_000 });

  // 5) 部门操作员：挂接有条件（共享类型=2 默认）库表资源到新目录。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/hookup-submit');
  await page.getByPlaceholder('挂接到哪个已发布目录').fill(catalogCode);
  await page.getByPlaceholder('本资源的唯一标识').fill(RES_CODE);
  await page.getByPlaceholder('例如：养老资源信息').fill(RES_TITLE);
  await page.getByPlaceholder('须与目标目录归属一致（否则挂接被拒）').fill(ORG);
  await page.getByPlaceholder('源字段').first().fill('name');
  await page.getByPlaceholder('目标字段').first().fill('name');
  await page.getByRole('button', { name: '提交复核' }).click();
  await expect(page.locator('.toast-stack')).toContainText('已提交复核', { timeout: 15_000 });

  // 6) 部门管理员：挂接审核通过。
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/hookup-review');
  const hookupRow = page.locator('tr', { hasText: RES_TITLE });
  await expect(hookupRow).toHaveCount(1, { timeout: 15_000 });
  await hookupRow.getByRole('button', { name: '通过挂接' }).click();
  await expect(hookupRow).toHaveCount(0, { timeout: 15_000 });

  // 7) R3 钉死：业务运营员在 P5「待发布资源」队列看到该资源并可发布
  //    （修复前 resource.asset.publish 全前端零调用面，资源死在「待发布」）。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider');
  const resQueue = page.getByTestId('resource-publish-queue');
  const resRow = resQueue.locator('li.publish-row', { hasText: RES_TITLE });
  await expect(resRow).toHaveCount(1, { timeout: 15_000 });
  await resRow.getByTestId('publish-resource-btn').click();
  await expect(resQueue.locator('li.publish-row', { hasText: RES_TITLE })).toHaveCount(0, { timeout: 20_000 });

  // 8) 部门操作员：从资源详情发起申请（R1：申请单绑定资源码）→ 草稿确认提交。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, `#/discovery/resource/${encodeURIComponent(RES_CODE)}`);
  const applyBtn = page.locator('button[data-skill="request.create"]');
  await expect(applyBtn).toBeVisible({ timeout: 15_000 });
  await applyBtn.click();
  await page.waitForURL(/#\/request-flow\/request\//, { timeout: 15_000 });
  const reqId = decodeURIComponent(page.url().split('/request-flow/request/')[1] ?? '').split('?')[0];
  expect(reqId, '申请草稿应跳详情页并携带单号').toBeTruthy();
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

test('链路2：反向编目审核收件箱列可办草稿且通过审核不再 409（R4）', async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);

  // 预铸一条反向编目草稿（precondition，与 wave15 预铸单同模式；request fixture 无 cookie 免
  // CSRF）。**先铸后登录**：收件箱读 snapshot 投影，登录时取一次——铸单须发生在快照拉取之前。
  const draftCode = `rev-e2e-0611-${TS}`;
  const draftTitle = `反向编目验证草稿${TS}`;
  const minted = await request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.reverse_draft.create`, {
    data: {
      role: 'ROLE_ORGAN_MANAGER',
      catalog_code: draftCode,
      title: draftTitle,
      owner_org_id: ORG,
      schema_ref: `schema:${draftCode}`,
      confirmed: true,
    },
  });
  expect(minted.ok(), `reverse_draft.create HTTP ${minted.status()}`).toBeTruthy();

  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  // 业务运营员：收件箱应列出该草稿（修复前收件箱列 pending_review 全集，待审草稿永不出现）。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/inbox/field-decision');
  const row = page.locator('tr', { hasText: draftTitle });
  await expect(row).toHaveCount(1, { timeout: 15_000 });
  await row.getByRole('link', { name: '处理' }).click();

  // 详情页「通过审核」必须真通过（修复前行行 409 invalid_state 死循环）。
  const approveBtn = page.getByRole('button', { name: '通过审核' });
  await expect(approveBtn).toBeVisible({ timeout: 15_000 });
  await approveBtn.click();
  await expect(page.locator('.toast-stack')).toContainText('已通过', { timeout: 15_000 });
});
