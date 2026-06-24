import { test, expect } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.describe('P3 供需对接浏览器入口', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
  });

  test('登记一条 demand 并可见阶段', async ({ page }) => {
    await gotoHash(page, '#/request-flow/supply-demand');
    await expect(page.getByRole('heading', { name: '找不到数据 · 登记需求' })).toBeVisible();
    const title = `E2E-demand-${Date.now()}`;
    await page.locator('#demand-title').fill(title);
    await page.getByRole('button', { name: '登记需求' }).click();
    await page.waitForTimeout(1200);
    await expect(page.locator('.focus-table tbody tr').first()).toBeVisible();
    await expect(page.locator('.focus-table')).toContainText('发现缺口');
  });

  test('业务运营员对接需求时检索匹配目录不再落入不可用错误', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const runTag = Date.now().toString(36);
    const title = `E2E 供需对接检索-${runTag}`;
    const hint = '低保对象';
    try {
      const created = await api.post(`${E2E_BASE_URL}/api/skills/demand.register`, {
        data: {
          role: 'ROLE_ORGAN_OPERATER',
          confirmed: true,
          title,
          target_resource_hint: hint,
          applicant_dept: 'E2E 申请部门',
        },
      });
      expect(created.ok(), await created.text()).toBeTruthy();
      const createdBody = (await created.json()) as { id?: string; result?: { id?: string } };
      const demandId = createdBody.id ?? createdBody.result?.id ?? '';
      expect(demandId).toBeTruthy();
      const advanced = await api.post(`${E2E_BASE_URL}/api/skills/demand.phase.advance`, {
        data: {
          role: 'ROLE_BUSIAUDIT',
          confirmed: true,
          demand_id: demandId,
          next_phase: 'registered',
        },
      });
      expect(advanced.ok(), await advanced.text()).toBeTruthy();
    } finally {
      await api.dispose();
    }

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider/inbox/demand-match');
    const row = page.locator('.focus-table tbody tr', { hasText: title });
    await expect(row).toHaveCount(1, { timeout: 15_000 });

    await row.getByRole('link', { name: '对接' }).click();
    await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 15_000 });

    await Promise.all([
      page.waitForResponse((resp) =>
        resp.url().includes('/api/skills/catalog.entry.query') &&
        resp.request().method() === 'POST',
      ),
      page.getByRole('button', { name: '检索匹配目录' }).click(),
    ]);
    await expect(page.locator('.toast-stack')).toContainText(/已匹配目录|未命中/);
    await expect(page.locator('.toast-stack')).not.toContainText('目录检索暂不可用');
  });
});
