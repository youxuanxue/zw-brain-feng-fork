import { expect, type APIRequestContext, type Page, type TestInfo } from '@playwright/test';

export const E2E_BASE_URL = process.env.ZW_E2E_BASE_URL ?? 'http://127.0.0.1:8800';

/** Skip suite when REST+WebUI stack is not up (CI should start scripts/start-local.sh first). */
export async function skipUnlessBackend(page: Page, testInfo: TestInfo): Promise<void> {
  try {
    const resp = await page.request.get(`${E2E_BASE_URL}/`);
    if (!resp.ok()) {
      testInfo.skip(true, `backend not reachable: HTTP ${resp.status()}`);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    testInfo.skip(true, `backend not reachable: ${msg}`);
  }
}

export async function waitAppReady(page: Page): Promise<void> {
  const loginBtn = page.locator('#login-gate-submit');
  const userMenu = page.locator('.user-menu-button');
  await Promise.race([
    loginBtn.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => null),
    userMenu.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => null),
  ]);
  if (await loginBtn.isVisible().catch(() => false)) {
    await loginBtn.click();
  }
  // 每个用例 = 新浏览器上下文 → 冷启动一次会话装载（dev-bypass-login + 首拉 snapshot）；
  // 真库副本（134MB）+ 同步审计写在慢环境（worktree）偶尔 >30s 致 #role-switch 迟显、setup 假超时。
  // 抬到 60s 给冷启动余量（快环境/CI 仍秒级返回，不拖慢正常路径），消除 session-init 计时脆性。
  await page.waitForSelector('.user-menu-button', { timeout: 60_000 });
  await page.waitForSelector('#role-switch', { timeout: 60_000 });
}

export async function setRole(page: Page, role: string): Promise<void> {
  await page.waitForSelector('#role-switch', { timeout: 20_000 });
  await page.selectOption('#role-switch', role);
  // Deterministic: assert the switch actually holds the new role, then let the
  // role-triggered snapshot refetch settle (bounded). Replaces a blind 1200ms
  // sleep that could sample transient pre-refetch state.
  await expect(page.locator('#role-switch')).toHaveValue(role);
  await page.waitForLoadState('networkidle', { timeout: 4_000 }).catch(() => undefined);
}

export async function gotoHash(page: Page, hash: string): Promise<void> {
  // Force a real hashchange even when the target equals the current hash:
  // Vue router no-ops on an identical hash, so re-navigating to the same
  // detail route after a role switch would keep the previous role's rendered
  // view (stale v-if) — the root cause of the permission re-render flake. We
  // bounce through a sentinel hash first to guarantee a remount.
  await page.evaluate((h) => {
    if (window.location.hash === h) {
      window.location.hash = '#/__nav_reset__';
    }
  }, hash);
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
  // NB: do NOT assert the hash equals the target — permission-guarded routes
  // intentionally redirect away (the no-access bounce), so the final hash may
  // differ by design. Callers assert on the resulting DOM / url. Detail views
  // fetch on mount; let the route's data settle (bounded).
  await page.waitForLoadState('networkidle', { timeout: 4_000 }).catch(() => undefined);
}

/** 工作台行内发布（业务运营员）：切 BUSIAUDIT → #/workbench → 展开积压卡 → 点该条记录「发布」→ 验「已发布」toast。
 *  backlogTitle: '待发布目录' | '待发布资源'；itemTitle: 该记录标题（须唯一可定位）。
 *  发布/审核等"点一下就办"的简单动作已统一收口工作台行内办理——供数据页旧办理队列已退役，
 *  各链路的发布步骤改走本 helper（详情/多步流仍留各自收件箱）。 */
export async function publishViaWorkbench(
  page: Page,
  backlogTitle: '待发布目录' | '待发布资源',
  itemTitle: string,
): Promise<void> {
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/workbench');
  const todo = page.getByTestId('workbench-todo').filter({ hasText: backlogTitle });
  await expect(todo).toHaveCount(1, { timeout: 15_000 });
  await todo.getByTestId('workbench-todo-expand').click();
  const item = page.getByTestId('workbench-decision-item').filter({ hasText: itemTitle });
  await expect(item.first()).toBeVisible({ timeout: 15_000 });
  await item.first().getByTestId('workbench-todo-decision').filter({ hasText: '发布' }).first().click();
  await expect(page.locator('.toast-stack')).toContainText('已发布', { timeout: 15_000 });
}

/** 取第一条真实存在的 catalog_code（用于异议 spec 等需要真值 ID 的场景）。
 *  查询走**无 cookie** 的独立 APIRequestContext：带 cookie 的 page.request POST 会命中服务端
 *  CSRF 双提交拦截（dev 仅无 cookie 请求豁免，role 走 body）——同 permission_matrix 走查范式。 */
export async function firstCatalogCode(api: APIRequestContext): Promise<string | null> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_ORGAN_OPERATER', limit: 1, confirmed: true },
  });
  if (!resp.ok()) return null;
  const body = (await resp.json()) as { items?: Array<{ catalog_code?: string }> };
  return body.items?.[0]?.catalog_code ?? null;
}

/** 取第一条交付任务的 request_id；可选传 status filter，凭据三语样例需要 'granted' 才有 credential。 */
export async function firstDeliveryRequestId(
  page: Page,
  statusFilter?: string,
): Promise<string | null> {
  const resp = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_OPERATER`);
  if (!resp.ok()) return null;
  const body = (await resp.json()) as Record<string, unknown>;
  const tasks = (body.delivery_tasks ?? []) as Array<Record<string, unknown>>;
  for (const t of tasks) {
    if (statusFilter && String(t.status ?? '') !== statusFilter) continue;
    const reqId = String(t.requestId ?? t.request_id ?? '');
    if (reqId) return reqId;
  }
  return null;
}

/** 确保至少一条待发布目录；多轮 e2e 发布后队列为空时自动从 pending_review 补一条。
 *  写/查询走无 cookie 独立 APIRequestContext（带 cookie POST 命中 CSRF，见 firstCatalogCode）。 */
export async function ensurePublishQueue(api: APIRequestContext): Promise<boolean> {
  const queueResp = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (queueResp.ok()) {
    const body = (await queueResp.json()) as { items?: unknown[] };
    if (body.items?.length) return true;
  }

  const pendingResp = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'pending_review', limit: 1 },
  });
  if (!pendingResp.ok()) return false;
  const pending = (await pendingResp.json()) as {
    items?: Array<{ catalog_code?: string; id?: string }>;
  };
  const code = pending.items?.[0]?.catalog_code ?? pending.items?.[0]?.id;
  if (!code) return false;

  const reviewResp = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.review`, {
    data: {
      role: 'ROLE_BUSIAUDIT',
      catalog_code: code,
      decision: 'approve',
      confirmed: true,
    },
  });
  if (!reviewResp.ok()) return false;

  const after = await api.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (!after.ok()) return false;
  const afterBody = (await after.json()) as { items?: unknown[] };
  return Boolean(afterBody.items?.length);
}
