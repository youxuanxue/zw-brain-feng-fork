import { test, expect } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// 漏扫 0609 Layer 1：在**真实浏览器**里确认严格 CSP + 安全响应头不破坏 SPA。
// 关键点：若 `script-src 'self'` 挡住了打包后的 module 脚本，SPA 根本无法挂载，
// waitAppReady 会超时——所以"应用挂载成功"本身就是 CSP 放行脚本的实证。

test('严格 CSP 下 SPA 正常挂载、无 CSP 违规、XHR/路由可用', async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);

  const cspViolations: string[] = [];
  page.on('console', (msg) => {
    const t = msg.text();
    if (/content security policy|refused to (load|execute|connect|apply)/i.test(t)) {
      cspViolations.push(t);
    }
  });
  page.on('pageerror', (err) => {
    if (/content security policy/i.test(err.message)) cspViolations.push(err.message);
  });

  await page.goto('/');
  // 应用挂载 = 打包 module 脚本在 script-src 'self' 下成功加载执行。
  await waitAppReady(page);

  // 角色切换 + 路由跳转 = connect-src 'self' 的 XHR 与渲染在 CSP 下工作。
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/workbench');
  await expect(page.locator('#app').locator('*').first()).toBeVisible();

  expect(cspViolations, `CSP 违规：\n${cspViolations.join('\n')}`).toEqual([]);
});

test('文档响应携带安全头且 Server banner 去版本化', async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);
  const resp = await page.request.get(`${E2E_BASE_URL}/`);
  expect(resp.ok()).toBeTruthy();
  const h = resp.headers();
  // banner 不泄漏 Python 版本
  expect(h['server']).toBe('zw-brain');
  // 安全头齐全
  expect(h['content-security-policy']).toContain("script-src 'self'");
  expect(h['x-frame-options']).toBe('DENY');
  expect(h['x-content-type-options']).toBe('nosniff');
  expect(h['referrer-policy']).toBeTruthy();
  expect(h['permissions-policy']).toBeTruthy();
});
