import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

/** 6 worker 主路径页面：不得出现「功能建设中」占位。 */
const PAGE_MATRIX: Array<{ role: string; hash: string; heading: RegExp | string }> = [
  // 问候语随 R-004 修复改真实会话身份现算（display_name + 时段问候；dev-bypass=「本地调试」），
  // 三时段全覆盖，不再钉死 seed 虚构人物的「上午好」二段。
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/workbench', heading: /上午好|下午好|晚上好/ },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery', heading: '可申请资源' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery/catalog-browse', heading: '目录浏览' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow', heading: '办共享申请' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/objection', heading: '我的异议' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/supply-demand', heading: '找不到数据 · 登记需求' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/delivery-exchange', heading: '交付任务' },
  // #/zones-pack（专题包页）随专题包整面退出本期而下线（D55/P6，F0-B）：路由/导航已删，
  // 此处同步移除矩阵行，避免导航到已删路由触发 dead-link 失败（本 feature 即「不留 dead link」）。
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider', heading: '提供方管理' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/wizard/reverse-catalog', heading: '反向编目向导' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/inbox/objection', heading: '异议响应收件箱' },
  { role: 'ROLE_SECURITY_AUDIT', hash: '#/compliance-ops', heading: '合规与运营' },
  // 外部系统 / 流程与表单配置随 Wave1 收口归平台运维员独有（D55/P2·P3：业务运营员退外部系统、
  // 流程表单配置反转 D49 收平台运维员）；矩阵行同步把驱动角色从 BUSIAUDIT 改 SYSTEM，
  // 既修因导航收权产生的 dead-link 失败，也补上运维员后台页面的主路径渲染覆盖。
  { role: 'ROLE_SYSTEM', hash: '#/integration-admin', heading: /^外部系统$/ },
  { role: 'ROLE_SYSTEM', hash: '#/integration-admin/engines', heading: '流程与表单配置' },
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
