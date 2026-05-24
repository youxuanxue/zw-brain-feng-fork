/**
 * F5 B1.2 接入扩展中心 — e2e 规格（PLACEHOLDER）
 * =================================================
 *
 * 状态：placeholder — zw-brain-web 当前未配置 playwright / cypress / vitest，
 * 此 .spec.ts 描述 3 tab + 写操作二次确认 + 信任级双层语义边界 + 三引擎 slot
 * 跳转的端到端预期行为，等 E5 接入 e2e harness 后正式 land。Python 端集成测试
 * （tests/integration/test_b12_intake.py，PR #91 commit 385332f 已 land main）
 * 已覆盖 capability.package.* 后端数据流；UI 这层等 harness 就位再加运行时
 * 断言。
 *
 * 验证清单（按 supervisor F5 instruction 一一对应）：
 *
 *   1. 路由层鉴权：ROLE_ORGAN_OPERATER 访问 /integration-admin 应被 BFF
 *      redirect 或显示「无权限」占位；ROLE_SECURITY_ADMIN / ROLE_BUSIAUDIT
 *      正常进入（与 useAuth.ts BFF 模型一致；后端 policy.py
 *      package.* 权限已限）。
 *
 *   2. 3 tab 切换：点击 tab 顺序「能力包注册 → 暴露范围矩阵 → 三引擎入口」
 *      均能渲染 panel-head + panel body；activeTab 与 aria-selected 同步。
 *
 *   3. 真实数据展示（live BFF）：当 brain 后端启动且 dev-iam-bypass 生效，
 *      packages tab 调 /api/skills/package.list 返回；matrix tab 调
 *      /api/skills/package.exposure.matrix.query 返回；source pill 显示
 *      "live"。
 *
 *   3'. fallback 切片（dev fixture）：brain 后端不启动时，packages + matrix
 *      tabs source pill 显示 "fixture"；数据来自 src/fixtures/b12-fixture.ts
 *      （PACKAGE_LIST_FIXTURE + EXPOSURE_MATRIX_FIXTURE）。
 *
 *   4. 信任级双层语义边界 disclaimer：能力包注册 tab 顶部固定显示
 *      「信任级 trust_level 是 本平台对能力包的信任评估（业务字段，4 档：
 *      基线 / 已审 / 严管 / 撤回）。与 AgentRuntime 外部 Agent 来源信任级
 *      （3 档：platform / verified / untrusted，AgentRuntime 触发后落地）
 *      不是同一字段」；不出现把两者混淆的文案。
 *
 *   5. 写操作 human_confirmation_required 二次确认：审核 / 启用 / 停用 /
 *      回滚 / 信任级升降 5 类按钮触发后必须先弹 window.confirm() 二次
 *      确认；用户取消则不调后端。回滚额外要求 window.prompt() 输入原因；
 *      信任级升降要求输入目标级别 + 原因，三档校验非法值。
 *
 *   6. 元审计 request_id 透传：UI 每次调 capability 时生成 UI-PKG-* 前缀
 *      request_id（newRequestId in usePackageLifecycle.ts）传给后端，
 *      后端元审计能 correlate（与 audit.event.query / replay 同 pattern）。
 *
 *   7. 状态机按钮 disabled 兜底：active 状态的能力包「批准」disabled；
 *      非 pending 状态「退回」disabled；非 approved/rolled-back「启用」
 *      disabled；非 active「停用」disabled；无 rollback_target「回滚」
 *      disabled——与后端 InvalidStateError 防御一致。
 *
 *   8. 矩阵筛选：暴露范围矩阵 tab 的 journey / status 下拉切换触发重新调
 *      package.exposure.matrix.query；后端 totals 同步更新。
 *
 *   9. 三引擎 slot 跳转：三引擎入口 tab 显示 3 张 slot 卡片（审批流 / 表单 /
 *      推荐），每张可点击跳转 #/engines-admin（E3 PR #92 B13EnginesAdmin.vue
 *      已 land）；slot status 全部 "可用"（status === 'available'）。B1.2
 *      不重实装三引擎业务逻辑——与 E3 的协作约定（useEngineSlots.ts 是
 *      contract）。
 *
 *  10. R12 工程术语黑名单（preflight 段 24）：UI 用户面文本不出现
 *      "package" / "projection" / "capability" 等 9 词在 Chinese-rich
 *      string 内；B1.2 例外允许「能力包」（架构 §5.5 已合规）。
 *
 *  11. R13 单租户保护：所有 capability 调用硬编码 tenant_id="sd-default"；
 *      跨租户防御已在后端 _enforce_tenant_scope（PR #91 land），UI 这层
 *      不必重复。
 *
 *  12. AgentRuntime Registry 4 字段尚未泄漏：本 UI 不显示 runtime_spec_version
 *      / agent_yaml_ref / workspace_required 这 3 个 AgentRuntime 字段；
 *      Registry trust_level（platform/verified/untrusted）仅在 disclaimer
 *      文本中作 contrast 解释，不显示在能力包列表表头。F6 触发后另开 PR
 *      land Registry 字段时再升级 UI。
 *
 * 测试运行约定（e2e harness 就位后）：
 *   - 优先 playwright（与 F3-UI b11_compliance.spec.ts 同 harness 决策）
 *   - dev 模式：npm run dev + ZW_BRAIN_DEV_IAM_BYPASS=1 python -m
 *     zw_brain.entry.rest.server 同时跑；test 跑 npx playwright test
 *   - confirm/prompt mock：playwright page.on('dialog') 自动 accept；
 *     verify backend invoke 序列符合预期
 *
 * 改造日（e2e harness land 时）：把本 placeholder 12 条逐条转 it() block；
 * 保留本文档作 trace。
 */

export const B12_E2E_PLACEHOLDER = {
  tabs: ['packages', 'matrix', 'engines'] as const,
  packageActions: [
    'package.review_decide',
    'tenant.capability.enable',
    'tenant.capability.disable',
    'package.rollback',
    'package.trust_level.update',
  ] as const,
  readSkills: ['package.list', 'package.exposure.matrix.query'] as const,
  engineSlots: ['approval_flow', 'form_schema', 'recommendation'] as const,
  expectedRoles: ['ROLE_SECURITY_ADMIN', 'ROLE_BUSIAUDIT'] as const,
  trustLevelsBusinessSide: ['baseline', 'reviewed', 'restricted', 'revoked'] as const,
  trustLevelsAgentRuntimeRegistry: ['platform', 'verified', 'untrusted'] as const,
};
