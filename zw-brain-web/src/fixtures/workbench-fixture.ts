// 与 zw_brain/domain/seed_snapshot.json::workbench.ROLE_ORGAN_OPERATER 同源切片。
// 仅在后端 /api/skills/workbench.view 不可达（开发期未启 brain server）时兜底。
// 真实部署一定走 API，不读这份 fixture。
//
// 数据范围：sd-default 单租户单角色（部门操作员）；F2/F3 阶段移除或归并到 dev-server stub。

export interface WorkbenchTodo {
  id: string;
  title: string;
  status: string;
  href?: string;
  category?: string;
}

export interface WorkbenchView {
  greeting: string;
  subtitle: string;
  todos: WorkbenchTodo[];
  highlights: string[];
  aiSummary: {
    summary: string;
    actions?: string[];
    basis?: string[];
  };
}

export const WORKBENCH_FIXTURE: WorkbenchView = {
  // R-004（#258 复审）：虚构人物名退役。离线 fixture 无会话身份可带出 → 通用问候，
  // 不捏造姓名头衔；live 路径问候语由后端按 actor_snapshot.display_name 现算。
  greeting: '您好',
  subtitle:
    '你有 1 条停车场信息复用申请待看进度；本周共有 10 条真实政务案例可被订阅；1 条减负提示来自约 1.8 万条 组织表数据。',
  todos: [
    {
      id: 'REQ-2026-04-25-0011',
      title: '停车场信息共享目录复用申请进入受控准入',
      status: '审批中',
      href: '#/request-flow/request/REQ-2026-04-25-0011',
    },
    // 专题包待办随专题包退出本期而移除（D55/P6）：dev fallback fixture 不留指向已下线路由的死链。
    {
      id: 'REQ-2026-04-24-0007',
      title: '专项摸排任务退回补充',
      status: '待修改',
      href: '#/request-flow/request/REQ-2026-04-24-0007',
    },
  ],
  highlights: [
    '本周 3 条涉企需求被拦截为「先复用模板再补差异字段」',
    '停车场信息共享目录已覆盖库表 / 文件资源',
    '营商环境专题建议先用共享底座再发起差异采集',
    '本次任务已自动带出企业基础字段 12 项',
    '仅需补录 3 项现场差异字段',
  ],
  aiSummary: {
    summary:
      '建议你先跟进"停车场信息共享目录复用申请"，因为这条链已经具备真实目录、审批口径清楚，最快能验证"先复用后补录"的黄金旅程。',
    actions: ['查看模板覆盖率', '查看差异字段清单', '进入申请进度'],
    basis: [
      '当前需求命中涉企基础信息高频字段',
      '模板已被多个专题包复用',
      '差异字段只剩现场经营状态与走访备注',
    ],
  },
};
