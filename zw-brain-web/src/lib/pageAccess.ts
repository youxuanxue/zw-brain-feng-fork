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
const PUBLIC_ROUTE_PREFIXES = ['/login', '/profile', '/migration-acceptance'] as const;

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
  // J2 在线编制 ↔ 目录审核收件箱（OPERATER 提交后切到 reviewer 应直接看到待办）
  {
    prefix: '/provider/wizard/inline-catalog',
    roles: ['ROLE_ORGAN_OPERATER'],
    redirectIfDenied: '/provider/inbox/catalog-review',
  },
  {
    prefix: '/provider/inbox/catalog-review',
    roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
    redirectIfDenied: '/provider/wizard/inline-catalog',
  },
  // 反向编目（pages/P5ReverseCatalogWizard.vue → canCreateDraft）
  { prefix: '/provider/wizard/reverse-catalog', roles: ['ROLE_ORGAN_MANAGER'] },
  // 字段审核（pages/P5FieldDecisionDetail.vue → canDecide；路由 slug 仍 field-decision）
  { prefix: '/provider/inbox/field-decision', roles: ['ROLE_BUSIAUDIT'] },
  // 挂接审核（pages/P5HookupReviewInbox.vue → canApprove）
  { prefix: '/provider/inbox/hookup-review', roles: ['ROLE_BUSIAUDIT'] },
  // 异议响应（pages/P5ObjectionDetail.vue → role: ROLE_ORGAN_MANAGER）
  { prefix: '/provider/inbox/objection', roles: ['ROLE_ORGAN_MANAGER'] },
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
 * 例如 P5Provider 对所有 provider shell 角色开放，但「发布目录」action 仅 MANAGER+BUSIAUDIT。
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
  // P5Provider / P5InlineCatalogWizard 发布
  'catalog.entry.publish': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P4Credential 重新签发
  'credential.issue': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P3ReviewDetail 通过 / 退回 / 驳回（已被 isReviewer 守护，但显式登记便于 FocusLink 复用）
  'approval.case.decide': ['ROLE_ORGAN_MANAGER'],
  // P2ResourceDetail / P3RequestDetail
  'request.create': ['ROLE_ORGAN_OPERATER'],
  'request.submit': ['ROLE_ORGAN_OPERATER'],
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
  // P5 反向 / API / 质量 wizard
  'resource.asset.review': ['ROLE_BUSIAUDIT'],
  'resource.api.register': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  'resource.api.submit_review': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  'resource.api.review': ['ROLE_BUSIAUDIT'],
  'resource.api.publish': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  'resource.api.test': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  'quality.rule.upsert': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // P3 供需 / 交付
  'delivery.trigger_recovery': ['ROLE_ORGAN_MANAGER'],
  'service.publish_or_suspend': ['ROLE_ORGAN_MANAGER'],
  // P2ResourceDetail 字段数据模型（只读）— metadata.schema.query.execute
  'metadata.schema.query': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  // C5（D50）P5 国家扩展要素编制 — 与后端 policy catalog.national_ext_elem.compile.execute set-equal。
  'catalog.national_ext_elem.compile': ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  // C6（D50）P3 国家直达转报 — 与后端 policy application.escalate_national.execute set-equal。
  'application.escalate_national': ['ROLE_BUSIAUDIT'],
};

export function canPerformAction(action: keyof typeof ACTION_ROLE_GATES | string, role: string): boolean {
  const allowed = ACTION_ROLE_GATES[action];
  if (!allowed) return true; // 未注册的 action 默认不拦（后端仍兜底）
  return allowed.includes(role);
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
