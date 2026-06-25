import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import {
  E2E_BASE_URL,
  ensurePublishQueue,
  firstCatalogCode,
  firstDeliveryRequestId,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
} from './helpers';

/**
 * PR #108 客户验收清单 — 逐条映射上帝视角验收表。
 * 失败即代表客户演示会踩坑，必须修到全绿。
 */

const REQUEST_CREATE_BLOCKING_STATUSES = new Set(['pending', 'submitted', 'supplementing', 'summary-pending']);

async function requestCreateBlockedResourceIds(api: APIRequestContext): Promise<Set<string>> {
  const resp = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!resp.ok()) return new Set();
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  const requests = (body.requests ?? []) as Array<Record<string, unknown>>;
  return new Set(
    requests
      .filter((r) => REQUEST_CREATE_BLOCKING_STATUSES.has(String(r.status ?? '')))
      .map((r) => String(r.resourceId ?? r.resource_id ?? ''))
      .filter(Boolean),
  );
}

async function firstDiscoveryResourceForRequest(api: APIRequestContext): Promise<string | null> {
  const blocked = await requestCreateBlockedResourceIds(api);
  const resp = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!resp.ok()) return null;
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  const discovery = (body.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  const candidates = resources.filter((r) => {
    const id = String(r.id ?? '');
    return id && !id.startsWith('recall:') && !blocked.has(id);
  });
  for (const row of candidates) {
    const id = String(row.id ?? '');
    const detail = await api.get(
      `${E2E_BASE_URL}/api/skills/catalog.resource_view?role=ROLE_ORGAN_OPERATER&resource_id=${encodeURIComponent(id)}`,
    );
    if (!detail.ok()) continue;
    const body = (await detail.json().catch(() => ({}))) as Record<string, unknown>;
    if (String(body.lifecycleStatus ?? '') === 'active') return id;
  }
  return null;
}

async function firstCatalogResourceForRequest(
  api: APIRequestContext,
): Promise<{ catalogCode: string; resourceId: string } | null> {
  const blocked = await requestCreateBlockedResourceIds(api);
  const browse = await api.post(`${E2E_BASE_URL}/api/skills/catalog.browse`, {
    data: { role: 'ROLE_ORGAN_OPERATER', lifecycle: 'active', limit: 100 },
  });
  if (!browse.ok()) return null;
  const body = (await browse.json().catch(() => ({}))) as { items?: Array<{ catalog_code?: string }> };
  const codes = (body.items ?? []).map((it) => String(it.catalog_code ?? '')).filter(Boolean);
  for (const catalogCode of codes) {
    const list = await api.post(`${E2E_BASE_URL}/api/skills/catalog.resource.list`, {
      data: { role: 'ROLE_ORGAN_OPERATER', catalog_code: catalogCode, lifecycle: 'active', limit: 50 },
    });
    if (!list.ok()) continue;
    const listBody = (await list.json().catch(() => ({}))) as {
      items?: Array<{ resource_code?: string }>;
    };
    const resource = (listBody.items ?? []).find((it) => {
      const id = String(it.resource_code ?? '');
      return id && !blocked.has(id);
    });
    if (resource?.resource_code) return { catalogCode, resourceId: resource.resource_code };
  }
  return null;
}

