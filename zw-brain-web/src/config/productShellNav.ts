/**
 * 与旧 js/pages.js `PRODUCT_SHELL_NAV` 对齐（E5 Vue 重建时补回主导航）。
 * 同步更新 zw_brain/domain/web_snapshot_redaction.py 中对应 frozenset。
 */
/** 旅程分组：左侧侧边栏按「用数 / 供数 / 后台」三段组织（信息架构 = D39 2 旅程 + B1 后台）。 */
export type JourneyGroup = 'use' | 'supply' | 'admin';

export const JOURNEY_GROUP_LABEL: Record<JourneyGroup, string> = {
  use: '用数据',
  supply: '供数据',
  admin: '后台与审计',
};

export interface ShellNavItem {
  key: string;
  navLabel: string;
  /** 侧边栏每项的一行业务说明（设计即工作方式：让人知道这里办什么）。 */
  navDesc: string;
  to: string;
  group: JourneyGroup;
  roles: readonly string[];
}

export const PRODUCT_SHELL_NAV: ShellNavItem[] = [
  {
    key: 'workbench',
    navLabel: '工作台',
    navDesc: '今日待办与办理建议一屏看清',
    to: '/workbench',
    group: 'use',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT', 'ROLE_SYSTEM'],
  },
  {
    key: 'discovery',
    navLabel: '找数据',
    navDesc: '搜索可复用的政务数据资源',
    to: '/discovery',
    group: 'use',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'request-flow',
    navLabel: '办申请',
    navDesc: '发起、跟进与审批共享申请',
    to: '/request-flow',
    group: 'use',
    // ROLE_BUSIAUDIT：j1-credential-revoke 决策 A —— 业务运营员在 P3 申请详情合规收回/暂停授权。
    // 审批等 action 仍由 action-gate 限 MANAGER（无权不可见），BUSIAUDIT 只多出收回/暂停。
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  },
  {
    key: 'delivery-exchange',
    navLabel: '领数据',
    navDesc: '领取访问凭据、核对交付回执',
    to: '/delivery-exchange',
    group: 'use',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'zones-pack',
    navLabel: '专题包',
    navDesc: '按场景订阅成套共享数据',
    to: '/zones-pack',
    group: 'use',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'provider',
    navLabel: '供数据',
    navDesc: '维护本部门对外提供的数据',
    to: '/provider',
    group: 'supply',
    // ROLE_ORGAN_OPERATER：roles §66 / J2 §166 明确「在线编制」属操作员职责，须能进 /provider shell。
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  },
  {
    key: 'compliance-ops',
    navLabel: '查审计',
    navDesc: '审计证据回放与合规核查',
    to: '/compliance-ops',
    group: 'admin',
    roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT', 'ROLE_SECURITY_ADMIN', 'ROLE_SYSTEM'],
  },
  {
    // 「接入扩展中心」容器解体（负责人 2026-06-05 裁）：后台四模块各自独立成导航——
    // 查审计 / 外部系统 / 流程表单 / 身份治理。短标签为全名字面收缩，不造新词。
    key: 'integration-admin',
    navLabel: '外部系统',
    navDesc: '外来系统接入审批、信任评估与启停',
    to: '/integration-admin',
    group: 'admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  },
  {
    // 流程与表单配置独立为导航模块（第一轮 ruled-but-staged「配置轴升独立主导航」兑现）。
    // 路由仍为 /integration-admin/engines（零路由churn），页头保留全名「流程与表单配置」。
    key: 'engines',
    navLabel: '流程表单',
    navDesc: '审批流程、申请表单与智能推荐配置',
    to: '/integration-admin/engines',
    group: 'admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  },
  {
    // 身份治理独立为左侧导航项（负责人 2026-06-05 裁 Q1）。
    // 路由仍为 /integration-admin/iam-governance（契约测试不破），角色门同 capability。
    key: 'iam-governance',
    navLabel: '身份治理',
    navDesc: '旧权限映射候选审核与租户策略',
    to: '/integration-admin/iam-governance',
    group: 'admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  },
];

export function visibleShellNav(role: string): ShellNavItem[] {
  return PRODUCT_SHELL_NAV.filter((item) => item.roles.includes(role));
}

/** 把有权项按旅程分组（用数 / 供数 / 后台），空组不返回。 */
export function visibleShellNavByGroup(
  role: string,
): Array<{ group: JourneyGroup; label: string; items: ShellNavItem[] }> {
  const order: JourneyGroup[] = ['use', 'supply', 'admin'];
  const visible = visibleShellNav(role);
  return order
    .map((group) => ({
      group,
      label: JOURNEY_GROUP_LABEL[group],
      items: visible.filter((it) => it.group === group),
    }))
    .filter((g) => g.items.length > 0);
}

/** 与旧 `ZW_PAGE_SHELL` 路由前缀 → shell key 映射一致。 */
export function activeShellKey(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  if (p.startsWith('/discovery')) return 'discovery';
  if (p.startsWith('/request-flow')) return 'request-flow';
  if (p.startsWith('/delivery-exchange')) return 'delivery-exchange';
  if (p.startsWith('/provider')) return 'provider';
  if (p.startsWith('/compliance-ops')) return 'compliance-ops';
  if (p.startsWith('/zones-pack')) return 'zones-pack';
  // 身份治理 / 流程表单 独立导航项：须在 /integration-admin 前缀判断之前命中，否则被吸附回外部系统高亮。
  if (p.startsWith('/integration-admin/iam-governance')) return 'iam-governance';
  if (p.startsWith('/integration-admin/engines')) return 'engines';
  if (p.startsWith('/integration-admin')) return 'integration-admin';
  if (p.startsWith('/workbench') || p === '/profile' || p.startsWith('/login')) return 'workbench';
  return 'workbench';
}
