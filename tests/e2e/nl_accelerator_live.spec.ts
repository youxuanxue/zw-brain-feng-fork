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
  await page.getByRole('button', { name: '找数助手' }).click();
  await page.getByRole('button', { name: '查省营商环境相关数据' }).click();
  await expect(page.locator('.nl-tag-ok')).toContainText('真实后端', { timeout: 30_000 });
  await expect(page.locator('.nl-summary')).not.toBeEmpty();
});

test('P3 NL 加速器待审计数 live 解析', async ({ page }) => {
  // IA 重构（拆「办申请」）：P3「办共享申请」NL 加速器面板随 P3RequestFlow.vue 列表页退役，本期无新前端宿主
  //（领数据 #/delivery-exchange 不挂 NL 面板；NL live 解析仍由 P2 发现页用例 + nlAcceleratorRouting.ts
  // 的 P3 分支单测覆盖）。故此 P3 NL UI 走查暂无可点击的真实面，honest skip（不假装）。
  void page;
  test.skip(true, 'P3 NL 加速器面板随拆「办申请」退役、无新前端宿主（IA 重构）；待重新归家后恢复');
});