async function firstReverseDraftCatalogWithSuggestions(
  api: APIRequestContext,
): Promise<{ catalogCode: string; schemaRef: string } | null> {
  const resp = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
  if (!resp.ok()) return null;
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  const provider = (body.provider ?? {}) as Record<string, unknown>;
  const catalogs = (provider.catalogs ?? []) as Array<Record<string, unknown>>;
  const candidates = catalogs
    .map((c) => ({
      catalogCode: String(c.catalog_code ?? c.id ?? ''),
      schemaRef: String(c.schema_ref ?? c.schema_snapshot_ref ?? c.source_ref ?? ''),
      name: String(c.name ?? c.title ?? ''),
      status: String(c.status ?? c.lifecycle_status ?? ''),
    }))
    .filter((c) => c.catalogCode && c.schemaRef)
    .sort((a, b) => reverseDraftCandidateScore(b) - reverseDraftCandidateScore(a));
  for (const candidate of candidates) {
    const suggest = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.reverse_draft.suggest`, {
      data: { role: 'ROLE_ORGAN_MANAGER', schema_ref: candidate.schemaRef, catalog_code: candidate.catalogCode },
    });
    if (!suggest.ok()) continue;
    const result = (await suggest.json().catch(() => ({}))) as Record<string, unknown>;
    const coverage = (result.coverage ?? {}) as Record<string, unknown>;
    if (Number(coverage.total ?? 0) > 0) {
      return { catalogCode: candidate.catalogCode, schemaRef: candidate.schemaRef };
    }
  }
  return null;
}

function reverseDraftCandidateScore(candidate: { name: string; status: string }): number {
  let score = 0;
  if (candidate.status === 'active') score += 1000;
  if (candidate.status === 'draft') score += 100;
  if (candidate.status === 'pending_review') score += 50;
  if (!/测试|test|ces|dhh|未命名/i.test(candidate.name)) score += 100;
  if (candidate.name && !/^\d{12,}/.test(candidate.name)) score += 50;
  return score;
}

async function expectDraftSubmitVisible(page: Page): Promise<string> {
  await expect
    .poll(async () => page.evaluate(() => window.location.hash), { timeout: 12_000 })
    .toMatch(/#\/request-flow\/request\/(REQ-\d{4}-\d{2}-\d{2}-\d{4}|[0-9a-f]{32})/);
  const hash = await page.evaluate(() => window.location.hash);
  const requestId = decodeURIComponent(hash.split('/').pop() ?? '');
  expect(requestId, '发起申请后应进入申请详情页').toBeTruthy();

  // request.create 后快照刷新与详情读取可能竞速；重新进入详情页，断言用户最终能确认提交。
  await page.reload();
  await waitAppReady(page);
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, `#/request-flow/request/${encodeURIComponent(requestId)}`);
  await expect(page.getByRole('button', { name: '确认提交申请' })).toBeVisible({ timeout: 15_000 });
  return requestId;
}

test.describe('客户验收 — 部门操作员 J1', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('P2 找数据：资源卡查看详情 → 发起申请 → 申请详情可确认提交', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const resourceId = await firstDiscoveryResourceForRequest(api);
    await api.dispose();
    test.skip(!resourceId, 'no requestable discovery resource available');

    await gotoHash(page, '#/discovery');
    // D53①：找数据页标题随「只展示已发布资源」改版为「可申请资源」（原「可复用资源」退役）。
    await expect(page.getByRole('heading', { name: '可申请资源' })).toBeVisible();
    await expect(page.getByText('功能建设中')).toHaveCount(0);

    const resourceHref = `#/discovery/resource/${encodeURIComponent(resourceId!)}`;
    const card = page.locator('article.res-card').filter({ has: page.locator(`a[href="${resourceHref}"]`) }).first();
    await expect(card.getByRole('link', { name: '查看详情' })).toBeVisible({ timeout: 10_000 });
    await card.getByRole('link', { name: '查看详情' }).click();
    await expect(page).toHaveURL(new RegExp(`#\\/discovery\\/resource\\/${encodeURIComponent(resourceId!)}`), {
      timeout: 8_000,
    });
    const applyBtn = page.getByRole('button', { name: '发起申请' });
    await expect(applyBtn).toBeVisible();
    await applyBtn.click();
    await expectDraftSubmitVisible(page);
  });

  test('P2 目录浏览：目录详情资源卡 → 发起申请 → 申请详情可确认提交', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const anchor = await firstCatalogResourceForRequest(api);
    await api.dispose();
    test.skip(!anchor, 'no catalog resource available for request.create');

    // D43 后目录浏览页改为真 catalog_entry 列表 + 逐行钻取到目录详情看资源
    // （旧「在发现页检索「案例」」分类快捷链接已随改版移除；断言当前真实行为，
    // 不再硬编码已不存在的分类链接 / seed 依赖的「案例」分类）。
    await gotoHash(page, '#/discovery/catalog-browse');
    await expect(page.getByRole('heading', { name: '目录浏览' })).toBeVisible();
    const catalogHref = `#/discovery/catalog/${encodeURIComponent(anchor!.catalogCode)}`;
    const drill = page.locator(`a[href="${catalogHref}"]`).first();
    await expect(drill).toBeVisible({ timeout: 10_000 });
    await drill.click();
    await expect(page).toHaveURL(/#\/discovery\/catalog\//, { timeout: 8_000 });

    const resourceHref = `#/discovery/resource/${encodeURIComponent(anchor!.resourceId)}`;
    const card = page.locator('article.res-card').filter({ has: page.locator(`a[href="${resourceHref}"]`) }).first();
    const applyBtn = card.getByRole('button', { name: '发起申请' });
    await expect(applyBtn).toBeVisible({ timeout: 10_000 });
    await applyBtn.click();
    await expectDraftSubmitVisible(page);
  });

  test('P2 NL 加速器 → 自动搜索出资源', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.getByRole('button', { name: '找数助手' }).click();
    await page.getByRole('button', { name: '查历年GDP信息' }).click();
    await expect(page.locator('#p2-search')).toHaveValue(/历年GDP|GDP/, { timeout: 30_000 });
    // 客户试用入口必须把用户带到真实命中，而不是快捷按钮带空结果。
    await expect(page.getByText(/命中 [1-9]\d* 条可申请资源/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('P2 空态给真实下一步：浏览目录 / 登记需求', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.locator('#p2-search').fill(`验收无命中-${Date.now()}-not-found`);
    await expect(page.getByText('未命中资源。')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '浏览目录' })).toBeVisible();
    await expect(page.getByRole('link', { name: '登记需求 / 找不到数据' })).toBeVisible();
    await expect(page.getByRole('button', { name: '发起申请' })).toHaveCount(0);
  });

  test('P3 异议：新建 → 详情 → 提交至平台', async ({ page, playwright }) => {
    // D11：target_id 必须存在于库内；动态取第一条真实 catalog_code，禁止硬编码 fixture id
    const api = await playwright.request.newContext();
    const code = await firstCatalogCode(api);
    await api.dispose();
    test.skip(!code, 'no catalog row available in DB to anchor objection');
    const title = `验收异议-${Date.now()}`;
    await gotoHash(page, '#/request-flow/objection/new');
    await page.locator('#title').fill(title);
    await page.locator('#target').fill(code!);
    // 「创建异议」需 title+target+basis(异议依据) 三字段齐才启用（P3ObjectionNew.vue 行内校验）。
    await page.locator('#basis').fill('验收走查：字段描述与底册不一致');
    await page.getByRole('button', { name: '创建异议' }).click();
    await expect(page).toHaveURL(/#\/request-flow\/objection\/[^/]+$/, { timeout: 10_000 });
    await expect(page.getByRole('button', { name: '提交至平台' })).toBeVisible();
    await page.getByRole('button', { name: '提交至平台' }).click();
    await expect(page.getByText(/已提交|提交/i).first()).toBeVisible({ timeout: 8_000 });
    await gotoHash(page, '#/request-flow/objection');
    await expect(page.locator('.focus-table, table').getByText(title)).toBeVisible({ timeout: 8_000 });
  });

  test('P3 供需：登记 → 列表 → 推进一阶', async ({ page }) => {
    await gotoHash(page, '#/request-flow/supply-demand');
    const title = `验收需求-${Date.now()}`;
    await page.locator('#demand-title').fill(title);
    await page.getByRole('button', { name: '登记需求' }).click();
    await expect(page.locator('.focus-table tbody tr').filter({ hasText: title })).toBeVisible({
      timeout: 8_000,
    });
    await page.locator('.focus-table tbody tr').filter({ hasText: title }).click();
    const advance = page.locator('.detail-workspace').getByRole('button', { name: /推进至/ });
    await expect(advance).toBeVisible();
    await advance.click();
    await expect(page.getByText(/已提交|阶段/i).first()).toBeVisible({ timeout: 8_000 });
  });

  test('P4 任务详情 → 按资源类型分流操作（0611 §B 方案 B）', async ({ page }) => {
    // D53⑥（F1/6.4#15）：交付回执收窄到「部门管理员」——P4 交付归 MANAGER，
    // OPERATER 已无访问（路由层重定向）。此处切到 MANAGER 走真实交付旅程。
    // 0611 业务口径确认单 §B（2026-06-12 方案 B 终裁）：详情页操作按资源类型分流——
    // API/未知=「查看授权」、文件=「下载」、库表=「核对交换结果」（交换任务语系）。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/delivery-exchange');
    // IA 重构（拆「办申请」）：P4Delivery 升级为「领数据」一站入口——页头 h1=「领数据」，
    // 「交付任务」由独立页降为页内视图 tab（p4-view-tasks / p4-pane-tasks）。先切到交付任务视图。
    await expect(page.getByRole('heading', { name: '领数据' })).toBeVisible();
    await page.getByTestId('p4-view-tasks').click();
    await expect(page.getByTestId('p4-pane-tasks')).toBeVisible();
    const taskLink = page.locator('a[href*="#/delivery-exchange/task/"]').first();
    await expect(taskLink).toBeVisible({ timeout: 8_000 });
    const href = await taskLink.getAttribute('href');
    expect(href).toMatch(/#\/delivery-exchange\/task\//);
    await taskLink.click();
    // 标题随资源类型分语系：库表=「交换任务」、其余=「交付任务」。
    // level:1 锁页头 h1（库表详情还有 h2「交换任务详情」面板标题，同 regex 会双命中触发 strict mode）。
    await expect(page.getByRole('heading', { name: /交付任务|交换任务/, level: 1 })).toBeVisible();
    // 分流后操作区只渲染当前类型可执行的单一动作（不再领凭据+对账回执双按钮混排）。
    const actionBtn = page.getByRole('button', { name: /^(查看授权|下载|核对交换结果)$/ });
    await expect(actionBtn).toHaveCount(1);
    const credBtn = page.getByRole('button', { name: '查看授权' });
    if (await credBtn.isVisible()) {
      await credBtn.click();
      // 授权跳转需交付任务有 requestId（legacy hash-id 交付可能为空 → openCredential no-op）。
      // 跳转成功则断言凭据页诚实呈现：curl/Python 样例 或 未签发提示（C-1 凭据诚实化）。
      if (/#\/delivery-exchange\/credential\//.test(page.url())) {
        await expect(
          page.getByRole('heading', { name: /凭据|授权|调用/i }).or(page.getByText(/未签发|尚未签发|凭据尚未/)),
        ).toBeVisible({ timeout: 8_000 });
      }
    }
  });

  test('P4 凭据页诚实呈现（已签发三语样例 或 未签发提示）', async ({ page }) => {
    // D11：request_id 必须存在于库内；动态取第一条 granted 交付。
    // C-1 凭据诚实化：真实授权表无 per-grant 凭据 → legacy granted 诚实显「未签发」，
    // 仅当凭据真实签发时才有 curl/Python 三语样例。断言二者之一，不再假设捏造凭据。
    // D53⑥：凭据页归「部门管理员」（OPERATER 路由层已重定向）。切 MANAGER 走真实凭据旅程。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    const reqId = await firstDeliveryRequestId(page, 'granted');
    test.skip(!reqId, 'no granted delivery_task in snapshot');
    await gotoHash(page, `#/delivery-exchange/credential/${reqId}`);
    // R12：凭据页 H1 使用资源名，不把 32 位 request_id 当主标题直出；编号另在次行短码呈现。
    await expect(page.getByRole('heading', { name: /凭据|授权/, level: 1 })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'curl', exact: true }).or(page.getByText(/未签发|尚未签发|凭据尚未/)).first(),
    ).toBeVisible({ timeout: 12_000 });
  });
});

