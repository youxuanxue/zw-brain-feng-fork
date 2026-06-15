// B2 字段级元数据 10 列真 UI 全链钉死（债 b2-field-metadata-10col 提前本期，立项草案 §四验收口径）：
//   链路 1（库表）：UI 在线编目→目录两级审→发布 → 挂接向导逐列填 **10 列全部** 字段元数据 →
//     提交复核 → 部门管理员挂接审核 → 业务运营员资源发布 → 资源详情「字段数据模型」
//     **逐列回显与注册输入一致**（10 列全比，不抽样；含「更多」展开区低频列）。
//   链路 1 尾段（文件）：同目录挂接文件资源 + 可选字段登记 → 同链发布 → 详情同样逐列回显
//     （B2 后文件资源字段数据模型块解禁：有快照真展示）。
//   链路 2（存量不回归）：legacy 导入快照资源的字段数据模型基线 5 列照常渲染。
// 全部写动作经真实 UI 点击；唯一 API 介入 = 读侧 glue（按标题查目录码 / 探测 legacy schema 资源）。
import { expect, test, type Page } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const TS = Date.now();
const CAT_TITLE = `字段元数据验证目录${TS}`;
const RES_TITLE = `字段元数据验证库表${TS}`;
const FILE_TITLE = `字段元数据验证文件${TS}`;
// 资源标识 = 挂接向导系统自动生成（不再手敲）；从只读字段读出供详情页深链用。
// 归属机构 = 选中目录自动带出（不再手填，否则跨 org 校验拒）。

/** 读侧 glue：按标题查内部目录码（与 p0_feedback_0611_chain 同模式，免 CSRF）。 */
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

/** 写后快照 settle：invokeActionStub 的写后刷新是 fire-and-forget，与紧随其后的切岗位
 * 快照拉取存在 last-write-wins 竞速（陈旧岗位快照后到会覆盖展示数据）。提交后等网络
 * 静默再切岗位，保证切岗位后的拉取最后落地（测试确定性，不掩盖产品行为）。 */
async function settleAfterWrite(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined);
}

/** 行未出现时兜底：整页 reload（以当前岗位重新拉快照）后重新导航再等一次。 */
async function expectRowWithReloadFallback(
  page: Page,
  hash: string,
  rowLocator: () => ReturnType<Page['locator']>,
): Promise<void> {
  try {
    await expect(rowLocator()).toHaveCount(1, { timeout: 10_000 });
  } catch {
    await page.reload();
    await waitAppReady(page);
    await gotoHash(page, hash);
    await expect(rowLocator()).toHaveCount(1, { timeout: 15_000 });
  }
  // 点击前让快照刷新与 toast 退场：行重渲染（detach）与「已切换岗位」toast 拦截指针
  // 都会让 click 重试空转。
  await settleAfterWrite(page);
  await page.locator('.toast-stack strong').first().waitFor({ state: 'detached', timeout: 10_000 }).catch(() => undefined);
}

