import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 表单填报（form-autofill）真 UI 守卫：草稿详情渲染可编辑申请表单，
 * 字段带 provenance 四态（待填/AI建议·待确认/自动带出只读/已填锁定），
 * 人原地修订后该字段转「已填写」并锁定（此后自动填充/AI 不再覆盖）。
 *
 * 端到端链路：资源详情「发起复用申请」→ 直达草稿详情 → 申请表单面板 →
 * 改一个文本字段 → request.field.update → pill 变「已填写」+ 锁标。
 * 派生字段（区划/机构名称）渲染为只读（无输入框），体现派生权威不可手填。
 */

async function freshDiscoverableResource(
  page: import('@playwright/test').Page,
): Promise<string | null> {
  const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!snap.ok()) return null;
  const body = (await snap.json()) as Record<string, unknown>;
  const resources = ((body.discovery as Record<string, unknown>)?.resources ?? []) as Array<
    Record<string, unknown>
  >;
  const requests = (body.requests ?? []) as Array<Record<string, unknown>>;
  const busy = new Set(
    requests
      .filter((r) => !['completed', 'rejected', 'withdrawn'].includes(String(r.status ?? '')))
      .map((r) => String(r.resourceId ?? r.resource_id ?? ''))
      .filter(Boolean),
  );
  const r = resources.find((x) => x.id && !busy.has(String(x.id)));
  return r ? String(r.id) : null;
}

test.describe('表单填报 · 自动填充 + 原地修订锁定', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('草稿表单渲染 provenance 四态，改字段后锁定', async ({ page }) => {
    const resId = await freshDiscoverableResource(page);
    test.skip(!resId, 'no fresh discoverable resource in this DB');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/discovery/resource/${resId}`);

    const applyBtn = page.locator('button[data-skill="request.create"]');
    await expect(applyBtn).toBeVisible();
    await applyBtn.click();

    // 落到草稿详情（Action D：新铸申请编码为 32 位 hex）。
    await expect
      .poll(async () => page.evaluate(() => window.location.hash), { timeout: 8_000 })
      .toMatch(/#\/request-flow\/request\/(REQ-|[0-9a-f]{32})/);

    // 可编辑申请表单面板出现。
    const panel = page.locator('section.ff-panel');
    await expect(panel).toBeVisible();

    // 至少一个 provenance pill（四态之一）渲染。
    await expect(panel.locator('.ff-pill').first()).toBeVisible();

    // 派生字段（区划名称）只读：无输入框，渲染为只读值。
    const regionNameInput = panel.locator('[data-testid="ff-region_name"]');
    await expect(regionNameInput).toHaveCount(0);

    // 改「申请用途」文本字段 → 触发 request.field.update。
    const purpose = panel.locator('[data-testid="ff-purpose"]');
    await expect(purpose).toBeVisible();
    await purpose.fill('用于营商环境专班数据核验');
    await purpose.blur();

    // 改后该字段 pill 变「已填写」（human），并出现锁标。
    const purposePill = panel.locator('[data-testid="ff-pill-purpose"]');
    await expect(purposePill).toHaveText(/已填写/, { timeout: 8_000 });
    await expect(purposePill).toHaveClass(/ff-human/);

    // 枚举字段仍是字典下拉（真实选项）。
    await expect(panel.locator('select[data-testid="ff-apply_domain"] option').nth(1)).toBeAttached();

    // 机构选择器（18750 机构）：搜索分页 picker —— 打开 → 搜索 → 有结果（找得到、点得动）。
    const organTrigger = panel.locator('[data-testid="ff-organ_code"]');
    await expect(organTrigger).toBeVisible();
    await organTrigger.click();
    const organSearch = page.locator('[data-testid="ff-organ_code-search"]');
    await expect(organSearch).toBeVisible();
    await organSearch.fill('局'); // 政府机构普遍含「局」，保证有命中
    await expect(page.locator('[data-testid="ff-organ_code-list"] .rp-item').first()).toBeVisible({ timeout: 8_000 });
    await page.locator('.rp-backdrop').click({ position: { x: 5, y: 5 } }); // 点遮罩角落关闭 picker（中心可能被向下展开的弹层覆盖）

    // 区划选择器：逐级下钻 picker —— 打开 → 顶级区划列表可见（省级）。
    const regionTrigger = panel.locator('[data-testid="ff-region_code"]');
    await expect(regionTrigger).toBeVisible();
    await regionTrigger.click();
    await expect(page.locator('[data-testid="ff-region_code-list"] .rp-item').first()).toBeVisible({ timeout: 8_000 });
    await page.locator('.rp-backdrop').click({ position: { x: 5, y: 5 } }); // 点遮罩角落关闭 picker（中心可能被向下展开的弹层覆盖）

    // AI 建议填充：点按钮 → 空可建议字段转「AI建议·待确认」；人填的 purpose 不被覆盖；草稿不自动提交。
    const aiBtn = panel.locator('[data-testid="ff-ai-suggest"]');
    await expect(aiBtn).toBeVisible();
    await aiBtn.click();
    await expect(panel.locator('.ff-pill.ff-ai').first()).toBeVisible({ timeout: 10_000 });
    await expect(purposePill).toHaveText(/已填写/); // 人填字段仍锁定，未被 AI 覆盖
  });
});
