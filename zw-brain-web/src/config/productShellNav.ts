/**
 * 与旧 js/pages.js `PRODUCT_SHELL_NAV` 对齐（E5 Vue 重建时补回主导航）。
 * 同步更新 zw_brain/domain/web_snapshot_redaction.py 中对应 frozenset。
 */
export interface ShellNavItem {
  key: string;
  navLabel: string;
  to: string;
  roles: readonly string[];
}

export const PRODUCT_SHELL_NAV: ShellNavItem[] = [
  {
    key: 'workbench',
    navLabel: '数据共享工作台',
    to: '/workbench',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT', 'ROLE_SYSTEM'],
  },
  {
    key: 'discovery',
    navLabel: '找可复用数据',
    to: '/discovery',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'request-flow',
    navLabel: '办共享申请',
    to: '/request-flow',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  },
  {
    key: 'delivery-exchange',
    navLabel: '看交付回执',
    to: '/delivery-exchange',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'provider',
    navLabel: '维护数据供给',
    to: '/provider',
    // ROLE_ORGAN_OPERATER：roles §66 / J2 §166 明确「在线编制」属操作员职责，须能进 /provider shell。
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  },
  {
    key: 'compliance-ops',
    navLabel: '查审计证据',
    to: '/compliance-ops',
    roles: ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT', 'ROLE_SECURITY_ADMIN', 'ROLE_SYSTEM'],
  },
  {
    key: 'zones-pack',
    navLabel: '进专题包',
    to: '/zones-pack',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    key: 'integration-admin',
    navLabel: '管受控接入',
    to: '/integration-admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  },
];

export function visibleShellNav(role: string): ShellNavItem[] {
  return PRODUCT_SHELL_NAV.filter((item) => item.roles.includes(role));
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
  if (p.startsWith('/integration-admin')) return 'integration-admin';
  if (p.startsWith('/workbench') || p === '/profile' || p.startsWith('/login')) return 'workbench';
  return 'workbench';
}
