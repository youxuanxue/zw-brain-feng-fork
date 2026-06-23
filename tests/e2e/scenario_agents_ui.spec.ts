import { test, expect, type Page, type TestInfo } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 场景智能体浏览器 UI：【数据应用】顶级页列出 B 类应用（法人信用画像核验），
// 点开进入对话工作台并出现快捷问题；AgentRuntime 开启时再跑真实浏览器对话往返。
// A 类找数已由找数页「找数助手」承载，不再单设面板。
test.describe('场景智能体 UI：数据应用', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('数据应用页：列出 B 类应用，点开有对话框与快捷问题', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByRole('heading', { name: '数据应用' })).toBeVisible();
    // B 类应用卡片（category=data-app 由后端从 labels.surface 派生）
    await expect(page.getByRole('heading', { name: '法人信用画像核验' })).toBeVisible();
    // 点「打开」→ 进入对话工作台，出现输入框 + 快捷问题
    await page.getByRole('button', { name: '打开' }).first().click();
    await expect(page.locator('#achat-input-legal-person-credit-profiler')).toBeVisible();
    await expect(page.getByRole('button', { name: '做企业授信尽调需要看哪些数据？' })).toBeVisible();
  });

  test('数据应用页：AgentRuntime 开启时可完成真实对话往返', async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    await skipUnlessAgentRuntime(page, testInfo);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/data-apps');
    await page.getByRole('button', { name: '打开' }).first().click();

    const input = page.locator('#achat-input-legal-person-credit-profiler');
    await expect(input).toBeVisible();
    await input.fill('做企业授信尽调需要看哪些数据？');
    await page.getByRole('button', { name: '发送' }).click();

    const assistant = page.locator('.achat-msg[data-role="assistant"] .achat-msg-body').last();
    await expect(assistant).toBeVisible({ timeout: 180_000 });
    await expect(assistant).not.toContainText(
      /暂时无法回答|任务执行失败|智能问答未启用|未返回 task_id|轮询超时|HTTP 5|服务端日志/,
      { timeout: 1_000 },
    );
    await expect(assistant).not.toHaveText('（无回复内容）');
  });
});

test.describe('平台指南悬浮问答', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('平台指南：AgentRuntime 开启时可完成真实问答往返', async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    await skipUnlessAgentRuntime(page, testInfo);
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/workbench');

    await page.getByRole('button', { name: '平台指南' }).click();
    await expect(page.getByRole('dialog', { name: '平台指南问答' })).toBeVisible();

    const input = page.locator('#guide-input');
    await expect(input).toBeVisible();
    await input.fill('本地部署后如何确认智能问答已开启？');
    await page.getByRole('button', { name: '发送' }).click();

    const answer = page.locator('.guide-msg[data-role="assistant"] .guide-msg-body').last();
    await expect(answer).toBeVisible({ timeout: 180_000 });
    await expect(answer).not.toContainText(
      /暂时无法回答|任务执行失败|智能问答未启用|未返回 task_id|轮询超时|HTTP 5|AgentRuntime|服务端日志/,
      { timeout: 1_000 },
    );
    await expect(answer).not.toHaveText('（无回复内容）');
  });

  test('平台指南：后端错误不把内部运行时术语展示给客户', async ({ page }) => {
    await page.route('**/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, agent_runtime: { enabled: true } }),
      });
    });
    await page.route('**/api/agent-runtime/tasks', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'agent_runtime_unreachable', detail: 'AgentRuntime unreachable' }),
      });
    });
    await page.reload();
    await waitAppReady(page);
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/workbench');

    await page.getByRole('button', { name: '平台指南' }).click();
    await expect(page.getByRole('dialog', { name: '平台指南问答' })).toBeVisible();
    await page.locator('#guide-input').fill('本地部署后如何确认智能问答已开启？');
    await page.getByRole('button', { name: '发送' }).click();

    const answer = page.locator('.guide-msg[data-role="assistant"] .guide-msg-body').last();
    await expect(answer).toContainText('智能问答服务暂不可用');
    await expect(answer).not.toContainText(/AgentRuntime|agent_runtime/);
  });
});

async function skipUnlessAgentRuntime(page: Page, testInfo: TestInfo) {
  const resp = await page.request.get('/health').catch(() => null);
  if (!resp?.ok()) {
    test.skip(true, 'backend health unavailable');
    return;
  }
  const body = (await resp.json().catch(() => null)) as { agent_runtime?: { enabled?: boolean } } | null;
  if (!body?.agent_runtime?.enabled) {
    testInfo.annotations.push({ type: 'skip', description: 'AgentRuntime disabled in this environment' });
    test.skip(true, 'AgentRuntime disabled in this environment');
  }
}
