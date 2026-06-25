/**
 * 页面访问 SoT：与 config/productShellNav.ts 的 shell key / roles 对齐。
 * 后端快照裁剪见 zw_brain/domain/web_snapshot_redaction.py（须同步改 roles 集合）。
 *
 * 两级权限：
 *   1) shell 级 — 由 PRODUCT_SHELL_NAV[shellKey].roles 决定（顶栏导航是否对该角色显示）。
 *   2) 子路由级 — 部分 wizard / inbox 子路由的 role 比 shell 更严格（例如
 *      `/provider/wizard/inline-catalog` 仅 OPERATER，`/provider/inbox/catalog-review`
 *      仅 MANAGER + BUSIAUDIT）。子路由 role 表是 page 内 canXxx computed 的镜像，
 *      若新增/调整子路由权限，须同步更新本表，由 router.beforeEach + App.vue.onRoleChange
 *      统一触发跳转。
 */

import {
  activeShellKey,
  PRODUCT_SHELL_NAV,
  visibleShellNav,
  type ShellNavItem,
} from '@/config/productShellNav';

/** 不参与 shell 权限判定的辅助路由（登录 / 个人中心等）。 */
const PUBLIC_ROUTE_PREFIXES = ['/login'] as const;

/**
 * 子路由级 role 白名单覆盖（比 shell 更严格）。
 * 顺序敏感：更长 / 更具体的前缀必须排在前面。
 *
 * - `roles`：被允许停留在该子路由的岗位（page 内 canXxx computed 的镜像）。
 * - `redirectIfDenied`：当前岗位不在 `roles` 时，默认跳到这里（业务流水线上的"对位下一站"，
 *    比 shell 顶层更具体）。defaultRouteForRole() 会校验目标对新岗位仍开放后再跳。
 */
