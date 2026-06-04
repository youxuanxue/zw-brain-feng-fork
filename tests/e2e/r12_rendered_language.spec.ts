import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';
import { scanForbidden } from './r12-forbidden-patterns';

/**
 * R12 渲染层语言守卫（用户语言层架构核心）。
 *
 * 反馈实锤：动态数据走数据通道把工程语言（能力 id / 渠道 token / ISO 时间 /
 * 裸 hex 标题 / HTTP 状态码 / 黑名单词）直出到了渲染后的 UI，绕过了只扫源码
 * 的静态守卫段 24。本 spec 登录后遍历全部场景页，对每页渲染后的可见文本
 * 断言禁用模式（单源 r12-forbidden-patterns.ts）零命中。
 *
 * 这是真 UI 渲染断言（经 Playwright 真实 DOM innerText），不是源码扫描。
 * 本 spec 不 back 任何 .feature（# Pytest 边），不触发 D46.g 测量重采。
 */

// 全部场景页 × 有权角色。覆盖反馈点中泄漏过的页：工作台（待办/办理建议/亮点）、
// 交付任务（渠道/时间/hex）、在途申请（hex/时间）、专题包（projection 占位）、
// 资源详情（HTTP 404）、目录浏览（裸编码标题）。
const PAGE_MATRIX: Array<{ role: string; hash: string; note: string }> = [
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/workbench', note: '工作台待办/办理建议/本周亮点' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery', note: '资源发现' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery/catalog-browse', note: '目录浏览（待发布标题）' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow', note: '在途申请（编号/提交时间）' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/objection', note: '我的异议' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/supply-demand', note: '登记需求' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/delivery-exchange', note: '交付任务（渠道/更新/名称）' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/zones-pack', note: '专题包（描述占位）' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider', note: '提供方管理' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/inbox/objection', note: '异议响应收件箱' },
  { role: 'ROLE_BUSIAUDIT', hash: '#/provider/inbox/field-decision', note: '字段审核收件箱（原字段裁决）' },
  { role: 'ROLE_SECURITY_AUDIT', hash: '#/compliance-ops', note: '合规与运营' },
  { role: 'ROLE_BUSIAUDIT', hash: '#/integration-admin', note: '接入扩展中心' },
];

test.describe('R12 渲染层无工程语言泄漏', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  for (const row of PAGE_MATRIX) {
    test(`${row.role} ${row.hash} — ${row.note}`, async ({ page }) => {
      await setRole(page, row.role);
      await gotoHash(page, row.hash);
      // 让列表 / 详情数据 settle（gotoHash 已 networkidle 兜底，这里再给一拍）。
      await page.waitForTimeout(600);

      // 只扫主内容区可见文本（不含导航 chrome 之外的脚本/属性）。
      const region = page.locator('#app-router');
      const text = (await region.innerText().catch(() => '')) || '';
      const hits = scanForbidden(text);

      if (hits.length) {
        const report = hits
          .map((h) => `  · [${h.patternId}] ${h.label} → "${h.sample}"`)
          .join('\n');
        // eslint-disable-next-line no-console
        console.error(`R12 泄漏 @ ${row.hash} (${row.role}):\n${report}`);
      }
      expect(
        hits,
        `渲染层工程语言泄漏 @ ${row.hash}：\n${hits
          .map((h) => `[${h.patternId}] ${h.sample}`)
          .join('; ')}`,
      ).toEqual([]);
    });
  }
});
