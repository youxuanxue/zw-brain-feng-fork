import { expect, type Page, type TestInfo } from '@playwright/test';

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
  await page.waitForSelector('.user-menu-button', { timeout: 30_000 });
  await page.waitForSelector('#role-switch', { timeout: 30_000 });
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

/** 取第一条真实存在的 catalog_code（用于异议 spec 等需要真值 ID 的场景）。 */
export async function firstCatalogCode(page: Page): Promise<string | null> {
  const resp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
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

/** 确保至少一条待发布目录；多轮 e2e 发布后队列为空时自动从 pending_review 补一条。 */
export async function ensurePublishQueue(page: Page): Promise<boolean> {
  const queueResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (queueResp.ok()) {
    const body = (await queueResp.json()) as { items?: unknown[] };
    if (body.items?.length) return true;
  }

  const pendingResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'pending_review', limit: 1 },
  });
  if (!pendingResp.ok()) return false;
  const pending = (await pendingResp.json()) as {
    items?: Array<{ catalog_code?: string; id?: string }>;
  };
  const code = pending.items?.[0]?.catalog_code ?? pending.items?.[0]?.id;
  if (!code) return false;

  const reviewResp = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.review`, {
    data: {
      role: 'ROLE_BUSIAUDIT',
      catalog_code: code,
      decision: 'approve',
      confirmed: true,
    },
  });
  if (!reviewResp.ok()) return false;

  const after = await page.request.post(`${E2E_BASE_URL}/api/skills/catalog.entry.query`, {
    data: { role: 'ROLE_BUSIAUDIT', lifecycle_status: 'approved_pending_publish', limit: 1 },
  });
  if (!after.ok()) return false;
  const afterBody = (await after.json()) as { items?: unknown[] };
  return Boolean(afterBody.items?.length);
}