test.describe('客户验收 — 部门管理员 J2', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
  });

  test('P5 J2 可见待办卡计数真实且可点', async ({ page }) => {
    // J2-7 chokepoint：MANAGER 在 P5Provider 仅可见自己有权进的待办卡，数量由
    // filterByRouteAccess 决定。D57⑧ 后含「反向编目审核」（部门审入口卡）——
    // 入口卡零积压也渲染（深链到诚实空态收件箱，非死链），故计数断言为合法数字 ≥0。
    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
    const cards = page.locator('.stat-card');
    const count = await cards.count();
    expect(count).toBeGreaterThan(0);
    await expect(page.locator('.stat-card', { hasText: '反向编目审核' })).toHaveCount(1);
    for (let i = 0; i < count; i++) {
      const card = cards.nth(i);
      const n = await card.locator('strong').textContent();
      expect(Number(n ?? -1)).toBeGreaterThanOrEqual(0);
    }
    await cards.first().click();
    await expect(page).toHaveURL(/#\/provider\/inbox\//);
    await expect(page.getByText('功能建设中')).toHaveCount(0);
  });

  test('P5 反向编目向导可生成建议', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const anchor = await firstReverseDraftCatalogWithSuggestions(api);
    await api.dispose();
    test.skip(!anchor, 'no reverse-draft catalog with schema suggestions available');

    await gotoHash(page, '#/provider/wizard/reverse-catalog/detail');
    await expect(page.getByRole('heading', { name: '反向编目向导' })).toBeVisible();
    await page.locator('.gov-select').selectOption(anchor!.catalogCode);
    await page.getByRole('button', { name: '生成字段建议' }).click();
    await expect(page.getByText('字段建议已生成')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('reverse-field-candidates')).toBeVisible();
  });
});

