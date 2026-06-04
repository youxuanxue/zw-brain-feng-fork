import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 缺陷 2（0604 客户试用反馈）守卫：业务运营员工作台「今日待办」零死端 + 真实库现算.
 *
 * 守护点：
 *   - 业务运营员（ROLE_BUSIAUDIT）的每条待办都是**可点的深链**（<a href>，非纯文本死项）。
 *   - 点击任一待办**落到可办理页面**（非 404、非原地不动；目标 shell 渲染出来）。
 *   - 待办数据**从真实库现算**（待发布/待审核目录 + 待审核资源 + 待受理申请），与
 *     catalog.entry.query / resource.asset.query / 申请态的真实积压一致，而非 seed 写死文案。
 */

interface WorkbenchTodo {
  id: string;
  title: string;
  href?: string;
}

async function fetchWorkbench(
  page: import('@playwright/test').Page,
  role: string,
): Promise<{ todos: WorkbenchTodo[] } | null> {
  const resp = await page.request.get(
    `${E2E_BASE_URL}/api/skills/workbench.view?role=${encodeURIComponent(role)}`,
  );
  if (!resp.ok()) return null;
  return (await resp.json()) as { todos: WorkbenchTodo[] };
}

async function countCatalog(
  page: import('@playwright/test').Page,
  lifecycle: string,
): Promise<number> {
  // GET（catalog.entry.query 是读能力）避免 page.request.post 的 BFF CSRF 门，与
  // workbench 后端现算同口径（也走 GET 读路径）。
  const resp = await page.request.get(
    `${E2E_BASE_URL}/api/skills/catalog.entry.query?role=ROLE_BUSIAUDIT&lifecycle_status=${encodeURIComponent(lifecycle)}&limit=1`,
  );
  if (!resp.ok()) return -1;
  const body = (await resp.json()) as { total?: number };
  return Number(body.total ?? -1);
}

test.describe('业务运营员工作台 · 待办零死端 + 真实库现算', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('每条待办可点深链 + 落到可办理页面', async ({ page }) => {
    const wb = await fetchWorkbench(page, 'ROLE_BUSIAUDIT');
    test.skip(!wb, 'workbench.view unreachable');
    const todos = wb!.todos ?? [];
    test.skip(todos.length === 0, 'no real backlog todos for business operator in this DB');

    // 每条待办都必须带深链（href），不存在「有标题无去处」的死项。
    for (const t of todos) {
      expect(t.href, `todo ${t.title} must carry a deep link`).toBeTruthy();
      expect(String(t.href).startsWith('#/'), `todo href is a hash route: ${t.href}`).toBeTruthy();
    }

    // UI 侧：业务运营员工作台每条待办渲染为可点 <a>。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');
    const links = page.locator('[data-testid="workbench-todo-link"]');
    await expect(links.first()).toBeVisible();
    expect(await links.count()).toBe(todos.length);

    // 遍历每条待办：点进去落到可办理页（shell 渲染、非 404 空壳、非停在工作台）。
    for (let i = 0; i < todos.length; i++) {
      const todo = todos[i];
      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, '#/workbench');
      const link = page.locator('[data-testid="workbench-todo-link"]').nth(i);
      await expect(link).toBeVisible();
      await link.click();
      // 目标页是 provider / request-flow shell——断言路由真的变了（非原地不动）
      // 且页面主区渲染出来（main.focus-page 存在、非 404 文案）。
      await page.waitForLoadState('networkidle', { timeout: 4_000 }).catch(() => undefined);
      const hash = await page.evaluate(() => window.location.hash);
      expect(hash, `todo "${todo.title}" navigated away from workbench`).not.toBe('#/workbench');
      expect(hash.startsWith(String(todo.href).split('?')[0])).toBeTruthy();
      await expect(page.locator('main.focus-page')).toBeVisible();
      await expect(page.getByText('not_found')).toHaveCount(0);
    }
  });

  test('待办计数与真实库积压一致（待发布/待审核目录）', async ({ page }) => {
    const wb = await fetchWorkbench(page, 'ROLE_BUSIAUDIT');
    test.skip(!wb, 'workbench.view unreachable');
    const todos = wb!.todos ?? [];

    const pendingPublish = await countCatalog(page, 'approved_pending_publish');
    const pendingReview = await countCatalog(page, 'pending_review');
    test.skip(pendingPublish < 0 || pendingReview < 0, 'catalog.entry.query unreachable');

    const publishTodo = todos.find((t) => t.id === 'backlog-catalog-publish');
    const reviewTodo = todos.find((t) => t.id === 'backlog-catalog-review');

    // 现算口径：DB 有积压才出待办；待办标题数字 = 真实库该生命周期态计数。
    if (pendingPublish > 0) {
      expect(publishTodo, '待发布目录积压>0 应有对应待办').toBeTruthy();
      expect(publishTodo!.title).toContain(String(pendingPublish));
    } else {
      expect(publishTodo, '待发布目录零积压则无对应待办（无空死链）').toBeFalsy();
    }
    if (pendingReview > 0) {
      expect(reviewTodo, '待审核目录积压>0 应有对应待办').toBeTruthy();
      expect(reviewTodo!.title).toContain(String(pendingReview));
    } else {
      expect(reviewTodo).toBeFalsy();
    }
  });
});
