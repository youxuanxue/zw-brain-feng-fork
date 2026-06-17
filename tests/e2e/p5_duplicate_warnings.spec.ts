import { test, expect } from '@playwright/test';
import { ensurePublishQueue, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 发布动作已统一收口工作台行内办理（供数据页旧发布队列退役）。本用例验后端契约：
// catalog.entry.publish 响应含 duplicate_warnings 字段（不论由哪个 UI 触发，重复率由后端现算）。
test.describe('工作台发布重复率提醒', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    const ready = await ensurePublishQueue(page);
    if (!ready) testInfo.skip(true, 'cannot seed approved_pending_publish queue');
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/workbench');
  });

  test('catalog.entry.publish 响应含 duplicate_warnings 字段', async ({ page }) => {
    const todo = page.getByTestId('workbench-todo').filter({ hasText: '待发布目录' });
    await expect(todo).toHaveCount(1, { timeout: 15_000 });
    await todo.getByTestId('workbench-todo-expand').click();
    const publishBtn = page
      .getByTestId('workbench-decision-item')
      .first()
      .getByTestId('workbench-todo-decision')
      .filter({ hasText: '发布' })
      .first();
    await expect(publishBtn).toBeVisible({ timeout: 15_000 });
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/skills/catalog.entry.publish') && r.ok(),
    );
    await publishBtn.click();
    const resp = await respPromise;
    const body = (await resp.json()) as Record<string, unknown>;
    const inner = (body.result ?? body) as Record<string, unknown>;
    expect(Array.isArray(inner.duplicate_warnings)).toBe(true);
  });
});
