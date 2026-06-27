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
// exempt：该页内「合法保留工程原文」的 region 选择器（其 innerText 在扫描前剔除）。
// 唯一用例 = B11 合规面审计取证原文块（见下方 R12 取证豁免说明）。
// tabs：本页是 v-show 多 tab 面（如 B11 合规面的 统计/异常/追责/回放），默认面之外的 tab
// DOM 被 v-show 隐藏、innerText 取不到 → 静态单扫只覆盖默认面（盲区①）。置 true 时扫描循环
// 逐个点 nav.focus-tabs 的 role="tab" 按钮，把每个 tab 渲染后的文本累加进扫描文本。
const PAGE_MATRIX: Array<{ role: string; hash: string; note: string; exempt?: string[]; tabs?: boolean }> = [
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/workbench', note: '工作台待办/办理建议/本周亮点' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery', note: '资源发现' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/discovery/catalog-browse', note: '目录浏览（待发布标题）' },
  // 办申请已拆解归并领数据：列表根 #/request-flow 重定向 /delivery-exchange（操作员默认落「我的申请」tab），
  // 与下方 #/delivery-exchange 行同页，去重移除；异议/登记需求子路由保留（仍独立可达）。
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/objection', note: '我的异议' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/request-flow/supply-demand', note: '登记需求' },
  { role: 'ROLE_ORGAN_OPERATER', hash: '#/delivery-exchange', note: '领数据：我的申请进度/授权/交付任务' },
  // #/zones-pack 专题包整面退出本期（D55/P6，#235）：路由已下线，移除死链行避免导航到已删路由。
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider', note: '供数据' },
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/inbox/objection', note: '异议响应收件箱' },
  // D57⑧：反向编目审核（部门审）归部门管理员；扫描随角色门同步，否则路由守卫弹走、扫的是别页。
  { role: 'ROLE_ORGAN_MANAGER', hash: '#/provider/inbox/field-decision', note: '反向编目审核收件箱（原字段审核/字段裁决）' },
  // 合规面：审计取证原文 <pre> 块（脱敏 payload / 回放 payload）按负责人批准的
  // 「R12 取证豁免」显式 scope 排除——这些是回放/追责的合法取证视图，须按原文保留
  // snake_case 键（如 legacy_role_ref / role_lacks_permission），不 label 化、不还原。
  // 其余 status-pill 类枚举（audit_class/dimension/phase/rule）与点分 skill_id 仍受 R12 管，
  // 已在 B11ComplianceOps.vue 经 auditDisplay 中文化 / 隐 id 到 title。
  // tabs:true → 遍历 统计/异常/追责/回放 四个 v-show tab 后再扫（堵盲区①：回放/追责面
  // 的裸 ISO 时间戳 occurred_at/denied_at 此前藏在隐藏 DOM 里逃过单扫）。
  {
    role: 'ROLE_SECURITY_AUDIT',
    hash: '#/compliance-ops',
    note: '合规与运营（统计/异常/追责/回放四 tab）',
    exempt: ['#app-router pre.sanitized', '#app-router pre.replay-payload'],
    tabs: true,
  },
  // D55/P2：外部系统归平台运维员独有（业务运营员退出）。
  { role: 'ROLE_SYSTEM', hash: '#/integration-admin', note: '外部系统' },
  // B1.3 服务调用监控整页（堵盲区②：#/service-ops 此前不在 PAGE_MATRIX，整页裸 ISO
  // 时间戳 last_reported_at 无人扫）。role 取 ROLE_SYSTEM（平台运维员）——productShellNav
  // service-ops.roles = ['ROLE_BUSIAUDIT','ROLE_SYSTEM']，且无 ROUTE_ROLE_OVERRIDE 覆盖，
  // 故平台运维员可达本页（与上方 ROLE_SYSTEM #/integration-admin 行同源角色门）。
  { role: 'ROLE_SYSTEM', hash: '#/service-ops', note: '服务调用监控' },
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
      let text = (await region.innerText().catch(() => '')) || '';
      // 取证豁免块文本须在「其所在 tab 可见时」抓取——v-show 隐藏面的 allInnerTexts() 返回空，
      // 故 exempt 文本随各 tab 累加收集，最后统一剔除（否则隐藏 tab 的取证 <pre> 漏剔 → 误命中）。
      const exemptTexts: string[] = [];
      const collectExempt = async (): Promise<void> => {
        for (const sel of row.exempt ?? []) {
          const blocks = await page.locator(sel).allInnerTexts().catch(() => [] as string[]);
          for (const b of blocks) if (b) exemptTexts.push(b);
        }
      };
      await collectExempt();

      // 盲区①：v-show 多 tab 面（B11 统计/异常/追责/回放）默认面之外的 DOM 隐藏，
      // innerText 取不到 → 逐个点 tab 让其渲染后把文本（及其 exempt 取证块）累加。
      if (row.tabs) {
        const tabBtns = page.locator('#app-router nav.focus-tabs button[role="tab"]');
        const tabCount = await tabBtns.count().catch(() => 0);
        for (let t = 0; t < tabCount; t += 1) {
          await tabBtns.nth(t).click().catch(() => undefined);
          await page.waitForTimeout(400); // 让该 tab 的 v-show 面渲染 + 数据 settle 一拍
          const tabText = (await region.innerText().catch(() => '')) || '';
          text = `${text}\n${tabText}`;
          await collectExempt(); // 该 tab 可见时收集其取证 <pre> 原文（隐藏后取不到）
        }
      }
      // R12 取证豁免：把显式登记的 exempt region（审计取证 <pre> 原文块）的文本
      // 从扫描文本里剔除——这些工程原文按负责人批准合法保留，不应触发渲染层守卫。
      for (const b of exemptTexts) {
        if (b) text = text.split(b).join(' ');
      }
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

  // 资源详情页（#/discovery/resource/:id）：资源 id 运行时来自真实库（seed-light 空库无资源），
  // 故经发现页「查看详情」入口动态进入；无资源时 skip（诚实，同 dump-依赖 spec 的留本地纪律）。
  // 守 A2 细条状态映射（状态 draft 等 lifecycle 不得裸出，formatResourceStatus）+ 分型块语言层。
  test('ROLE_ORGAN_OPERATER 资源详情页 — 渲染层无工程语言泄漏', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/discovery');
    await page.waitForTimeout(800);
    const detailLink = page.locator('a[href^="#/discovery/resource/"]').first();
    if ((await detailLink.count()) === 0) {
      test.skip(true, 'seed-light 空库无可申请资源 → 无资源详情可巡检（需真实库副本）');
      return;
    }
    await detailLink.click();
    await page.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => undefined);
    await page.waitForTimeout(1200); // 等 catalog.resource_view 富集覆盖快照（draft/active 等原始态）

    const text = (await page.locator('#app-router').innerText().catch(() => '')) || '';
    const hits = scanForbidden(text);
    if (hits.length) {
      // eslint-disable-next-line no-console
      console.error(`R12 泄漏 @ 资源详情:\n${hits.map((h) => `  · [${h.patternId}] "${h.sample}"`).join('\n')}`);
    }
    expect(
      hits,
      `资源详情渲染层工程语言泄漏：\n${hits.map((h) => `[${h.patternId}] ${h.sample}`).join('; ')}`,
    ).toEqual([]);
  });
});
