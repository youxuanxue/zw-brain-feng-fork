import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// D45 全局数据缺位修复 — J1 列表字段全量真实库投影 + 发现页可用过滤 + 卡片信息密度。
// 验收：① 发现页只展示「可用」资源（多列密排 + 类型徽标 + 共享类型色 chip）；
//       ② P3 在途申请 / 待我审批 展现全量真实库（非 seed 5 条）。
test.describe('J1 数据缺位修复（D45）', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.setViewportSize({ width: 1440, height: 1024 });
    await page.goto('/');
    await waitAppReady(page);
  });

  test('资源发现：只展示可用资源 + 多列密排 + 类型徽标 + 共享类型色 chip', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(1500);

    // 全量真实库（远超 seed 12）；卡片数 = 命中数。
    const cards = page.locator('.card-grid .res-card');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
    expect(await cards.count(), '可用资源应全量展现（非 seed 精选）').toBeGreaterThan(40);

    // 多列密排（非单列满宽）。
    const cols = await page.evaluate(() => {
      const g = document.querySelector('.card-grid');
      return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0;
    });
    expect(cols, '卡片应多列密排').toBeGreaterThan(1);

    // 类型徽标（库表/文件/接口…）齐全。
    expect(await page.locator('.res-kind').count(), '每卡应有物化形态徽标').toBeGreaterThan(40);

    // 共享类型决策 chip：无条件(绿) + 有条件(琥珀) 都存在。
    expect(await page.locator('.res-share--open').count(), '应有无条件共享 chip').toBeGreaterThan(0);
    expect(await page.locator('.res-share--conditional').count(), '应有有条件共享 chip').toBeGreaterThan(0);

    // 发现页只展示「可用」态：状态标签不含草稿/已下线/已过期等非可用态。
    const statuses = new Set(await page.locator('.res-status').allInnerTexts());
    for (const bad of ['草稿', '已下线', '已过期', '已暂停', '审核中']) {
      expect(statuses.has(bad), `默认视图不应含非可用态「${bad}」`).toBeFalsy();
    }
  });

  test('P3 在途申请：展现全量真实申请（非 seed 5 条）', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/request-flow');
    await page.waitForTimeout(1500);
    const rows = page.locator('.focus-table tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    expect(await rows.count(), '在途申请应全量真实（远超 seed 5）').toBeGreaterThan(40);
    // 每行有资源名（申请类，非需求噪声）。
    await expect(rows.first()).not.toBeEmpty();
  });

  test('P3 待我审批：审批角色见全量真实待审', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/request-flow');
    await page.waitForTimeout(1500);
    const rows = page.locator('.focus-table tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    expect(await rows.count(), '待我审批应全量真实（远超 seed 5）').toBeGreaterThan(10);
  });
});