test.describe('客户验收 — 业务运营 P5 发布', () => {
  test.beforeEach(async ({ page, playwright }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    const api = await playwright.request.newContext();
    const ready = await ensurePublishQueue(api);
    await api.dispose();
    if (!ready) testInfo.skip(true, 'cannot seed approved_pending_publish queue');
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
  });

  test('工作台待发布目录行内发布 + duplicate_warnings 字段', async ({ page }) => {
    // 发布统一收口工作台行内（供数据页旧发布队列退役）；契约不变：响应含 duplicate_warnings。
    await gotoHash(page, '#/workbench');
    const todo = page.getByTestId('workbench-todo').filter({ hasText: '待发布目录' });
    await expect(todo).toHaveCount(1, { timeout: 12_000 });
    await todo.getByTestId('workbench-todo-expand').click();
    const btn = page
      .getByTestId('workbench-decision-item')
      .first()
      .getByTestId('workbench-todo-decision')
      .filter({ hasText: '发布' })
      .first();
    await expect(btn).toBeVisible({ timeout: 12_000 });
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/skills/catalog.entry.publish') && r.ok(),
    );
    await btn.click();
    const resp = await respPromise;
    const json = (await resp.json()) as Record<string, unknown>;
    const inner = (json.result ?? json) as Record<string, unknown>;
    expect(Array.isArray(inner.duplicate_warnings)).toBe(true);
  });
});

