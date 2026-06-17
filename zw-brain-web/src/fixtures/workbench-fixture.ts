// 与 zw_brain/domain/seed_snapshot.json::workbench.ROLE_ORGAN_OPERATER 同源切片。
// 仅在后端 /api/skills/workbench.view 不可达（开发期未启 brain server）时兜底。
// 真实部署一定走 API，不读这份 fixture。
//
// 数据范围：sd-default 单租户单角色（部门操作员）；F2/F3 阶段移除或归并到 dev-server stub。

/**
 * 行内决策契约（后端 workbench.view 投影按需附带，前端只消费）：
 * 当一条待办带 `action` 时，工作台行可就地展开一个小决策面，用户在工作台内
 * 看要点、点办理，不必跳出 #/workbench。无 action 的待办仍走原 href 深链。
 *
 * 自门控纪律：行内按钮不经路由守卫，必须自行用 canPerformAction(gate, role) 判可见
 * （无权 = 不渲染按钮，承「无权即不可见」）。
 */
export interface WorkbenchTodoDecision {
  /** 按钮文案（白话，禁工程术语）。 */
  label: string;
  /** 复用 .gov-btn-primary/-secondary/-danger 的色调。 */
  tone: 'primary' | 'secondary' | 'danger';
  /** 成功后 toast 标题。 */
  success: string;
  /** 本决策独有的入参，与 basePayload 合并后下发。 */
  payload: Record<string, unknown>;
  /** 可选：本决策单独的能力 skillId（不填则回落所在 item / action 的 capability）。
   *  聚合待办里同一条记录可能有「通过」与「下线」等走不同 capability 的决策。 */
  capability?: string;
  /** 可选：本决策单独的能力门（不填则回落所在 item / action 的 gate）。 */
  gate?: string;
  /** 可选：点击后先展开理由框、填写确认再下发（如「驳回」需说明依据）。 */
  needsReason?: boolean;
  /** needsReason 时理由值合并进 payload 的键名，默认 'reason'（驳回类常用 'reject_reason'）。 */
  reasonKey?: 'reason' | 'reject_reason';
}

/** 聚合待办（decision-list）里的一条可逐条办理的记录。 */
export interface WorkbenchTodoActionItem {
  /** 行内唯一键（如资源编码 / 申请单号），用于展开态、理由框定位。 */
  id: string;
  /** 该条记录的标题（白话）。 */
  label: string;
  /** 该条记录的要点行（<=6 行），紧凑展示。 */
  context: { label: string; value: string }[];
  /** 该条记录下发的默认能力 skillId（决策可各自覆盖）。 */
  capability: string;
  /** 该条记录的默认能力门（决策可各自覆盖 gate）。 */
  gate: string;
  /** 合并进每次决策调用的公共入参，例如 { resource_code }。 */
  basePayload: Record<string, unknown>;
  /** 该条记录的一个或多个决策按钮。 */
  decisions: WorkbenchTodoDecision[];
}

/**
 * 行内决策有两种形态（discriminated union，以 kind 区分）：
 *   - 'decision'：单条记录，几行要点 + 通过/驳回类按钮（M1 已实现，本类型不变）。
 *   - 'decision-list'：聚合待办（如「待发布资源 4 条」），展开成逐条记录，每条就地办理。
 */
export interface WorkbenchTodoActionSingle {
  kind: 'decision';
  /** 真正下发的能力 skillId，例如 application.dept_approve。 */
  capability: string;
  /** 传给 canPerformAction(gate, role) 的能力门（通常同 capability）。 */
  gate: string;
  /** 合并进每次决策调用的公共入参，例如 { request_id }。 */
  basePayload: Record<string, unknown>;
  /** 决策面要点行（<=6 行）。 */
  context: { label: string; value: string }[];
  /** 一个或多个决策按钮。 */
  decisions: WorkbenchTodoDecision[];
}