/** UI 编目→两级审→发布（precondition 段，与 p0 chain 完全同步骤）。返回 catalog_code。 */
async function publishFreshCatalog(page: Page, request: any): Promise<string> {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/inline-catalog');
  await page.getByPlaceholder('例如：医疗救助申请人信息').fill(CAT_TITLE);
  await page.getByPlaceholder('例如：民政服务').fill('营商环境');
  await page.getByPlaceholder('例如：医疗救助建模系统').fill('字段元数据验证来源系统');
  await page.getByPlaceholder('例如：社会保障').fill('市场监管');
  await page.getByPlaceholder('例如：用于医疗救助资格审核与待遇核算').fill('B2 字段元数据 e2e 验证');
  await page.getByPlaceholder('例如：根据个人信息保护要求，按授权范围共享').fill('按授权范围共享');
  await page.getByPlaceholder('一句话说明本目录覆盖的数据范围与用途。').fill('B2 字段级元数据 10 列 e2e 验证目录。');
  await page.getByTestId('inline-catalog-create-btn').click();
  await expect(page.locator('body')).toContainText('已生成目录草稿', { timeout: 15_000 });
  await page.getByTestId('inline-catalog-update-btn').click();
  await expect(page.locator('body')).toContainText('元数据与信息项已保存', { timeout: 15_000 });
  await page.getByTestId('inline-catalog-submit-btn').click();
  await expect(page.locator('body')).toContainText('已提交，当前状态', { timeout: 15_000 });
  const catalogCode = await findCatalogCodeByTitle(request, CAT_TITLE);

  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/catalog-review');
  await approveRowByText(page, CAT_TITLE, 'catalog-review-approve-btn');
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/inbox/catalog-review');
  await approveRowByText(page, CAT_TITLE, 'catalog-review-approve-btn');
  await gotoHash(page, '#/provider');
  const catQueue = page.locator('section[aria-label="待发布目录"]');
  const catRow = catQueue.locator('li.publish-row', { hasText: CAT_TITLE });
  await expect(catRow).toHaveCount(1, { timeout: 15_000 });
  await catRow.getByTestId('publish-catalog-btn').click();
  await expect(catQueue.locator('li.publish-row', { hasText: CAT_TITLE })).toHaveCount(0, { timeout: 15_000 });
  return catalogCode;
}

/** 挂接审核（管理员）→ 资源发布（业务运营员），按标题行操作。 */
async function reviewAndPublishResource(page: Page, resTitle: string): Promise<void> {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/hookup-review');
  const hookupRow = page.locator('tr', { hasText: resTitle });
  await expectRowWithReloadFallback(page, '#/provider/inbox/hookup-review', () => hookupRow);
  await hookupRow.getByRole('button', { name: '通过挂接' }).click();
  await expect(hookupRow).toHaveCount(0, { timeout: 15_000 });
  await settleAfterWrite(page);

  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider');
  const resQueue = page.getByTestId('resource-publish-queue');
  const resRow = resQueue.locator('li.publish-row', { hasText: resTitle });
  await expectRowWithReloadFallback(page, '#/provider', () => resRow);
  await resRow.getByTestId('publish-resource-btn').click();
  await expect(resQueue.locator('li.publish-row', { hasText: resTitle })).toHaveCount(0, { timeout: 20_000 });
  await settleAfterWrite(page);
}

/** 打开资源详情并展开「字段数据模型」，返回表格 locator。 */
async function openSchemaTable(page: Page, resourceCode: string) {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, `#/discovery/resource/${encodeURIComponent(resourceCode)}`);
  await expect(page.locator('[data-testid="resource-schema-block"]')).toBeVisible({ timeout: 15_000 });
  await page.locator('[data-testid="resource-schema-toggle"]').click();
  const table = page.locator('[data-testid="resource-schema-table"]');
  await expect(table).toBeVisible({ timeout: 15_000 });
  return table;
}