test.describe('客户验收 — 平台运维员 B1', () => {
  // D55/P2·P3·P4：后台 B1.2（外部系统 / 流程与表单配置 / 身份治理）归平台运维员独有，
  // 业务运营员退出（见末尾「业务运营员无权进 B1.2」收权用例同源守卫）。
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_SYSTEM');
  });

  test('身份治理独立左导航可达（Q1 裁决：不再寄居接入中心 tab 栏）', async ({ page }) => {
    await gotoHash(page, '#/integration-admin');
    await expect(page.getByRole('heading', { name: '外部系统', exact: true })).toBeVisible();
    await expect(page.getByText('功能建设中')).toHaveCount(0);
    await expect(page.getByRole('link', { name: '身份治理' })).toBeVisible();
    await page.getByRole('link', { name: '身份治理' }).click();
    await expect(page).toHaveURL(/#\/integration-admin\/iam-governance/, { timeout: 8_000 });
    await expect(page.getByRole('heading', { name: '身份治理' })).toBeVisible();
    // 身份治理保留用户与角色 / 谁能访问什么两个管理面，旧权限映射审核不再作为页面模块出现。
    await expect(page.getByRole('tab', { name: '用户与角色' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '谁能访问什么' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '旧权限映射审核' })).toHaveCount(0);
  });

  test('B1.2 能力包详情链', async ({ page }) => {
    await gotoHash(page, '#/integration-admin');
    const detailLink = page.locator('a[href*="#/integration-admin/package/"]').first();
    await expect(detailLink).toBeVisible({ timeout: 12_000 });
    await detailLink.click();
    await expect(page).toHaveURL(/#\/integration-admin\/package\//, { timeout: 8_000 });
    await expect(page.getByText('功能建设中')).toHaveCount(0);
  });

  test('B1.2 部门操作员无权进身份治理', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/integration-admin/iam-governance');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toMatch(/#\/integration-admin\/iam-governance/);
  });

  test('B1.2 业务运营员无权进 B1.2（D55/P2·P4 收权）', async ({ page }) => {
    // 收权实证：外部系统 / 身份治理 D55 归平台运维员独有，业务运营员被路由守卫踢出（无权=不可见）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/integration-admin');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toMatch(/#\/integration-admin/);
  });

  test('B1.2 流程与表单配置子页可达（去黑话：无三引擎/Wave 字样）', async ({ page }) => {
    await gotoHash(page, '#/integration-admin/engines');
    await expect(page.getByRole('heading', { name: '流程与表单配置' })).toBeVisible();
    await expect(page.getByText(/预览|草稿/).first()).toBeVisible();
    await expect(page.getByText(/三引擎|Wave\s*2/i)).toHaveCount(0);
  });
});

test.describe('客户验收 — 安全审计 B1.1', () => {
  test('合规四 panel + 调查助手', async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_SECURITY_AUDIT');
    await gotoHash(page, '#/compliance-ops');
    await expect(page.getByRole('heading', { name: '合规与运营' })).toBeVisible();
    await expect(page.getByText('功能建设中')).toHaveCount(0);
    await expect(page.getByText('扫描事件').first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: '就当前视图生成摘要' }).click();
    await expect(page.locator('.assistant-summary').first()).toBeVisible({ timeout: 20_000 });
  });
});

// 「客户验收 — P7 专题」describe 随专题包整面退出本期而移除（D55/P6，#235）：
// #/zones-pack 路由已下线、订阅按钮无渲染面，验收项一并退役（待专题包复活时恢复）。
