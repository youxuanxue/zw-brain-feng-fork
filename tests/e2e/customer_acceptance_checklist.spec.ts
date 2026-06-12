import { test, expect } from '@playwright/test';
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

test.describe('客户验收 — 部门操作员 J1', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('P2 发现 → 发起申请入口可见', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    // D53①：找数据页标题随「只展示已发布资源」改版为「可申请资源」（原「可复用资源」退役）。
    await expect(page.getByRole('heading', { name: '可申请资源' })).toBeVisible();
    await expect(page.getByText('功能建设中')).toHaveCount(0);
    const applyBtn = page.getByRole('button', { name: /发起申请|申请/i }).first();
    await expect(applyBtn).toBeVisible();
  });

  test('P2 目录浏览 → 列真实目录并可钻取资源', async ({ page }) => {
    // D43 后目录浏览页改为真 catalog_entry 列表 + 逐行钻取到目录详情看资源
    // （旧「在发现页检索「案例」」分类快捷链接已随改版移除；断言当前真实行为，
    // 不再硬编码已不存在的分类链接 / seed 依赖的「案例」分类）。
    await gotoHash(page, '#/discovery/catalog-browse');
    await expect(page.getByRole('heading', { name: '目录浏览' })).toBeVisible();
    const drill = page.getByRole('link', { name: '查看目录资源' }).first();
    await expect(drill).toBeVisible({ timeout: 10_000 });
    await drill.click();
    await expect(page).toHaveURL(/#\/discovery\/catalog\//, { timeout: 8_000 });
  });

  test('P2 NL 加速器 → 自动搜索出资源', async ({ page }) => {
    await gotoHash(page, '#/discovery');
    await page.getByRole('button', { name: '智能检索' }).click();
    await page.getByRole('button', { name: '查省营商环境相关数据' }).click();
    await expect(page.locator('#p2-search')).toHaveValue('营商环境', { timeout: 8_000 });
    // C-1 删演示单后真实库未必有「营商环境」命中：断言 NL 加速器真实驱动了搜索
    // （命中 N 条 或 诚实「未命中」状态文案），不依赖已删的演示资源存在。
    await expect(page.getByText(/命中 \d+ 条可申请资源|未命中/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('P3 异议：新建 → 详情 → 提交至平台', async ({ page }) => {
    // D11：target_id 必须存在于库内；动态取第一条真实 catalog_code，禁止硬编码 fixture id
    const code = await firstCatalogCode(page);
    test.skip(!code, 'no catalog row available in DB to anchor objection');
    const title = `验收异议-${Date.now()}`;
    await gotoHash(page, '#/request-flow/objection/new');
    await page.locator('#title').fill(title);
    await page.locator('#target').fill(code!);
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
    await expect(page.getByRole('heading', { name: '交付任务' })).toBeVisible();
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
    await expect(page.getByRole('heading', { name: new RegExp(`${reqId}.*凭据`) })).toBeVisible();
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

  test('P5 J2 可见待办卡非零且可点', async ({ page }) => {
    // J2-7 chokepoint：MANAGER 在 P5Provider 仅可见自己有权进的待办卡（demand-match + objection），
    // 不再固定四卡 — 数量由 filterByRouteAccess 决定。
    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
    const cards = page.locator('.stat-card');
    const count = await cards.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const card = cards.nth(i);
      const n = await card.locator('strong').textContent();
      expect(Number(n ?? 0)).toBeGreaterThan(0);
    }
    await cards.first().click();
    await expect(page).toHaveURL(/#\/provider\/inbox\//);
    await expect(page.getByText('功能建设中')).toHaveCount(0);
  });

  test('P5 反向编目向导可生成建议', async ({ page }) => {
    await gotoHash(page, '#/provider/wizard/reverse-catalog');
    await expect(page.getByRole('heading', { name: '反向编目向导' })).toBeVisible();
    await page.locator('.gov-select').selectOption({ index: 1 });
    await page.getByRole('button', { name: '生成字段建议' }).click();
    await expect(page.getByText('字段建议已生成')).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('客户验收 — 业务运营 P5 发布', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    const ready = await ensurePublishQueue(page);
    if (!ready) testInfo.skip(true, 'cannot seed approved_pending_publish queue');
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
  });

  test('P5 待发布目录发布 + duplicate_warnings 字段', async ({ page }) => {
    await gotoHash(page, '#/provider');
    const btn = page.getByTestId('publish-catalog-btn').first();
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
    await expect(page.getByText('映射候选列表')).toBeVisible();
    await expect(page.locator('.data-source-badge')).toBeVisible();
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
