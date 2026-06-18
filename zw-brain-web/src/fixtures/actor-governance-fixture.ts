/**
 * 身份治理「用户与角色」+「谁能访问什么」面板 fallback（后端不可达时展示结构样例，非验收依据）。
 *
 * 仅经 lib/panelFallback.applyPanelFallback 在**开发构建**回退使用（source='fixture' → 演示数据徽标）；
 * 生产构建一律不上屏（D11 业务数据禁 Mock）。所有条目均为虚构占位，evidence 标 source:'fixture'。
 */

export type ActorStatus = 'active' | 'iam_account_missing' | 'unmatched' | 'disabled';

export interface ActorBinding {
  org_code: string;
  role_code: string;
  binding_status: string;
}

export interface ActorItem {
  external_actor_id: string;
  display_name: string;
  org_code: string;
  status: ActorStatus;
  iaf_bound: boolean;
  binding_status: string;
  bindings: ActorBinding[];
  role_codes: string[];
}

export interface ActorListResult {
  tenant_id: string;
  total: number;
  items: ActorItem[];
  summary: { total: number; status_counts: Record<string, number> };
}

export interface AccessMatrixRole {
  role_code: string;
  display_name: string;
  capability_count: number;
  capabilities: string[];
}

export interface AccessMatrixCapability {
  capability_id: string;
  roles: string[];
}

export interface AccessMatrixResult {
  roles: AccessMatrixRole[];
  capabilities: AccessMatrixCapability[];
}

export const ACTOR_LIST_FIXTURE: ActorListResult = {
  tenant_id: 'sd-default',
  total: 3,
  items: [
    {
      external_actor_id: 'sample-actor-zhangsan',
      display_name: '张三（样例）',
      org_code: 'SD-JNGAJ',
      status: 'active',
      iaf_bound: true,
      binding_status: 'active',
      bindings: [{ org_code: 'SD-JNGAJ', role_code: 'ROLE_ORGAN_OPERATER', binding_status: 'active' }],
      role_codes: ['ROLE_ORGAN_OPERATER'],
    },
    {
      external_actor_id: 'sample-actor-lisi',
      display_name: '李四（样例）',
      org_code: 'SD-JNRSJ',
      status: 'iam_account_missing',
      iaf_bound: false,
      binding_status: 'iam_account_missing',
      bindings: [{ org_code: 'SD-JNRSJ', role_code: 'ROLE_ORGAN_MANAGER', binding_status: 'iam_account_missing' }],
      role_codes: ['ROLE_ORGAN_MANAGER'],
    },
    {
      external_actor_id: 'sample-actor-wangwu',
      display_name: '王五（样例）',
      org_code: 'SD-JNMZJ',
      status: 'unmatched',
      iaf_bound: false,
      binding_status: 'unmatched',
      bindings: [],
      role_codes: [],
    },
  ],
  summary: {
    total: 3,
    status_counts: { active: 1, iam_account_missing: 1, unmatched: 1 },
  },
};

export const ACCESS_MATRIX_FIXTURE: AccessMatrixResult = {
  roles: [
    {
      role_code: 'ROLE_ORGAN_OPERATER',
      display_name: '部门操作员',
      capability_count: 3,
      capabilities: ['catalog.entry.create_draft', 'resource.api.register', 'request.create'],
    },
    {
      role_code: 'ROLE_ORGAN_MANAGER',
      display_name: '部门管理员',
      capability_count: 3,
      capabilities: ['catalog.entry.review', 'resource.asset.review', 'application.dept_approve'],
    },
    {
      role_code: 'ROLE_BUSIAUDIT',
      display_name: '业务运营员',
      capability_count: 2,
      capabilities: ['catalog.entry.publish', 'objection.case.accept'],
    },
    {
      role_code: 'ROLE_SECURITY_AUDIT',
      display_name: '安全审计员',
      capability_count: 1,
      capabilities: ['audit.event.query'],
    },
    {
      role_code: 'ROLE_SYSTEM',
      display_name: '平台运维员',
      capability_count: 1,
      capabilities: ['governance.actor.list'],
    },
  ],
  capabilities: [
    { capability_id: 'catalog.entry.create_draft', roles: ['ROLE_ORGAN_OPERATER'] },
    { capability_id: 'resource.api.register', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
    { capability_id: 'request.create', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
    { capability_id: 'catalog.entry.review', roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'] },
    { capability_id: 'resource.asset.review', roles: ['ROLE_ORGAN_MANAGER'] },
    { capability_id: 'application.dept_approve', roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'] },
    { capability_id: 'catalog.entry.publish', roles: ['ROLE_BUSIAUDIT'] },
    { capability_id: 'objection.case.accept', roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'] },
    { capability_id: 'audit.event.query', roles: ['ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'] },
    { capability_id: 'governance.actor.list', roles: ['ROLE_SYSTEM'] },
  ],
};
