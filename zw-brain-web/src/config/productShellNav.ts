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
    navDesc: '搜索可申请的政务数据资源',
    to: '/discovery',
    group: 'use',
    // 安全审计员非数据使用方（v5 无找数据），Wave 1/S5 收敛纯只读监督者后退出找数据（D55/P17）。
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'],
  },
  // 「办申请」独立导航解体（IA 重构）：发起申请已在「找数据」；受理/审核归「工作台」；
  // 我的申请 / 我的授权归并「领数据」，使领数据成为消费方「我的数据」一站式入口。
  // 申请详情 / 受理审核详情 / 异议 / 供需 等子路由保留为深链目标，角色门见
  // pageAccess.ts ROUTE_ROLE_OVERRIDES（/request-flow/* 不再回落 delivery-exchange shell 角色）。
  {
    key: 'delivery-exchange',
    navLabel: '领数据',
    navDesc: '申请进度、凭据领取与交付回执',
    to: '/delivery-exchange',
    group: 'use',
    // D55/P13：领数据回归部门操作员+部门管理员（反转 D53/F1）；P18 安全审计员退出领数据导航。
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'],
  },
  {
    // 智能体：承接 A 类平台办事助手 + B 类场景用数助手。路由沿用 /data-apps，
    // 避免 URL churn；页面内按 AGENT.yaml labels.scenario_class 分组。
    // roles = 已落地 AgentRuntime 场景智能体可用角色并集；卡片级继续按 allowed_roles 过滤。
    key: 'data-apps',
    navLabel: '智能体',
    navDesc: '找数办事的智能助手',
    to: '/data-apps',
    group: 'use',
    roles: ['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT', 'ROLE_SYSTEM'],
  },
  // 专题包导航项退出本期（D55/P6）：下线整面，保数据不删库；待复活时恢复 zones-pack 导航。
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
    // 查审计拆分（D55/P8·P9，Wave1-S3）：审计日志 / 证据回放 / 审计事件面收窄到
    // 业务运营员 + 安全审计员。部门管理员退审计日志（P9）、平台运维员退审计日志（P8），
    // 二者均不再看到本导航项（无权 = 不可见，非"可见但禁用"）。
    // 服务调用监控独立为下方 service-ops 导航项（平台运维员 / 业务运营员 + 管理员/审计只读）。
    key: 'compliance-ops',
    navLabel: '查审计',
    navDesc: '审计证据回放与合规核查',
    to: '/compliance-ops',
    group: 'admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'],
  },
  {
    // 服务调用监控（D55/P8 拆分 → D57⑥ 收窄）：网关运行只读面。
    // D57⑥ 收窄后全局服务调用统计退役——per-resource 调用记录保留在领数据 P4 凭据门内
    // （ops.service.invocation.query），本面只承接网关运行只读，不再展示全局调用统计空壳。
    // 仅平台运维员 + 业务运营员（v5 服务调用日志口径）；部门管理员、安全审计员退出全局监控。
    // 角色门与后端 ops.service.report.query.execute 一致。
    key: 'service-ops',
    navLabel: '服务调用监控',
    navDesc: '网关运行只读',
    to: '/service-ops',
    group: 'admin',
    roles: ['ROLE_BUSIAUDIT', 'ROLE_SYSTEM'],
  },
  {
    // 「接入扩展中心」容器解体（负责人 2026-06-05 裁）：后台四模块各自独立成导航——
    // 查审计 / 外部系统 / 流程表单 / 身份治理。短标签为全名字面收缩，不造新词。
    key: 'integration-admin',
    navLabel: '外部系统',
    navDesc: '外来系统接入审批、信任评估与启停',
    to: '/integration-admin',
    group: 'admin',
    roles: ['ROLE_SYSTEM'],
  },
  {
    // 流程与表单配置独立为导航模块（第一轮 ruled-but-staged「配置轴升独立主导航」兑现）。
    // 路由仍为 /integration-admin/engines（零路由churn）；页头见 ENGINES_PAGE_TITLE（待接入标注）。
    key: 'engines',
    navLabel: '流程表单',
    navDesc: '审批流程、申请表单与智能推荐配置',
    to: '/integration-admin/engines',
    group: 'admin',
    // D55/P3 反转 D49 配置角色：流程表单配置 = 平台级系统配置 = 平台运维员独有，部门管理员/业务运营员退出。
    roles: ['ROLE_SYSTEM'],
  },
  {
    // 身份治理独立为左侧导航项（负责人 2026-06-05 裁 Q1）。
    // 路由仍为 /integration-admin/iam-governance（契约测试不破），角色门同 capability。
    key: 'iam-governance',
    navLabel: '身份治理',
    navDesc: '用户和角色分派、能力矩阵',
    to: '/integration-admin/iam-governance',
    group: 'admin',
    roles: ['ROLE_SYSTEM'],
  },
];

/** B1.2 流程表单页头全名（配置尚未接入真实业务，页头诚实标注）。 */
export const ENGINES_PAGE_TITLE = '流程与表单配置（待接入）';

export function visibleShellNav(role: string): ShellNavItem[] {
  return PRODUCT_SHELL_NAV.filter((item) => item.roles.includes(role));
}

export function shellNavItemByKey(key: string): ShellNavItem | undefined {
  return PRODUCT_SHELL_NAV.find((item) => item.key === key);
}

export function shellNavLabelByKey(key: string): string {
  return shellNavItemByKey(key)?.navLabel ?? key;
}

export function shellNavLabelForPath(path: string): string {
  return shellNavLabelByKey(activeShellKey(path));
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
  if (p.startsWith('/data-apps')) return 'data-apps';
  // 「办申请」导航解体后，/request-flow/* 子路由（保留为深链目标）归属领数据 shell，
  // 由 PRODUCT_SHELL_NAV 高亮/授权落在 delivery-exchange；具体子路由角色门见
  // pageAccess.ts ROUTE_ROLE_OVERRIDES（reviewer 详情等比 delivery shell 更宽/不同）。
  if (p.startsWith('/request-flow')) return 'delivery-exchange';
  if (p.startsWith('/delivery-exchange')) return 'delivery-exchange';
  if (p.startsWith('/provider')) return 'provider';
  if (p.startsWith('/compliance-ops')) return 'compliance-ops';
  if (p.startsWith('/service-ops')) return 'service-ops';
  // /zones-pack 专题包路由退出本期（D55/P6）：路由已下线，不再映射 shell key。
  // 身份治理 / 流程表单 独立导航项：须在 /integration-admin 前缀判断之前命中，否则被吸附回外部系统高亮。
  if (p.startsWith('/integration-admin/iam-governance')) return 'iam-governance';
  if (p.startsWith('/integration-admin/engines')) return 'engines';
  if (p.startsWith('/integration-admin')) return 'integration-admin';
  if (p.startsWith('/workbench') || p === '/profile' || p.startsWith('/login')) return 'workbench';
  return 'workbench';
}
