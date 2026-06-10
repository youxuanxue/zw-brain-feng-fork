/** P3 申请流「部门审核」队列（第二级终审，D55/P21）：部门管理员审 dept_approved（受理后）单据。
 *  有条件共享受理→部门审核两级：本队列 = 第二级。无条件共享无本级（业务运营员受理即终）。 */
export const REQUEST_FLOW_REVIEWER_ROLES = ['ROLE_ORGAN_MANAGER'] as const;

/** 业务运营员在 P5 反向编目审核收件箱办理反向编目草稿。 */
export const FIELD_DECISION_ROLES = ['ROLE_BUSIAUDIT'] as const;

/** 挂接审核通过（D55/G1 照 v5「资源挂接审核 = 部门管理员」校正，与后端
 *  resource.asset.review={ROLE_ORGAN_MANAGER} 及路由 /provider/inbox/hookup-review set-equal）。 */
export const HOOKUP_REVIEW_ROLES = ['ROLE_ORGAN_MANAGER'] as const;

/** J2 在线编制目录（catalog.entry.create_draft / update / submit_review）。
 *  D55/P11：部门操作员 + 部门管理员（管理员经 hierarchy 有 create 权，路由也已开放）。 */
export const INLINE_CATALOG_AUTHOR_ROLES = ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] as const;

/** 供数侧「目录/资源管理清单」（T9）只读浏览岗位：供数三岗位（部门操作员/部门管理员/业务运营员）
 *  均可按生命周期浏览本部门已编目目录 / 已挂接资源。操作员=编制者也需看本部门清单跟踪状态
 *  （业务方 2026-06-09 确认：给操作员只读本部门清单）。清单纯只读、无行内管理动作，故视图门
 *  比发布岗更宽；发布/变更等写动作仍各自走 ACTION_ROLE_GATES。安全审计不在供数侧、不列入。 */
export const PROVIDER_ASSET_VIEWER_ROLES = [
  'ROLE_ORGAN_OPERATER',
  'ROLE_ORGAN_MANAGER',
  'ROLE_BUSIAUDIT',
] as const;

export function canViewProviderAssets(role: string): boolean {
  return (PROVIDER_ASSET_VIEWER_ROLES as readonly string[]).includes(role);
}

/** J2 部门审目录（catalog.entry.review 第 1 层，pending_review → pending_platform_review）。 */
export const CATALOG_DEPT_REVIEWER_ROLES = ['ROLE_ORGAN_MANAGER'] as const;

/** J2 平台审目录（catalog.entry.review 第 2 层，pending_platform_review → approved_pending_publish）。 */
export const CATALOG_PLATFORM_REVIEWER_ROLES = ['ROLE_BUSIAUDIT'] as const;

/** P3 申请流「受理」队列（第一级初级审核，D55/P21）：业务运营员受理 submitted 单据。
 *  无条件 = 受理即终（submitted→granted）；有条件 = 受理（submitted→dept_approved）后转部门审核。
 *  与 policy application.platform_approve.execute / application.resource.review.execute 对齐。 */
export const REQUEST_FLOW_PLATFORM_REVIEWER_ROLES = ['ROLE_BUSIAUDIT'] as const;

export function canReviewRequests(role: string): boolean {
  return (REQUEST_FLOW_REVIEWER_ROLES as readonly string[]).includes(role);
}

/** J1 受理队列（第一级，业务运营员）= 省大数据局业务运营员（与 policy 受理类 key 对齐）。 */
export function canPlatformReviewRequests(role: string): boolean {
  return (REQUEST_FLOW_PLATFORM_REVIEWER_ROLES as readonly string[]).includes(role);
}

export function canDecideFieldDrafts(role: string): boolean {
  return (FIELD_DECISION_ROLES as readonly string[]).includes(role);
}

export function canApproveHookup(role: string): boolean {
  return (HOOKUP_REVIEW_ROLES as readonly string[]).includes(role);
}

export function canAuthorInlineCatalog(role: string): boolean {
  return (INLINE_CATALOG_AUTHOR_ROLES as readonly string[]).includes(role);
}

export function canReviewCatalogDept(role: string): boolean {
  return (CATALOG_DEPT_REVIEWER_ROLES as readonly string[]).includes(role);
}

export function canReviewCatalogPlatform(role: string): boolean {
  return (CATALOG_PLATFORM_REVIEWER_ROLES as readonly string[]).includes(role);
}

/** C5（D50）国家扩展要素编制：部门管理员编制 + 业务运营员主管审核（与后端 policy
 *  catalog.national_ext_elem.compile.execute 对齐）。flag 门另由 snapshot.webui.nationalChannel.enabled 把守。 */
export const NATIONAL_EXT_ELEM_ROLES = ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'] as const;

export function canCompileNationalExtElem(role: string): boolean {
  return (NATIONAL_EXT_ELEM_ROLES as readonly string[]).includes(role);
}

/** C6（D50）国家直达转报：仅业务运营员可见「国家通道」tab + 办转报（与后端 policy
 *  application.escalate_national.execute 对齐）。flag 门另由 snapshot.webui.nationalChannel.enabled 把守。 */
export const NATIONAL_DIRECT_ROLES = ['ROLE_BUSIAUDIT'] as const;

export function canViewNationalChannel(role: string): boolean {
  return (NATIONAL_DIRECT_ROLES as readonly string[]).includes(role);
}
