import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 缺陷 1（0604 客户试用反馈）守卫：起草复用申请后**直达草稿详情**，流程不断头.
 *
 * 试用实锤：点「发起复用申请」→ toast「复用申请已起草」→ 用户被扔在原地，找不到刚起草
 * 的记录。根因：request.create 是写能力，REST 把返回包成 `{ ok, result: { request_id } }`，
 * 前端 resolveRequestIdFromAction 只看顶层 id（恒缺）→ 取不到 id → navigateToRequestDetail
 * 不触发。修复后应直落 `#/request-flow/request/<REQ-id>` 详情页（可确认/可提交）。
 *
 * 守护点：
 *   - 在资源详情点「发起复用申请」后，**URL 落到该草稿的详情路由**（非停在资源详情/发现页）。
 *   - 详情页**渲染出该申请**（标题=申请号、基本信息可见），即用户能确认刚起草的内容。
 */

/**
 * 找一个**尚无在途申请**的可发现资源——确保点「发起复用申请」走的是 request.create 的
 * **成功信封**路径（`{ ok, result: { request_id } }`），这正是缺陷 1 的根因路径：
 * 旧 resolveRequestIdFromAction 只看顶层 id，对成功信封取不到 id → 不跳转。
 * （若资源已有在途申请，request.create 返 invalid_state，detail 里带现成 REQ-id，会被
 *  另一条 regex 回退路径救活——那不是本缺陷要守的路径，故排除。）
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
  // 已有在途申请的 resourceId 集合（active 态：非终结）。
  const busyResourceIds = new Set(
    requests
      .filter((r) => !['completed', 'rejected', 'withdrawn'].includes(String(r.status ?? '')))
      .map((r) => String(r.resourceId ?? r.resource_id ?? ''))
      .filter(Boolean),
  );
  const r = resources.find((x) => x.id && !busyResourceIds.has(String(x.id)));
  return r ? String(r.id) : null;
}

test.describe('起草复用申请 · 直达草稿详情闭环', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('发起复用申请 → 直达申请详情（非原地不动）', async ({ page }) => {
    const resId = await freshDiscoverableResource(page);
    test.skip(!resId, 'no fresh (no in-flight request) discoverable resource in this DB');

    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, `#/discovery/resource/${resId}`);

    const applyBtn = page.locator('button[data-skill="request.create"]');
    await expect(applyBtn).toBeVisible();
    await applyBtn.click();

    // 起草成功后应离开资源详情、落到申请详情路由（Action D：新铸申请编码为 32 位 hex，
    // 与导入单同形；存量 REQ-* 历史编号兼容）。
    await expect
      .poll(async () => page.evaluate(() => window.location.hash), { timeout: 8_000 })
      .toMatch(/#\/request-flow\/request\/(REQ-\d{4}-\d{2}-\d{2}-\d{4}|[0-9a-f]{32})/);

    const hash = await page.evaluate(() => window.location.hash);
    const reqId = hash.split('/').pop() as string;

    // 详情页确实把这条草稿渲染出来：用户可确认并提交，且不出现“申请已生成但未找到”断头。
    await expect(page.locator('main.focus-page')).toBeVisible();
    await expect(page.getByText('未找到该申请')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '确认提交申请' })).toBeVisible();
  });
});
