import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.beforeEach(async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);
  await page.goto('/');
  await waitAppReady(page);
});

test('P5 API 服务化向导可达', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/wizard/api-service');
  await expect(page.getByRole('heading', { name: 'API 服务化向导' })).toBeVisible();
});

test('P5 挂接审核收件箱有 live 待办', async ({ page }) => {
  // pageAccess.ts ROUTE_ROLE_OVERRIDES: /provider/inbox/hookup-review 仅 BUSIAUDIT；
  // MANAGER 进会被路由守卫重定向，故收件箱页测试必须以 BUSIAUDIT 起。
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/provider/inbox/hookup-review');
  await expect(page.getByRole('heading', { name: '挂接审核收件箱' })).toBeVisible();
  await expect(page.locator('.focus-table tbody tr').first()).toBeVisible();
});

test('P5 供需对接列表可点进详情', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_MANAGER');
  await gotoHash(page, '#/provider/inbox/demand-match');
  await expect(page.getByRole('heading', { name: '供需对接收件箱' })).toBeVisible();
  await page.locator('.row-link').first().click();
  await expect(page.locator('.focus-detail')).toBeVisible();
});

test('B1.2 外部系统模块可达（ROLE_BUSIAUDIT）', async ({ page }) => {
  await setRole(page, 'ROLE_BUSIAUDIT');
  await gotoHash(page, '#/integration-admin');
  await expect(page.getByRole('heading', { name: '外部系统', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '已接入的外部系统' })).toBeVisible();
});
