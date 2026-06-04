import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * P2 资源详情「字段数据模型」只读块 e2e（render-debt 还债：metadata.schema.query）。
 *
 * 守护点：
 *   - 授权岗位（MANAGER）在带 schema 的资源详情页能看到「字段数据模型」表（真实列）。
 *   - 无权岗位（OPERATER）整块从 DOM 完全消失（无权=不可见，非 disabled/非静默失败）。
 *   - 前端用 useResourceSchema 接通用 /api/skills/metadata.schema.query，不新增 REST 路由。
 */

function hasColumnRows(result: Record<string, unknown>): boolean {
  const items = (result.items ?? []) as Array<Record<string, unknown>>;
  return items.some(
    (it) => it && typeof it.schema_json === 'object' && (it.schema_json as Record<string, unknown>)?.column_name,
  );
}

/**
 * 找一个真有逐列数据模型、且经 P2 发现页可达的 resource_code。
 * discovery.resources 的 id 即 resource_asset.resource_code（P2 资源详情 route param）；
 * 逐个用 metadata.schema.query 探测列级 schema，命中第一个返回。
 */
async function resourceCodeWithSchema(page: import('@playwright/test').Page): Promise<string | null> {
  const role = 'ROLE_ORGAN_MANAGER';
  const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=${role}`);
  if (!snap.ok()) return null;
  const body = (await snap.json()) as Record<string, unknown>;
  const discovery = (body.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  for (const r of resources) {
    const code = String(r.id ?? '');
    if (!code) continue;
    const schemaResp = await page.request.get(
      `${E2E_BASE_URL}/api/skills/metadata.schema.query?role=${role}&resource_code=${encodeURIComponent(code)}`,
    );
    if (!schemaResp.ok()) continue;
    const schemaBody = (await schemaResp.json()) as Record<string, unknown>;
    if (hasColumnRows((schemaBody.result ?? schemaBody) as Record<string, unknown>)) return code;
  }
  return null;
}

/** 找一个真实库里**确实没有**字段模型的可见资源（用于断言诚实空态、非 404）。 */
async function resourceCodeWithoutSchema(
  page: import('@playwright/test').Page,
): Promise<string | null> {
  const role = 'ROLE_ORGAN_MANAGER';
  const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=${role}`);
  if (!snap.ok()) return null;
  const body = (await snap.json()) as Record<string, unknown>;
  const discovery = (body.discovery ?? {}) as Record<string, unknown>;
  const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
  for (const r of resources) {
    const code = String(r.id ?? '');
    if (!code) continue;
    const schemaResp = await page.request.get(
      `${E2E_BASE_URL}/api/skills/metadata.schema.query?role=${role}&resource_code=${encodeURIComponent(code)}`,
    );
    // 缺陷 3 守护点：后端对无 schema 资源也必须返 200（诚实空），绝不 404。
    expect(schemaResp.status(), `metadata.schema.query must never 404 for ${code}`).toBe(200);
    const schemaBody = (await schemaResp.json()) as Record<string, unknown>;
    if (!hasColumnRows((schemaBody.result ?? schemaBody) as Record<string, unknown>)) return code;
  }
  return null;
}

test.describe('P2 资源详情 · 字段数据模型只读块', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('MANAGER 可见真实字段数据模型 / OPERATER 整块不渲染', async ({ page }) => {
    const resId = await resourceCodeWithSchema(page);
    test.skip(!resId, 'no discovery resource with field schema snapshot');

    // 授权岗位：看到「字段数据模型」块 + 真实列表。
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    const block = page.locator('[data-testid="resource-schema-block"]');
    await expect(block).toBeVisible();
    await expect(page.getByRole('heading', { name: '字段数据模型' })).toBeVisible();
    const table = page.locator('[data-testid="resource-schema-table"]');
    await expect(table).toBeVisible();
    // 至少一真实列行（thead + ≥1 tbody 行）。
    await expect(table.locator('tbody tr').first()).toBeVisible();

    // 无权岗位：整块从 DOM 消失（不是 disabled，不是 hidden）。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/discovery/resource/${resId}`);
    await expect(page.locator('[data-testid="resource-schema-block"]')).toHaveCount(0);
  });

  test('无 schema 资源 → 诚实空态（非 404 错误态）', async ({ page }) => {
    const resId = await resourceCodeWithoutSchema(page);
    test.skip(!resId, 'no discovery resource lacking field schema in this DB');

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/discovery/resource/${resId}`);

    // 块仍渲染（授权岗位），但走诚实空态——不是「加载失败：HTTP 404」错误态。
    await expect(page.locator('[data-testid="resource-schema-block"]')).toBeVisible();
    await expect(page.locator('[data-testid="resource-schema-empty"]')).toBeVisible();
    await expect(page.locator('[data-testid="resource-schema-error"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="resource-schema-table"]')).toHaveCount(0);
  });
});
