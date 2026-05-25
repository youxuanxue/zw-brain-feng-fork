/** P3 申请流：谁可以审批共享申请（approval.case.decide 与 policy 对齐）。 */
export const REQUEST_FLOW_REVIEWER_ROLES = ['ROLE_ORGAN_MANAGER'] as const;

/** 业务运营员在 P5 字段裁决收件箱办理反向编目草稿。 */
export const FIELD_DECISION_ROLES = ['ROLE_BUSIAUDIT'] as const;

/** 挂接审核通过（resource.asset.review 仅 BUSIAUDIT）。 */
export const HOOKUP_REVIEW_ROLES = ['ROLE_BUSIAUDIT'] as const;

export function canReviewRequests(role: string): boolean {
  return (REQUEST_FLOW_REVIEWER_ROLES as readonly string[]).includes(role);
}

export function canDecideFieldDrafts(role: string): boolean {
  return (FIELD_DECISION_ROLES as readonly string[]).includes(role);
}

export function canApproveHookup(role: string): boolean {
  return (HOOKUP_REVIEW_ROLES as readonly string[]).includes(role);
}