export const ROUTE_ROLE_OVERRIDES: ReadonlyArray<{
  prefix: string;
  roles: readonly string[];
  redirectIfDenied?: string;
}> = [
  // 「办申请」导航解体（IA 重构）后，/request-flow 列表页与导航项已删；以下子路由
  // 保留为深链目标，但 activeShellKey('/request-flow/*') 现回落 delivery-exchange shell
  // （roles=[OPERATER,MANAGER]），会错误地把 reviewer 挡在审核详情外。故各子路由在此显式
  // 声明自己页面本就允许的角色集，覆盖 shell 默认。前缀匹配 → 子路径（objection/new、
  // objection/:id、request/:id、review/:id）自动落入对应前缀，无需逐 :id 列举。
  // /request-flow/review：reviewer 决策详情（P3ReviewDetail）—— BUSIAUDIT 受理、MANAGER 审核。
  // 无权岗位（含申请人）跳工作台（受理/审核工作已迁工作台）。
  {
    prefix: '/request-flow/review',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_ORGAN_MANAGER'],
    redirectIfDenied: '/workbench',
  },
  // /request-flow/request：申请人申请详情 + 补录（P3RequestDetail）—— 申请人=操作员/管理员。
  { prefix: '/request-flow/request', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'], redirectIfDenied: '/delivery-exchange' },
  // /request-flow/objection：消费方「我的异议」收件箱/详情/发起（P3ObjectionInbox/Detail/New）。
  // 页面不在路由层 gate（仅 page 内 canSubmit/canEvaluate/canClose 按 action 门控写动作），
  // 沿用原 request-flow shell 消费方角色集 [OPERATER,MANAGER,BUSIAUDIT]——三者皆可查看自己的
  // 异议（evaluate 含三者；submit=操作员/管理员；close=管理员/业务运营员）。
  {
    prefix: '/request-flow/objection',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
    redirectIfDenied: '/delivery-exchange',
  },
  // /request-flow/supply-demand：消费方「供需对接 / 登记需求」（P3SupplyDemand）。
  // demand.register 是消费方登记数据缺口，沿用原 request-flow shell 消费方角色集。
  {
    prefix: '/request-flow/supply-demand',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
    redirectIfDenied: '/delivery-exchange',
  },
  // J2 在线编制 ↔ 目录审核收件箱（OPERATER 提交后切到 reviewer 应直接看到待办）
  // D55/P11：管理员也可直接进在线编制（经 hierarchy 有 create 权，加入后不再被踢到 inbox）
  {
    prefix: '/provider/wizard/inline-catalog',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
    redirectIfDenied: '/provider/inbox/catalog-review',
  },
  {
    prefix: '/provider/inbox/catalog-review',
    roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
    redirectIfDenied: '/provider/wizard/inline-catalog',
  },
  // 反向编目（pages/P5ReverseCatalogWizard.vue → canCreateDraft）D55/P14 操作员也可进
  { prefix: '/provider/datasources', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
  { prefix: '/provider/wizard/reverse-catalog', roles: ['ROLE_ORGAN_MANAGER', 'ROLE_ORGAN_OPERATER'] },
  // 反向编目审核（D57⑧ 两级管线第一级部门审 = 部门管理员；路由 slug 仍 field-decision）。
  // 业务运营员的反向审核在第二级平台审（目录审核收件箱平台档）→ 对位下一站 catalog-review；
  // 操作员无任何反向审核权（做的人不审自己）。
  {
    prefix: '/provider/inbox/field-decision',
    roles: ['ROLE_ORGAN_MANAGER'],
    redirectIfDenied: '/provider/inbox/catalog-review',
  },
  // G3：资源挂接向导（pages/P5HookupSubmitWizard.vue）—— 提交侧是供数维护动作
  // （resource.mount.*.prepare = 部门操作员；管理员经 hierarchy 隐式获得）。业务运营员退出供数注册。
  { prefix: '/provider/wizard/hookup-submit', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
  // G3：代理服务注册向导（pages/P5ApiServiceWizard.vue）—— 注册口径同 resource.api.register（D54）：
  // 部门操作员 + 部门管理员；业务运营员退出 API 注册。
  { prefix: '/provider/wizard/api-service', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
  // G1：挂接审核（pages/P5HookupReviewInbox.vue → canApprove）—— 照 v5「资源挂接审核 = 部门管理员」
  // 校正（撤回 R-007 交叉审），与后端 resource.asset.review={ROLE_ORGAN_MANAGER} set-equal。
  { prefix: '/provider/inbox/hookup-review', roles: ['ROLE_ORGAN_MANAGER'] },
  // G6：异议响应（pages/P5ObjectionDetail.vue）—— v5「异议核查 = 业务运营员 + 部门管理员」，
  // 业务运营员可受理；与后端 objection.case.accept/assign/reply/review/close（含 BUSIAUDIT）一致。
  { prefix: '/provider/inbox/objection', roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'] },
  // C5（D50）国家扩展要素编制（pages/P5NationalExtElem.vue → canCompileNationalExtElem）。
  // 角色门：MANAGER+BUSIAUDIT；flag 门（snapshot.webui.nationalChannel.enabled）在 hub/页内另把守。
  { prefix: '/provider/national-ext-elem', roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'] },
];

function _matchOverride(
  path: string,
): { prefix: string; roles: readonly string[]; redirectIfDenied?: string } | undefined {
  return ROUTE_ROLE_OVERRIDES.find((ov) => path === ov.prefix || path.startsWith(`${ov.prefix}/`));
}

export function shellItemForKey(key: string): ShellNavItem | undefined {
  return PRODUCT_SHELL_NAV.find((item) => item.key === key);
}

/** `#/foo/bar` → `/foo/bar`；非锚点直接返回。供 PageFocusHeader / 页内 nav 卡共用。 */
export function pathFromHref(href: string): string {
  if (href.startsWith('#')) return href.slice(1) || '/';
  return href;
}

/**
 * 按当前 role 过滤一组带 href 的 item（PageFocusHeader 顶栏链 / P5Provider 待办计数卡
 * / 其他页内 nav 列表共用）。getHref 提取每个 item 的目标路径，外链或非 SPA 路径默认保留。
 *
 * 单点过滤的目的：调用方写死的 link/card 列表统一在此过滤，无权岗位直接看不到入口，
 * 而不是"看得到但点击 toast 拒绝"。新增需要按 role 过滤的页面只调用本函数，
 * 不要在 page 内自己实现 role 比对（避免漂移）。
 */
export function filterByRouteAccess<T>(items: readonly T[], getHref: (it: T) => string, role: string): T[] {
  return items.filter((it) => {
    const path = pathFromHref(getHref(it));
    if (!path.startsWith('/')) return true;
    return isRouteAllowedForRole(path, role);
  });
}

/**
 * Action 级权限闸门（不是路由级）。仅放"页面已开放但其中某个 action 仅限部分角色"的场景，
 * 例如 P5Provider 对所有 provider shell 角色开放，但「发布目录」action 仅 BUSIAUDIT（D57⑤）。
 *
 * 权威源在后端 zw_brain/domain/policy.py PERMISSION_ROLES；本表只列前端会渲染 CTA / 入口链接的子集。
 * tests/test_role_codes_alignment.py 守住"本表中的每个 action 必须与后端 policy 一致"，
 * 避免前后端漂移。新增 CTA 想 gate 时直接在此追加 + 配后端 permission 即可。
 *
 * 共性原则（D-编号反模式「点击没反应」→「无权 = 不可见」）：
 *   - 写按钮 / FocusLink 一律走 canPerformAction 守护，不再让用户「看到入口 → 点击 403」。
 *   - 仅当后端 policy 角色集 ⊂ 该路由 shell 角色集时才需要在此声明（否则路由层已挡住）。
 */
export const ACTION_ROLE_GATES: Readonly<Record<string, readonly string[]>> = {
  // P5Provider 发布目录。D57⑤：目录发布权回收仅业务运营员（严格 v5「目录发布=业务运营员」，
  // R-001 给 MANAGER 的保留无签字且「仅自家」未实现）；管理员发布卡整卡不渲染（无权=不可见）。
  'catalog.entry.publish': ['ROLE_BUSIAUDIT'],
  // P5Provider 发布资源（#251 R3 队列）。D57⑤ 同口径机械延伸：v5 资源发布=业务运营员；
  // 原 canPublishResource 硬比对 BUSIAUDIT（刻意窄于旧 policy），本次 policy 对齐后注册回
  // set-equal 表，消除机械审计雷达外的分歧。
  'resource.asset.publish': ['ROLE_BUSIAUDIT'],
  // P4Credential 重新签发
  'credential.issue': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P3ReviewDetail 无条件共享受理即终（D55/P21：受理=业务运营员初级审核单步即终）。
  // 与后端 policy.approval.case.decide.execute={ROLE_BUSIAUDIT} set-equal。
  'approval.case.decide': ['ROLE_BUSIAUDIT'],
  // P2ResourceDetail / P3RequestDetail。D57④：管理员申请人身份照 v5 保留（「我的申请=管理员+
  // 操作员」），补回 MANAGER 发起/提交入口、收口前后端劈叉（后端 hierarchy 本就放行 200）。
  'request.create': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  'request.submit': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  // P3RequestDetail 有条件驳回（rejected）补件重提：复用 application.dept_approve.execute key
  // （decision='resubmit'，conditional_approval.applicant_resubmit），申请人 OPERATER/MANAGER 发起。
  // 与后端 policy.application.dept_approve.execute={ROLE_ORGAN_MANAGER,ROLE_ORGAN_OPERATER} set-equal
  // （test_action_role_gates_aligned_with_backend_policy 守）；部门审核（approve/reject）路径在后端
  // 另按 ctx.role==MANAGER 二次门控，前端 P3ReviewDetail 审批面承接，不在本详情页发审批决定。
  'application.dept_approve': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  // P3ReviewDetail 第一级受理（submitted → dept_approved/rejected），M1 工作台行内受理亦依赖它。
  // 此前漏注册 → canPerformAction 默认放行，行内按钮对无权岗位也渲染（破「无权=不可见」）。
  // 与后端 policy.application.platform_approve.execute={ROLE_BUSIAUDIT} set-equal。
  'application.platform_approve': ['ROLE_BUSIAUDIT'],
  // P3RequestDetail 撤回 / 暂停授权（write-critical）。j1-credential-revoke 决策 A（已签字）：
  // 撤回 = 业务运营员合规驱动 + 申请人本人主动放弃（owner 校验在后端）；暂停 = 业务运营员。
  // 与后端 policy.py 严格 set-equal（test_role_codes_alignment 守）。
  'application.grant.revoke': ['ROLE_BUSIAUDIT', 'ROLE_ORGAN_OPERATER'],
  'application.grant.suspend': ['ROLE_BUSIAUDIT'],
  // P5 编目工坊
  'catalog.entry.create_draft': ['ROLE_ORGAN_OPERATER'],
  'catalog.entry.update': ['ROLE_ORGAN_OPERATER'],
  'catalog.entry.submit_review': ['ROLE_ORGAN_OPERATER'],
  'catalog.entry.review': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // 反向编目部门审（D57⑧ 两级管线第一级）：confirm/reject = 部门管理员；平台审走上面的
  // catalog.entry.review（pending_platform_review 档，BUSIAUDIT）。操作员无反向审核权
  // （做的人不审自己）。与后端 policy set-equal（test_action_role_gates… 守）。
  'catalog.entry.reverse_draft.confirm': ['ROLE_ORGAN_MANAGER'],
  'catalog.entry.reverse_draft.reject': ['ROLE_ORGAN_MANAGER'],
  // P5 反向 / API wizard
  // G1：挂接资产审核照 v5 校正归部门管理员（撤回 R-007），与后端 resource.asset.review set-equal。
  'resource.asset.review': ['ROLE_ORGAN_MANAGER'],
  // 代理服务（API）注册口径 D54 GATE-1（业务方 2026-06-08 sign-off）：注册/提交审核 = 部门操作员 + 部门管理员；
  // 审核/发布 = 部门管理员；业务运营员退出 API 生命周期。须与后端 policy.PERMISSION_ROLES set-equal
  // （test_action_role_gates_aligned_with_backend_policy 守）。
  'resource.api.register': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  'resource.api.submit_review': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  'resource.api.review': ['ROLE_ORGAN_MANAGER'],
  'resource.api.publish': ['ROLE_ORGAN_MANAGER'],
  // 下线（withdraw→retired）是已发布服务的写关键动作，列表行内可点 → 显式登记并 set-equal 后端，
  // 不借 publish gate 代理（避免两者后端口径漂移时 UI 静默跟错）。
  'resource.api.withdraw': ['ROLE_ORGAN_MANAGER'],
  'resource.api.test': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  // P3 供需 / 交付
  'delivery.trigger_recovery': ['ROLE_ORGAN_MANAGER'],
  // 'service.publish_or_suspend' 已删（减法）：全 zw-brain-web/src 无任何 CTA/skillId 调用它
  // （仅 registry/pages.generated.ts 自动清单列入），UI 上线/暂停服务统一走 resource.api.withdraw。
  // 留空门只是给机械审计添噪，无可见入口可门控，故移除。
  // P2ResourceDetail 字段数据模型（只读）— metadata.schema.query.execute
  'metadata.schema.query': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  // B1.1 异议详情（查审计 shell 含安全审计员，D55/P22 审计纯只读）——升级/解决写动作
  // 仅业务运营员 + 部门管理员可见，与后端 objection.case.escalate/close set-equal。
  'objection.case.escalate': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  'objection.case.close': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P5ObjectionInbox/Detail 受理（D57①，R6）：异议收件箱纳入 submitted 态 + 接通受理动作，
  // v5 异议受理=业务运营员（+管理员），与后端 objection.case.accept set-equal。
  'objection.case.accept': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // C5（D50）P5 国家扩展要素编制 — 与后端 policy catalog.national_ext_elem.compile.execute set-equal。
  'catalog.national_ext_elem.compile': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // C6（D50）P3 国家直达转报 — 与后端 policy application.escalate_national.execute set-equal。
  'application.escalate_national': ['ROLE_BUSIAUDIT'],
  // P3ObjectionDetail 提交 / 评价（permission-matrix-0610）：提交=异议提出方（操作员/管理员，
  // v5「异议提出 = 部门操作员、部门管理员」）；评价=三岗位。与后端 set-equal。
  'objection.case.submit': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  'objection.case.evaluate': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P4Credential 调用记录段。D57⑥：安全审计员退服务调用监控（全局面随 service-ops 导航一并收窄）；
  // MANAGER 保留=「自家资源被调用情况」留在 P4 凭据门内（hasCredential 双门），与 policy set-equal。
  'ops.service.invocation.query': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  // 反向编目草稿发起（pages/P5ReverseCatalogWizard.vue → canCreateDraft，skillId
  // catalog.entry.reverse_draft.create）—— v5 操作员+管理员，与后端 policy
  // catalog.entry.reverse_draft.create.execute set-equal（R-014 收硬编码角色比对）。
  'catalog.entry.reverse_draft.create': ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  // 供方数据质量待办可见（pages/P5Provider.vue → canSeeDataQuality）—— 用途脏值的
  // 真实导入单是供方数据质量 owner（业务运营员）的待办，其余岗位不可见（无权=不渲染）。
  // 视图级可见门，无对应写 capability；R-014 收硬编码 role.value==='ROLE_BUSIAUDIT'。
  'provider.data_quality.view': ['ROLE_BUSIAUDIT'],
};

export function canPerformAction(action: keyof typeof ACTION_ROLE_GATES | string, role: string): boolean {
  const allowed = ACTION_ROLE_GATES[action];
  if (!allowed) return true; // 未注册的 action 默认不拦（后端仍兜底）
  return allowed.includes(role);
}

/**
 * 角色身份判定 chokepoint —— 当 UI 需要按「当前岗位是谁」区分**同一动作的不同变体**
 * （非纯权限门）时用本函数，不在 page 里散落 `role === 'ROLE_…'` 硬比对。
 *
 * 典型场景：application.grant.revoke 同时授予 BUSIAUDIT（合规收回）与 OPERATER
 * （申请人主动放弃），但两条路径渲染不同按钮/文案——用 canPerformAction 判「能不能」、
 * 用 hasRole 判「是哪条身份分支」。集中在此便于 R-014 守卫把 page 内硬编码角色比对
 * 钉死（pages/*.vue 不得出现 === 'ROLE_'），真值仍是单一来源。
 */
export function hasRole(role: string, target: string): boolean {
  return role === target;
}

export function isRouteAllowedForRole(path: string, role: string): boolean {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (normalized === '/' || PUBLIC_ROUTE_PREFIXES.some((p) => normalized.startsWith(p))) {
    return true;
  }
  const override = _matchOverride(normalized);
  if (override) {
    return override.roles.includes(role);
  }
  const key = activeShellKey(normalized);
  const item = shellItemForKey(key);
  if (!item) return true;
  return item.roles.includes(role);
}

/**
 * 当前岗位无权访问时，跳到该岗位可见的入口。
 *
 * 优先级（fromPath 提供时）：
 *   1) 若 fromPath 命中某 ROUTE_ROLE_OVERRIDES 且声明了 redirectIfDenied，
 *      且 redirectIfDenied 对新 role 允许 → 跳到 redirectIfDenied（业务流水线对位）；
 *   2) 否则若 fromPath 所在 shell 对新 role 开放 → 跳到 shell 顶层（保持上下文）；
 *   3) 否则跳到该 role 第一个可见的 shell。
 */
export function defaultRouteForRole(role: string, fromPath?: string): string {
  if (fromPath) {
    const normalized = fromPath.startsWith('/') ? fromPath : `/${fromPath}`;
    const override = _matchOverride(normalized);
    if (override?.redirectIfDenied && isRouteAllowedForRole(override.redirectIfDenied, role)) {
      return override.redirectIfDenied;
    }
    const shellKey = activeShellKey(normalized);
    const shell = shellItemForKey(shellKey);
    if (shell && shell.roles.includes(role) && normalized !== shell.to) {
      return shell.to;
    }
  }
  const nav = visibleShellNav(role);
  return nav[0]?.to ?? '/workbench';
}
