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
    await expect(page.getByRole('heading', { name: '可复用资源' })).toBeVisible();
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
    await expect(page.getByText(/命中 \d+ 条可复用资源|未命中/).first()).toBeVisible({ timeout: 10_000 });
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

  test('P4 任务详情 → 领凭据跳转', async ({ page }) => {
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByRole('heading', { name: '交付任务' })).toBeVisible();
    const taskLink = page.locator('a[href*="#/delivery-exchange/"]').first();
    await expect(taskLink).toBeVisible({ timeout: 8_000 });
    const href = await taskLink.getAttribute('href');
    expect(href).toMatch(/#\/delivery-exchange\//);
    await taskLink.click();
    await expect(page.getByRole('heading', { name: /交付任务/ })).toBeVisible();
    const credBtn = page.getByRole('button', { name: '领凭据' });
    if (await credBtn.isVisible()) {
      await credBtn.click();
      // 凭据跳转需交付任务有 requestId（legacy hash-id 交付可能为空 → openCredential no-op）。
      // 跳转成功则断言凭据页诚实呈现：curl/Python 样例 或 未签发提示（C-1 凭据诚实化）。
      if (/#\/delivery-exchange\/credential\//.test(page.url())) {
        await expect(
          page.getByRole('heading', { name: /凭据|调用/i }).or(page.getByText(/未签发|尚未签发|凭据尚未/)),
        ).toBeVisible({ timeout: 8_000 });
      }
    }
  });

  test('P4 凭据页诚实呈现（已签发三语样例 或 未签发提示）', async ({ page }) => {
    // D11：request_id 必须存在于库内；动态取第一条 granted 交付。
    // C-1 凭据诚实化：真实授权表无 per-grant 凭据 → legacy granted 诚实显「未签发」，
    // 仅当凭据真实签发时才有 curl/Python 三语样例。断言二者之一，不再假设捏造凭据。
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

test.describe('客户验收 — 业务运营 B1', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
  });

  test('B1.2 接入中心 → 身份治理中心', async ({ page }) => {
    await gotoHash(page, '#/integration-admin');
    await expect(page.getByRole('heading', { name: '接入扩展中心' })).toBeVisible();
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

  test('B1.2 三引擎子页 Wave2 预览 banner', async ({ page }) => {
    await gotoHash(page, '#/integration-admin/engines');
    await expect(page.getByRole('heading', { name: '三引擎配置' })).toBeVisible();
    await expect(page.getByText(/Wave\s*2|预览|草稿/i).first()).toBeVisible();
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

test.describe('客户验收 — P7 专题', () => {
  test('专题订阅按钮可用', async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/zones-pack');
    await expect(page.getByRole('heading', { name: /共享专区|专题包/ })).toBeVisible();
    // V1 起订阅持久化：未订阅的专题按钮可点订阅，已订阅的按钮置灰显示「已订阅」。
    // 优先点一个还可订阅的；若全部已订阅（库被前序测试订过），则验证「已订阅」诚实回显。
    // 列表投影较重（87 published 专题包，detail 级投影 ~1.4s），先等任一订阅态按钮
    // 渲染再分支——否则 count() 在列表加载完成前快照即取 0（原 race，与 helpers 去脆无关）。
    await expect(page.getByRole('button', { name: /订阅专题|已订阅/ }).first()).toBeVisible({
      timeout: 15_000,
    });
    const subscribeBtn = page.getByRole('button', { name: '订阅专题' }).first();
    if (await subscribeBtn.count() > 0) {
      await subscribeBtn.click();
      // 行为断言（去硬编码 toast 文案）：订阅后该专题持久置为「已订阅」态，
      // 而非断言一闪而过的 toast 文字（05-31 复核：唯一真 test-brittle）。
      await expect(page.getByRole('button', { name: '已订阅' }).first()).toBeVisible({ timeout: 8_000 });
    } else {
      await expect(page.getByRole('button', { name: '已订阅' }).first()).toBeVisible();
    }
  });
});