export interface WorkbenchTodoActionList {
  kind: 'decision-list';
  /** 聚合待办展开后的逐条记录，每条独立办理。 */
  items: WorkbenchTodoActionItem[];
}

export type WorkbenchTodoAction = WorkbenchTodoActionSingle | WorkbenchTodoActionList;

export interface WorkbenchTodo {
  id: string;
  title: string;
  status: string;
  href?: string;
  category?: string;
  /** 可选：带上后，符合权限的行可就地展开办理（见 WorkbenchTodoAction）。 */
  action?: WorkbenchTodoAction;
}

export interface WorkbenchView {
  greeting: string;
  subtitle: string;
  todos: WorkbenchTodo[];
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
    // 行内办理示例（部门管理员二级审核）：带 action 的待办可在工作台内就地展开决策面，
    // 不必跳出 #/workbench。href 仍保留作回退深链（无权岗位看不到办理面、仍可点链进详情）。
    {
      id: 'REQ-2026-04-26-0015',
      title: '人口基础信息共享目录复用申请待部门审核',
      status: '待部门审核',
      href: '#/request-flow/request/REQ-2026-04-26-0015',
      action: {
        kind: 'decision',
        capability: 'application.dept_approve',
        gate: 'application.dept_approve',
        basePayload: { request_id: 'REQ-2026-04-26-0015' },
        context: [
          { label: '资源', value: '人口基础信息共享目录' },
          { label: '申请人', value: '市民政局' },
          { label: '用途', value: '低保资格联审，比对人口基础信息' },
          { label: '共享方式', value: '有条件共享' },
          { label: '当前状态', value: '待部门审核' },
        ],
        decisions: [
          {
            label: '审核通过',
            tone: 'primary',
            success: '审核通过（已授权）',
            payload: { decision: 'approve' },
          },
          {
            label: '驳回',
            tone: 'danger',
            success: '部门审核驳回',
            payload: { decision: 'reject' },
          },
        ],
      },
    },
    // 聚合行内办理示例（decision-list）：一条「待发布资源」汇总待办在工作台内展开成
    // 逐条记录，每条就地通过 / 退回，不必逐个跳详情页。驳回带理由（reject_reason）。
    {
      id: 'WB-RES-PUBLISH-PENDING',
      title: '待发布资源 2 条',
      status: '待发布',
      action: {
        kind: 'decision-list',
        items: [
          {
            id: 'res-2026-0207',
            label: '市场主体登记基础信息（库表）',
            capability: 'resource.asset.publish',
            gate: 'resource.asset.publish',
            basePayload: { resource_code: 'res-2026-0207' },
            context: [
              { label: '资源形态', value: '库表' },
              { label: '所属目录', value: '涉企基础信息共享目录' },
              { label: '共享类型', value: '有条件共享' },
            ],
            decisions: [
              {
                label: '发布',
                tone: 'primary',
                success: '资源已发布',
                payload: { decision: 'publish' },
              },
              {
                label: '退回',
                tone: 'danger',
                success: '已退回提交方整改',
                payload: { decision: 'return_for_fix' },
                needsReason: true,
                reasonKey: 'reject_reason',
              },
            ],
          },
          {
            id: 'res-2026-0211',
            label: '不动产登记结果信息（文件）',
            capability: 'resource.asset.publish',
            gate: 'resource.asset.publish',
            basePayload: { resource_code: 'res-2026-0211' },
            context: [
              { label: '资源形态', value: '文件' },
              { label: '所属目录', value: '不动产登记共享目录' },
              { label: '共享类型', value: '有条件共享' },
            ],
            decisions: [
              {
                label: '发布',
                tone: 'primary',
                success: '资源已发布',
                payload: { decision: 'publish' },
              },
              {
                label: '退回',
                tone: 'danger',
                success: '已退回提交方整改',
                payload: { decision: 'return_for_fix' },
                needsReason: true,
                reasonKey: 'reject_reason',
              },
            ],
          },
        ],
      },
    },
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
