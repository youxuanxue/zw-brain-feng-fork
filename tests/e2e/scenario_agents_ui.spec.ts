import { test, expect, type Page, type TestInfo } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 场景智能体浏览器 UI：【智能体】顶级页按岗位展示可使用的助手；
// 业务用户只看到可达可用的助手，平台运维员可查看全部状态并处理启停/授权。
test.describe('场景智能体 UI：智能体', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('智能体页：服务可用时区分 A 类和 B 类，点开有对话框与快捷问题', async ({ page }) => {
    await mockAgentRuntimeEnabled(page);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByRole('heading', { name: '智能体', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: /A 类办事助手/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: '数据发现副驾' })).toBeVisible();
    await expect(page.getByText('可直接使用')).toHaveCount(0);

    await page.getByRole('tab', { name: /B 类用数助手/ }).click();
    await expect(page.getByRole('heading', { name: '法人信用画像核验' })).toBeVisible();
    await openAgentCard(page, '法人信用画像核验');
    await expect(page.locator('#achat-input-b-legal-person-credit-profiler')).toBeVisible();
    await expect(page.getByRole('button', { name: '这个助手适合帮授权用数方信用尽调人员处理什么问题？' })).toBeVisible();
  });

  test('智能体页：服务不可用时业务用户看不到不可达助手', async ({ page }) => {
    await mockAgentRuntimeDisabled(page);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByRole('heading', { name: '智能体', exact: true })).toBeVisible();
    await page.getByRole('tab', { name: /B 类用数助手/ }).click();
    await expect(page.getByRole('heading', { name: '法人信用画像核验' })).toHaveCount(0);
    await expect(page.locator('#achat-input-b-legal-person-credit-profiler')).toHaveCount(0);
  });

  test('智能体页：平台运维员可查看全部智能体和状态', async ({ page }) => {
    await mockAgentRuntimeDisabled(page);
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByText('平台运维员可查看全部智能体，处理启停、授权和重载。')).toBeVisible();
    await expect(page.getByRole('button', { name: '重载' })).toBeVisible();
    await expect(page.getByRole('button', { name: '运行体检' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '平台指南' })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: /A 类办事助手/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: '数据发现副驾' })).toBeVisible();

    await page.getByRole('tab', { name: /B 类用数助手/ }).click();
    const card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: '法人信用画像核验' }) });
    await expect(card).toBeVisible();
    await expect(card.locator('.agent-chip', { hasText: '服务未启动' })).toBeVisible();
    await expect(card.getByRole('button', { name: '服务未启动' })).toBeDisabled();
    await expect(card.getByText('授权', { exact: true })).toBeVisible();
    await expect(card.getByRole('button', { name: '调整授权' })).toBeVisible();
  });

  test('智能体页：无授权助手对业务不可见但平台运维员可见', async ({ page }) => {
    await mockAgentRuntimeEnabled(page);
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByRole('heading', { name: '权限合规自查副驾' })).toHaveCount(0);

    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/data-apps');
    await expect(page.getByRole('heading', { name: '权限合规自查副驾' })).toBeVisible();
    const card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: '权限合规自查副驾' }) });
    await expect(card.locator('.agent-chip', { hasText: '运行正常' })).toBeVisible();
    await expect(card.getByText('未授权岗位')).toBeVisible();
    await card.getByRole('button', { name: '调整授权' }).click();
    await expect(card.getByLabel('部门操作员')).toBeVisible();
    await expect(card.getByLabel('部门管理员')).toBeVisible();
    await expect(card.getByLabel('业务运营员')).toBeVisible();
    await expect(card.getByLabel('安全审计员')).toBeVisible();
    await expect(card.getByRole('button', { name: '打开' })).toBeEnabled();
  });

  test('智能体页：AgentRuntime 开启时可完成真实对话往返', async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    await skipUnlessAgentRuntime(page, testInfo);
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/data-apps');
    await page.getByRole('tab', { name: /B 类用数助手/ }).click();
    await openAgentCard(page, '法人信用画像核验');

    const input = page.locator('#achat-input-b-legal-person-credit-profiler');
    await expect(input).toBeVisible();
    await input.fill('做企业授信尽调需要看哪些数据？');
    await page.getByRole('button', { name: '发送' }).click();

    const assistant = page.locator('.achat-msg[data-role="assistant"] .achat-msg-body').last();
    await expect(assistant).toBeVisible({ timeout: 180_000 });
    await expect(assistant).not.toContainText(
      /暂时无法回答|任务执行失败|智能问答未启用|未返回 task_id|轮询超时|HTTP 5|服务端日志|本地调试回答/,
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
      /暂时无法回答|任务执行失败|智能问答未启用|未返回 task_id|轮询超时|HTTP 5|AgentRuntime|服务端日志|本地调试回答/,
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
    await expect(answer).toContainText('当前助手暂不可用');
    await expect(answer).not.toContainText(/AgentRuntime|agent_runtime/);
  });
});

async function skipUnlessAgentRuntime(page: Page, testInfo: TestInfo) {
  const resp = await page.request.get('/health').catch(() => null);
  if (!resp?.ok()) {
    test.skip(true, 'backend health unavailable');
    return;
  }
  const body = (await resp.json().catch(() => null)) as { agent_runtime?: { enabled?: boolean; ready?: boolean; status?: string } } | null;
  if (!body?.agent_runtime?.enabled || (body.agent_runtime.ready === false && body.agent_runtime.status !== 'running')) {
    testInfo.annotations.push({ type: 'skip', description: 'AgentRuntime disabled in this environment' });
    test.skip(true, 'AgentRuntime disabled in this environment');
  }
}

async function mockAgentRuntimeEnabled(page: Page) {
  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, agent_runtime: { enabled: true, ready: true, status: 'running' } }),
    });
  });
}

async function mockAgentRuntimeDisabled(page: Page) {
  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, agent_runtime: { enabled: false, ready: false, status: 'disabled' } }),
    });
  });
}

async function openAgentCard(page: Page, agentName: string) {
  const card = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: agentName }) });
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: '打开' }).click();
}
