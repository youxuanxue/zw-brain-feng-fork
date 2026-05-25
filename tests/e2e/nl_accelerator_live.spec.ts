import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

test.beforeEach(async ({ page }, testInfo) => {
  await skipUnlessBackend(page, testInfo);
  await page.goto('/');
  await waitAppReady(page);
});

test('P2 NL 加速器走 live skill 解析', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/discovery');
  await page.getByRole('button', { name: '自然语言加速器' }).click();
  await page.getByRole('button', { name: '查省营商环境相关数据' }).click();
  await expect(page.locator('.nl-tag-ok')).toContainText('真实后端');
  await expect(page.locator('.nl-summary')).not.toBeEmpty();
});

test('P3 NL 加速器待审计数 live 解析', async ({ page }) => {
  await setRole(page, 'ROLE_ORGAN_OPERATER');
  await gotoHash(page, '#/request-flow');
  await page.getByRole('button', { name: '自然语言加速器' }).click();
  await page.getByRole('button', { name: '我待审的有几条' }).click();
  await expect(page.locator('.nl-tag-ok')).toContainText('真实后端');
  await expect(page.locator('.nl-summary')).toContainText('在途');
});
