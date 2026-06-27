import { test, expect, request as pwRequest, type APIRequestContext } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 反馈 5/6：分型资源详情（库表/文件/接口）+ 目录详情编制规范字段。
// 资源类型已收敛为 库表/文件/API（D53②：文件夹/链接退役，folder/url 归一为 file）。
// 锚点资源/目录全部从真实 seed 库现取（D11 禁 Mock）。
//
// 锚点解析（kind→真实 resource_code + 一个挂资源目录）在 beforeAll 用独立 APIRequestContext
// 一次性完成、缓存复用——不与页面导航/资产加载抢单线程 REST，避免遍历 N×目录的串行 API 拖慢
// 触发各 test 内 waitAppReady 的连锁等待。

interface Anchors {
  byKind: Record<string, string>;
  catalogWithResources: string | null;
}
let anchors: Anchors = { byKind: {}, catalogWithResources: null };

async function resolveAnchors(api: APIRequestContext): Promise<Anchors> {
  const out: Anchors = { byKind: {}, catalogWithResources: null };
  const browse = await api.post(`${E2E_BASE_URL}/api/skills/catalog.browse`, {
    data: { role: 'ROLE_ORGAN_MANAGER', limit: 80 },
  });
  if (!browse.ok()) return out;
  const body = (await browse.json()) as { items?: Array<{ catalog_code?: string }> };
  const codes = (body.items ?? []).map((i) => i.catalog_code).filter((c): c is string => Boolean(c));
  // 资源类型收敛为 库表/文件/API（D53②）——不再解析已退役的 url/folder 锚点。
  const wanted = new Set(['table', 'file', 'service']);
  for (const code of codes) {
    if (out.byKind.table && out.byKind.file && out.byKind.service) break;
    const listResp = await api.post(`${E2E_BASE_URL}/api/skills/catalog.resource.list`, {
      data: { role: 'ROLE_ORGAN_MANAGER', catalog_code: code, limit: 50 },
    });
    if (!listResp.ok()) continue;
    const list = (await listResp.json()) as {
      total?: number;
      items?: Array<{ resource_code?: string; resource_kind?: string }>;
    };
    if ((list.total ?? 0) > 0 && !out.catalogWithResources) out.catalogWithResources = code;
    for (const r of list.items ?? []) {
      const k = String(r.resource_kind ?? '');
      if (wanted.has(k) && !out.byKind[k] && r.resource_code) out.byKind[k] = r.resource_code;
    }
  }
  return out;
}

test.beforeAll(async () => {
  const api = await pwRequest.newContext();
  try {
    anchors = await resolveAnchors(api);
  } finally {
    await api.dispose();
  }
});

