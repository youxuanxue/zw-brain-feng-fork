import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady, E2E_BASE_URL } from './helpers';

/**
 * 业务运营员工作台 · 待办零死端 + 真实库现算（行内办理收口后更新）.
 *
 * 守护点：
 *   - 每条待办**或为可点深链**（聚合背包，<a href>）**或为行内可办**（per-application 受理，
 *     携 `action` 决策载荷 → 展开就地办、不跳出 #/workbench）——不存在「有标题无去处」死项。
 *   - 深链待办点击**落到可办理页面**（非 404、非原地不动；目标 shell 渲染出来）。
 *   - 行内待办展开出**决策面板**、**仍停在 #/workbench**（就地办、不跳走）——工作台收口
 *     受理/审核动作后的核心契约（反转旧「待办必跳走」断言）。
 *   - 待办数据**从真实库现算**；审核（目录/资源审批）属部门管理员，不进业务运营员工作台（E2，D53）。
 */

interface WorkbenchTodo {
  id: string;
  title: string;
  href?: string;
  // 行内自描述决策载荷（per-application 受理待办携带）；聚合背包待办无此字段。
  action?: { capability?: string } | null;
}

function isInline(t: WorkbenchTodo): boolean {
  return !!t.action && typeof t.action === 'object';
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

test.describe('业务运营员工作台 · 待办零死端（行内办理 + 深链）+ 真实库现算', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('每条待办或深链或行内可办 + 落到可办理处 / 就地展开', async ({ page }) => {
    const wb = await fetchWorkbench(page, 'ROLE_BUSIAUDIT');
    test.skip(!wb, 'workbench.view unreachable');
    const todos = wb!.todos ?? [];
    test.skip(todos.length === 0, 'no real backlog todos for business operator in this DB');

    const inline = todos.filter(isInline);
    const linked = todos.filter((t) => !isInline(t));

    // 无死项：深链待办带 hash 深链；行内待办带决策能力。
    for (const t of linked) {
      expect(t.href, `linked todo ${t.title} must carry a deep link`).toBeTruthy();
      expect(String(t.href).startsWith('#/'), `todo href is a hash route: ${t.href}`).toBeTruthy();
    }
    for (const t of inline) {
      expect(t.action!.capability, `inline todo ${t.title} must carry a decision capability`).toBeTruthy();
    }

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');

    // 深链待办渲染为可点链接；行内待办渲染为「展开办理」按钮。计数对齐分区（无遗漏、无错配）。
    const links = page.locator('[data-testid="workbench-todo-link"]');
    const expanders = page.locator('[data-testid="workbench-todo-expand"]');
    if (linked.length) await expect(links.first()).toBeVisible();
    expect(await links.count()).toBe(linked.length);
    expect(await expanders.count()).toBe(inline.length);

    // 深链待办：逐条点进去落到可办理页（路由真的变、main 渲染、非 404 空壳）。
    for (let i = 0; i < linked.length; i++) {
      const todo = linked[i];
      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, '#/workbench');
      const link = page.locator('[data-testid="workbench-todo-link"]').nth(i);
      await expect(link).toBeVisible();
      await link.click();
      await page.waitForLoadState('networkidle', { timeout: 4_000 }).catch(() => undefined);
      const hash = await page.evaluate(() => window.location.hash);
      expect(hash, `linked todo "${todo.title}" navigated away from workbench`).not.toBe('#/workbench');
      expect(hash.startsWith(String(todo.href).split('?')[0])).toBeTruthy();
      await expect(page.locator('main.focus-page')).toBeVisible();
      await expect(page.getByText('not_found')).toHaveCount(0);
    }

    // 行内待办（若有）：展开出决策面板、仍停在 #/workbench（就地办、不跳出工作台）。
    if (inline.length) {
      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, '#/workbench');
      const expander = page.locator('[data-testid="workbench-todo-expand"]').first();
      await expect(expander).toBeVisible();
      await expander.click();
      await expect(
        page.locator('[data-testid="workbench-todo-action-panel"]').first(),
      ).toBeVisible();
      const hash = await page.evaluate(() => window.location.hash);
      expect(hash, '行内待办展开不应跳出 #/workbench（就地办理契约）').toBe('#/workbench');
    }
  });

  test('待办计数与真实库积压一致（待发布目录）+ 审核类不入运营员工作台（E2）', async ({ page }) => {
    const wb = await fetchWorkbench(page, 'ROLE_BUSIAUDIT');
    test.skip(!wb, 'workbench.view unreachable');
    const todos = wb!.todos ?? [];

    const pendingPublish = await countCatalog(page, 'approved_pending_publish');
    test.skip(pendingPublish < 0, 'catalog.entry.query unreachable');

    const publishTodo = todos.find((t) => t.id === 'backlog-catalog-publish');

    // 现算口径：DB 有积压才出待办；待办标题数字 = 真实库该生命周期态计数（待发布属运营员职责）。
    if (pendingPublish > 0) {
      expect(publishTodo, '待发布目录积压>0 应有对应待办').toBeTruthy();
      expect(publishTodo!.title).toContain(String(pendingPublish));
    } else {
      expect(publishTodo, '待发布目录零积压则无对应待办（无空死链）').toBeFalsy();
    }

    // E2 职责口径：审核（目录/资源审批）属部门管理员——业务运营员工作台**绝不**出现审核类待办，
    // 无论真实库有多少待审核积压（与发布/受理/汇总职责正交，0605 反馈 6.4#11 + D53）。
    expect(
      todos.find((t) => t.id === 'backlog-catalog-review'),
      '审核类（待审核目录）不应进业务运营员工作台（E2）',
    ).toBeFalsy();
    expect(
      todos.find((t) => t.id === 'backlog-resource-review'),
      '审核类（待审核资源）不应进业务运营员工作台（E2）',
    ).toBeFalsy();
  });
});