test('B2 链路：注册逐列填 10 列 → 审核发布 → 详情逐列回显一致（库表 + 文件）', async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  const catalogCode = await publishFreshCatalog(page, request);

  // ── 库表：挂接向导逐列填 10 列（两行字段，行 1 含全部低频列） ────────────────
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/hookup-submit');
  // 所属目录走下拉（选已发布目录，归属随之带出）；资源标识系统自动生成，读出供后续详情深链。
  await page.getByTestId('hookup-catalog-select').selectOption(catalogCode);
  const RES_CODE = (await page.getByTestId('hookup-resource-code').textContent())?.trim() ?? '';
  expect(RES_CODE, '资源标识应自动生成').toBeTruthy();
  await page.getByPlaceholder('例如：养老资源信息').fill(RES_TITLE);
  await page.getByPlaceholder('t_xxx').fill('t_b2_field_demo');

  const fieldTable = page.getByTestId('hookup-field-table');
  // 行 1：xm / 姓名 / 字符串型 / 50 / 主键 / 非可空 + 更多（目录信息项 / 更新主键 / 标准 / 字典）。
  await page.getByPlaceholder('例如：xm').nth(0).fill('xm');
  await page.getByPlaceholder('例如：姓名').nth(0).fill('姓名');
  await fieldTable.locator('select').nth(0).selectOption('C');
  await fieldTable.getByPlaceholder('50').nth(0).fill('50');
  await page.getByLabel('字段 1 是否主键').check();
  await page.getByLabel('字段 1 是否可空').uncheck();
  await page.getByTestId('field-more-btn-0').click();
  await page.getByPlaceholder('该字段对应的目录信息项（可不填）').fill('目录信息项-姓名');
  await page.getByPlaceholder('例如：GB/T 2261.1').fill('GB/T 2261.1');
  await page.getByPlaceholder('例如：性别代码表').fill('姓名代码表');
  await page.getByLabel('字段 1 是否更新主键').check();
  await page.getByTestId('field-more-btn-0').click(); // 收起，行 2 操作互不干扰
  // 行 2：update_time / 更新时间 / 时间型 / 可空（默认）+ 更新时间标志。
  await page.getByRole('button', { name: '+ 增加字段' }).click();
  await page.getByPlaceholder('例如：xm').nth(1).fill('update_time');
  await page.getByPlaceholder('例如：姓名').nth(1).fill('更新时间');
  await fieldTable.locator('select').nth(1).selectOption('T');
  await page.getByTestId('field-more-btn-1').click();
  await page.getByLabel('字段 2 是否更新时间').check();

  await expect(page.locator('body')).toContainText('字段登记完整性：✓', { timeout: 5_000 });
  await page.getByRole('button', { name: '提交复核' }).click();
  await expect(page.locator('.toast-stack')).toContainText('已提交复核', { timeout: 15_000 });
  await settleAfterWrite(page);

  await reviewAndPublishResource(page, RES_TITLE);

  // ── 详情「字段数据模型」逐列回显（10 列全比，不抽样） ────────────────────────
  const table = await openSchemaTable(page, RES_CODE);
  // 扩展 3 列出列（注册登记过扩展元数据）。
  await expect(table.locator('thead')).toContainText('关联目录信息项');
  await expect(table.locator('thead')).toContainText('更新标识');
  await expect(table.locator('thead')).toContainText('数据标准·数据字典');
  const row1 = table.locator('tbody tr').nth(0);
  await expect(row1.locator('td').nth(0)).toHaveText('xm'); // ① 字段名
  await expect(row1.locator('td').nth(1)).toHaveText('姓名'); // ② 释义
  await expect(row1.locator('td').nth(2)).toHaveText('字符串型'); // ④ 字段类型（与注册输入同词）
  await expect(row1.locator('td').nth(3)).toHaveText('50'); // ⑤ 长度精度
  await expect(row1.locator('td').nth(4)).toContainText('主键'); // ⑥ 是否主键
  await expect(row1.locator('td').nth(4)).toContainText('必填'); // ⑦ 是否可空（否 → 必填）
  await expect(row1.locator('td').nth(5)).toHaveText('目录信息项-姓名'); // ③ 关联目录信息项
  await expect(row1.locator('td').nth(6)).toContainText('更新主键'); // ⑧ 是否更新主键
  await expect(row1.locator('td').nth(7)).toContainText('GB/T 2261.1 · 姓名代码表'); // ⑩ 数据标准·数据字典
  const row2 = table.locator('tbody tr').nth(1);
  await expect(row2.locator('td').nth(0)).toHaveText('update_time');
  await expect(row2.locator('td').nth(1)).toHaveText('更新时间');
  await expect(row2.locator('td').nth(2)).toHaveText('时间型');
  await expect(row2.locator('td').nth(4)).not.toContainText('必填'); // 可空 → 无「必填」
  await expect(row2.locator('td').nth(5)).toHaveText('—'); // 未填 → 诚实「—」
  await expect(row2.locator('td').nth(6)).toContainText('更新时间'); // ⑨ 是否更新时间
  await expect(row2.locator('td').nth(7)).toHaveText('—');

  // ── 文件：同目录挂接文件资源 + 可选字段登记 → 同链发布 → 详情回显 ─────────────
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/provider/wizard/hookup-submit');
  await page.getByRole('button', { name: '文件' }).click();
  await page.getByTestId('hookup-catalog-select').selectOption(catalogCode);
  const FILE_CODE = (await page.getByTestId('hookup-resource-code').textContent())?.trim() ?? '';
  expect(FILE_CODE, '文件资源标识应自动生成').toBeTruthy();
  await page.getByPlaceholder('例如：养老资源信息').fill(FILE_TITLE);
  await page.getByPlaceholder('students.csv').fill('persons.csv');
  await page.getByPlaceholder('/data/xxx.csv').fill('/data/persons.csv');
  await page.getByPlaceholder('例如：xm').nth(0).fill('sfzh');
  await page.getByPlaceholder('例如：姓名').nth(0).fill('身份证号');
  await page.getByPlaceholder('50').nth(0).fill('18');
  await page.getByRole('button', { name: '提交复核' }).click();
  await expect(page.locator('.toast-stack')).toContainText('已提交复核', { timeout: 15_000 });
  await settleAfterWrite(page);

  await reviewAndPublishResource(page, FILE_TITLE);

  const fileTable = await openSchemaTable(page, FILE_CODE);
  const fileRow = fileTable.locator('tbody tr').nth(0);
  await expect(fileRow.locator('td').nth(0)).toHaveText('sfzh');
  await expect(fileRow.locator('td').nth(1)).toHaveText('身份证号');
  await expect(fileRow.locator('td').nth(3)).toHaveText('18');
});

