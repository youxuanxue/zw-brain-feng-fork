/**
 * F3-UI B1.1 合规与运营 — e2e 规格（PLACEHOLDER）
 * =================================================
 *
 * 状态：placeholder — zw-brain-web 当前未配置 playwright / cypress / vitest，
 * 此 .spec.ts 描述 4 panel + 调查助手 端到端预期行为，等 E5 接入 e2e harness
 * 后正式 land。Python 端单测（tests/integration/test_b11_backend.py）已覆盖
 * 后端 capability 数据流；UI 这层等 harness 就位再加运行时断言。
 *
 * 验证清单（按 supervisor F3-UI instruction「至少 4 panel 切换 + 真实数据
 * 展示 + 调查助手脱敏摘要」一一对应）：
 *
 *   1. 路由层鉴权：ROLE_ORGAN_OPERATER 访问 /compliance-ops 应被 BFF
 *      redirect 或显示"无权限"占位；ROLE_SECURITY_AUDIT / ROLE_BUSIAUDIT
 *      正常进入页面（与现有 useAuth.ts BFF 模型对齐）。
 *
 *   2. 4 panel 切换：点击 tab 顺序「统计 → 异常 → 追责 → 回放」均能渲染
 *      panel-head + panel body；activePanel state 与 aria-selected 同步。
 *      切换时 summary.reset() 触发，助手区清空。
 *
 *   3. 真实数据展示（live BFF）：当 brain 后端启动且 dev-iam-bypass 生效时，
 *      4 panel 各 source-pill 显示 "live"；fixture pill 不出现。验证 BFF
 *      链路通：curl /api/skills/audit.event.statistics 返回 200 + JSON。
 *
 *   3'. fallback 切片（dev fixture）：brain 后端不启动时，4 panel source-pill
 *      显示 "fixture"；数据来自 src/fixtures/b11-fixture.ts 同 sd-default
 *      切片（与 P1Workbench 同 pattern）。
 *
 *   4. 调查助手脱敏摘要：activePanel != replay 时点「就当前视图生成摘要」
 *      按钮，调用 /api/skills/assistant.investigation_summary 走 shared/
 *      inference/client；returned summary 包含 panel 趋势描述但**不包含**
 *      原始 actor / skill_id / request_id 字面值（后端 _sanitize_value
 *      已 hash 化）。
 *
 *   5. D14 设计意图 — 助手摘要不替代原始证据：assistant-panel 位于 4 panel
 *      之后并列展示；disclaimer 文本 "助手摘要 不替代 上方原始审计证据"
 *      可见；sha1: 字段以 <code> 形态原样呈现，不还原。
 *
 *   6. activePanel === replay 时点摘要按钮：toast 提示「回放视图不走 AI 摘要」，
 *      不发起 chat 请求。
 *
 *   7. NL 加速器：3 预设词条点击后 invokeActionStub 走 ROLE_SECURITY_AUDIT；
 *      未 land 的 skill 显示「操作待后端 land」toast 而非红色错误。
 *
 *   8. R12 工程术语黑名单（preflight 段 24 已自动兜底）：UI 文案不出现
 *      "package" / "projection" / "capability" / "write-with-audit" /
 *      "register-version" / "apply-tenant-policy" / "reconcile-receipt" /
 *      "submit-evidence" / "policy_decision" 9 词在 Chinese-rich string
 *      字面量内；段 24 扫 .html .js .css（.vue 不强扫但本预算遵守在
 *      用户面文本内）。本 e2e 不重复 preflight 校验。
 *
 *   9. R13 单租户保护：UI 调用所有 capability 均传 tenant_id="sd-default"；
 *      手动构造跨租户调用应被后端 _enforce_tenant_scope 拦下（已被
 *      tests/integration/test_b11_backend.py::test_cross_tenant_access_is_denied_across_all_b11_handlers
 *      在 Python 侧覆盖；UI 这层不必重复）。
 *
 * 测试运行约定（e2e harness 就位后）：
 *   - 优先 playwright（@playwright/test）；如选 cypress 须 update vite.config
 *     proxy 与 baseURL；fixture 切片与 BFF mock 走 playwright route()
 *   - dev 模式：npm run dev + brain server (ZW_BRAIN_DEV_IAM_BYPASS=1 python
 *     -m zw_brain.entry.rest.server) 同时跑；test 跑 npx playwright test
 *   - CI 模式：先 npm run build + serve dist-vite/，然后启动 brain，再跑
 *     playwright（与现有 pytest e2e 同 harness 风格）
 *
 * 改造日（e2e harness land 时）：把本 placeholder 的注释清单逐条转 it()
 * block；保留这份文档以备 trace。
 */

import { test, expect } from '@playwright/test';
import { gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

// Placeholder 占位 export，防止本文件作为空模块被 typecheck 报红
export const B11_E2E_PLACEHOLDER = {
  panels: ['statistics', 'anomaly', 'accountability', 'replay'] as const,
  assistantSkill: 'assistant.investigation_summary',
  backendSkills: [
    'audit.event.query',
    'audit.event.replay',
    'audit.event.statistics',
    'audit.event.anomaly',
    'audit.event.accountability',
  ] as const,
  expectedRoles: ['ROLE_SECURITY_AUDIT', 'ROLE_BUSIAUDIT'] as const,
};

test.describe('B1.1 合规与运营 smoke', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
    await setRole(page, 'ROLE_SECURITY_AUDIT');
    await gotoHash(page, '#/compliance-ops');
  });

  test('SECURITY_AUDIT 进入页面并切换 4 panel', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '合规与运营' })).toBeVisible();
    for (const label of ['统计', '异常', '追责', '回放'] as const) {
      await page.getByRole('tab', { name: label }).click();
      await expect(page.getByRole('tab', { name: label })).toHaveAttribute('aria-selected', 'true');
    }
  });

  test('OPERATER 无权静默进入合规页', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/workbench');
    await gotoHash(page, '#/compliance-ops');
    await expect.poll(() => page.url(), { timeout: 10_000 }).not.toMatch(/#\/compliance-ops/);
  });

  // #161 god's-eye 收尾：B1.1「网关运行」只读面板（消费 ops.service.report.query）。
  test('SECURITY_AUDIT 看到「网关运行」tab 并展示在线/降级/离线计数', async ({ page }) => {
    const gwTab = page.getByRole('tab', { name: '网关运行' });
    await expect(gwTab).toBeVisible();
    await gwTab.click();
    await expect(gwTab).toHaveAttribute('aria-selected', 'true');
    // 计数条（在线/降级/离线）渲染 —— live 或 fixture 回退都应呈现三类
    await expect(page.getByRole('group', { name: '网关运行状态汇总' })).toBeVisible();
  });

  // 无权限即不可见（tab 级，非路由级）：ROLE_SYSTEM 的 shell roles 含 /compliance-ops，
  // 但缺 ops.service.report.query.execute（policy.py）→ 「网关运行」tab 不渲染，
  // 而非"可见但禁用"或"可见点击 403"。
  // （原断言用 ROLE_SECURITY_ADMIN，该角色本期退役 D55/P16；改用同样在合规 shell 内、
  //  同样不持网关查询权的现行角色 ROLE_SYSTEM，负向意图不变。）
  test('ROLE_SYSTEM 进得了合规页但看不到「网关运行」tab', async ({ page }) => {
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/compliance-ops');
    await expect(page.getByRole('heading', { name: '合规与运营' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '网关运行' })).toHaveCount(0);
  });
});