test.describe('分型资源详情（反馈 6）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
  });

  test('文件资源 → 文件信息分型块', async ({ page }) => {
    const code = anchors.byKind.file;
    test.skip(!code, '真实库无文件资源');
    await gotoHash(page, `#/discovery/resource/${encodeURIComponent(code!)}`);
    await page.waitForTimeout(800);
    await expect(page.getByTestId('resource-kind-badge')).toHaveText('文件');
    const block = page.getByTestId('typed-detail-block').filter({ hasText: '文件信息' });
    await expect(block).toBeVisible();
    await expect(block).toContainText('文件名称');
    await expect(block).toContainText('文件类型');
  });

  test('库表资源 → 库表信息分型块', async ({ page }) => {
    const code = anchors.byKind.table;
    test.skip(!code, '真实库无库表资源');
    await gotoHash(page, `#/discovery/resource/${encodeURIComponent(code!)}`);
    await page.waitForTimeout(800);
    await expect(page.getByTestId('resource-kind-badge')).toHaveText('库表');
    const block = page.getByTestId('typed-detail-block').filter({ hasText: '库表信息' });
    await expect(block).toBeVisible();
    await expect(block).toContainText('物理表名');
  });

  // 「链接资源 → 链接信息分型块」用例随 D53② 链接(url)类型退役一并删除：资源类型只剩
  // 库表/文件/API，存量 url 行已归一为 file（由 test_discovery_snapshot_projection
  // ::test_enrich_discovery_resources_folds_legacy_kind 在后端守 folder/url→file 折叠）。

  test('接口资源 → 接口信息分型块（数据稀疏也渲染模板，诚实空态）', async ({ page }) => {
    const code = anchors.byKind.service;
    test.skip(!code, '真实库无接口类资源');
    await gotoHash(page, `#/discovery/resource/${encodeURIComponent(code!)}`);
    await page.waitForTimeout(800);
    await expect(page.getByTestId('resource-kind-badge')).toHaveText('接口');
    await expect(
      page.getByTestId('typed-detail-block').filter({ hasText: '接口信息' }),
    ).toBeVisible();
  });

  test('资源详情含首屏决策字段 + 可展开编目字段', async ({ page }) => {
    const code = anchors.byKind.file;
    test.skip(!code, '真实库无文件资源');
    await gotoHash(page, `#/discovery/resource/${encodeURIComponent(code!)}`);
    await page.waitForTimeout(800);
    // 首屏决策块（共享与使用）
    await expect(page.getByTestId('decision-block')).toBeVisible();
    // 编目字段默认折叠 → 展开
    const toggle = page.getByTestId('compilation-toggle');
    await expect(toggle).toBeVisible();
    await toggle.click();
    const block = page.getByTestId('compilation-block');
    await expect(block).toContainText('数据资源目录代码');
  });
});

test.describe('目录详情编制规范字段（反馈 5）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
  });

  test('目录详情展示决策字段 + 摘要 + 可展开编制规范编目字段', async ({ page }) => {
    const target = anchors.catalogWithResources;
    test.skip(!target, '真实库无挂资源目录');
    await gotoHash(page, `#/discovery/catalog/${encodeURIComponent(target!)}`);
    await page.waitForTimeout(900);
    await expect(page.getByTestId('catalog-decision-block')).toBeVisible();
    const toggle = page.getByTestId('catalog-compilation-toggle');
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByTestId('catalog-compilation-block')).toContainText('数据资源目录代码');
  });
});

test.describe('发现页筛选三件套（反馈 7）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('名称检索 + 资源类型 + 提供部门三件套均在', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(800);
    await expect(page.locator('#p2-search')).toBeVisible();
    await expect(page.getByTestId('filter-kind')).toBeVisible();
    await expect(page.getByTestId('filter-provider')).toBeVisible();
  });

  test('提供部门下拉从真实库现算（非空）', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(1000);
    const options = page.locator('[data-testid="filter-provider"] option');
    // 至少有「全部提供部门」+ ≥1 真实部门
    await expect.poll(async () => options.count()).toBeGreaterThan(1);
  });

  test('按名称检索 + 提供部门筛选可组合收窄结果', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(800);
    await page.locator('#p2-search').fill('信息');
    await page.waitForTimeout(1200);
    const before = await page.locator('.res-card').count();
    test.skip(before === 0, '检索「信息」无命中（数据形态变化）');
    // 选一个与当前检索结果仍有交集的真实提供部门（避免盲选 nth(1) 把结果筛空）。
    const providerSel = page.getByTestId('filter-provider');
    const optionCount = await providerSel.locator('option').count();
    let after = 0;
    for (let i = 1; i < optionCount; i += 1) {
      const value = await providerSel.locator('option').nth(i).getAttribute('value');
      if (!value) continue;
      await providerSel.selectOption(value);
      await page.waitForTimeout(600);
      after = await page.locator('.res-card').count();
      if (after > 0 && after <= before) break;
      await providerSel.selectOption('');
      await page.waitForTimeout(300);
    }
    test.skip(after === 0, '检索「信息」与任一提供部门组合均无命中（数据形态变化）');
    expect(after).toBeLessThanOrEqual(before);
    expect(after).toBeGreaterThan(0);
  });
});
