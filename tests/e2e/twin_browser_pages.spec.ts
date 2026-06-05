import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

/** 6 worker 主路径页面：不得出现「功能建设中」占位。 */
const PAGE_MATRIX: Array<{ role: string; hash: string; heading: RegExp | string }> = [
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/workbench', heading: /工作台|上午好|下午好/ },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery', heading: '可复用资源' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery/catalog-browse', heading: '目录浏览' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow', heading: '办共享申请' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/objection', heading: '我的异议' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/supply-demand', heading: '找不到数据 · 登记需求' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/delivery-exchange', heading: '交付任务' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/zones-pack', heading: /共享专区|专题包/ },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider', heading: '提供方管理' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/wizard/reverse-catalog', heading: '反向编目向导' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/inbox/objection', heading: '异议响应收件箱' },
  { role: 'ROLE_SECURITY_AUDIT', hash: '#/compliance-ops', heading: '合规与运营' },
  { role: 'ROLE_BUSIAUDIT', hash: '#/integration-admin', heading: /^外部系统$/ },
  { role: 'ROLE_BUSIAUDIT', hash: '#/integration-admin/engines', heading: '流程与表单配置' },
];

test.describe('Twin 主路径页面无占位', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  for (const row of PAGE_MATRIX) {
    test(`${row.role} ${row.hash}`, async ({ page }) => {
      await setRole(page, row.role);
      await gotoHash(page, row.hash);
      await expect(page.getByText('功能建设中')).toHaveCount(0);
      await expect(page.getByRole('heading', { name: row.heading })).toBeVisible();
    });
  }
});
