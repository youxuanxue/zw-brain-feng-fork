import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 场景智能体浏览器 UI：【数据应用】顶级页列出 B 类应用（法人信用画像核验），
// 点开进入对话工作台并出现快捷问题。结构性断言（页面渲染 + 可点开），不依赖 live 推理
// （对话往返由 REST 单测验证）。A 类找数已由找数页既有「智能检索」承载，不再单设面板。
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
});