test('B2 存量不回归：legacy 导入快照资源的字段数据模型基线列照常渲染', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await page.goto(E2E_BASE_URL);
  await skipUnlessBackend(page, testInfo);
  await waitAppReady(page);

  // 探测一个 legacy 快照可达的库表资源（与 resource_schema_view.spec 同模式）。
  const role = 'ROLE_ORGAN_MANAGER';
  const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=${role}`);
  test.skip(!snap.ok(), 'snapshot API unavailable');
  const body = (await snap.json()) as Record<string, unknown>;
  const resources = ((body.discovery as Record<string, unknown>)?.resources ?? []) as Array<Record<string, unknown>>;
  let legacyCode: string | null = null;
  for (const r of resources) {
    const code = String(r.id ?? '');
    if (!code || String(r.kind ?? '') !== 'table') continue;
    const resp = await page.request.get(
      `${E2E_BASE_URL}/api/skills/metadata.schema.query?role=${role}&resource_code=${encodeURIComponent(code)}`,
    );
    if (!resp.ok()) continue;
    const schemaBody = (await resp.json()) as Record<string, unknown>;
    const items = ((schemaBody.result ?? schemaBody) as Record<string, unknown>).items as Array<Record<string, unknown>>;
    const hasLegacyColumns = (items ?? []).some(
      (it) =>
        typeof it.schema_json === 'object' &&
        (it.schema_json as Record<string, unknown>)?.column_name &&
        !String(it.source_ref ?? '').startsWith('register:'),
    );
    if (hasLegacyColumns) {
      legacyCode = code;
      break;
    }
  }
  test.skip(!legacyCode, 'no legacy resource with field schema snapshot');

  const table = await openSchemaTable(page, legacyCode!);
  // 基线 5 列照常（存量展示不回归）；行数 ≥1 真实列。
  for (const head of ['字段', '释义', '格式', '长度', '约束']) {
    await expect(table.locator('thead')).toContainText(head);
  }
  await expect(table.locator('tbody tr').first()).toBeVisible();
});
