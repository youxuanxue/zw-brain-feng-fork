// F7 fixture：live page-anchor→skill 映射失败时的最终兜底（dev / 离线演示）。
// 主路径见 lib/nlAcceleratorRouting.ts；此处保留 preset 样例供回落对齐。

export type StructuredActionKind = 'filter' | 'navigate' | 'invoke' | 'draft';

export interface StructuredAction {
  kind: StructuredActionKind;
  label: string;
  detail?: string;
  // 'filter'  → 主页面 emit 接住后应用到表格过滤
  // 'navigate'→ hash route
  // 'invoke'  → skill_id（与 useActionStub 协同）
  // 'draft'   → 草稿 form 预填 payload
  target?: string;
  payload?: Record<string, unknown>;
}

export interface NLAcceleratorParseResult {
  summary: string;
  parse_status: 'ok' | 'partial' | 'pending';
  actions: StructuredAction[];
}

// 4 个 page anchor 各 3 preset → fixture parse 结果。
// 真后端 land 后这份只剩 dev 兜底用；E1/E3/E4 应回返同 schema 的结构化结果。
export const NL_ACCELERATOR_FIXTURES: Record<string, Record<string, NLAcceleratorParseResult>> = {
  P2: {
    '查省营商环境相关数据': {
      summary: '已找到 3 个营商环境主题资源，建议先复用「停车场信息共享目录」',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '应用主题筛选：营商环境', target: 'zone', payload: { zone: '营商环境专区' } },
        // 「跳到营商环境专题包」导航随专题包退出本期而移除（D55/P6）：dev fixture 不留死链。
        { kind: 'invoke', label: '查模板覆盖率（catalog.entry.query）', target: 'catalog.entry.query', payload: { tag: '营商环境' } },
      ],
    },
    '近 7 天高使用资源': {
      summary: '本周订阅量 Top 3：停车场 / 营商环境基础 / 城市运行',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '按订阅量降序排序', target: 'sort', payload: { by: 'subscribers', dir: 'desc' } },
        { kind: 'filter', label: '时间窗口：近 7 天', target: 'time_window', payload: { days: 7 } },
      ],
    },
    '关联水电气交叉数据': {
      summary: '当前未命中水电气交叉数据；可在「找数据」按主题检索关联资源',
      parse_status: 'partial',
      // 「跳到营商环境专题」导航随专题包退出本期而移除（D55/P6）：dev fixture 不留死链。
      actions: [],
    },
  },
  P3: {
    '我待审的有几条': {
      summary: '当前 5 条在途申请，其中 2 条等待你审批',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '只显示「待我审批」', target: 'mine_pending', payload: { stage: 'pending_review' } },
        { kind: 'invoke', label: '一键拉审批队列', target: 'approval.view', payload: {} },
      ],
    },
    '催办昨天提交的申请': {
      summary: '昨天提交 1 条「停车场信息复用」尚未审批',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '时间窗口：昨日', target: 'time_window', payload: { date: 'yesterday' } },
        { kind: 'invoke', label: '触发催办通知', target: 'request.submit', payload: { reminder: true } },
      ],
    },
    '驳回所有 30 天未跟进': {
      summary: '识别到 1 条 30 天未跟进；驳回前需人工确认',
      parse_status: 'partial',
      actions: [
        { kind: 'filter', label: '过滤：≥30 天未跟进', target: 'stale_only', payload: { days: 30 } },
        { kind: 'draft', label: '草拟批量驳回意见（需人工 confirm）', target: 'approval.case.decide', payload: { decision: 'rejected' } },
      ],
    },
  },
  'B1.1': {
    '看本周高风险异议': {
      summary: '本周高风险异议 0 条；近 24h 一般异议 1 条',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '风险等级：高', target: 'risk', payload: { level: 'high' } },
        { kind: 'filter', label: '时间窗口：本周', target: 'time_window', payload: { week: 'current' } },
      ],
    },
    '近 24h 审计失败': {
      summary: '近 24h 审计写入失败 0 条；护栏正常',
      parse_status: 'ok',
      actions: [
        { kind: 'invoke', label: '查审计写入失败日志', target: 'audit.list', payload: { status: 'failed', window_hours: 24 } },
      ],
    },
    '溯源 REQ-2026-04-25-0011': {
      summary: '已定位申请单据；点击查看完整审计链',
      parse_status: 'ok',
      actions: [
        { kind: 'navigate', label: '跳到申请详情', target: '#/request-flow/request/REQ-2026-04-25-0011' },
        { kind: 'invoke', label: '查审计回放', target: 'audit.replay_evidence_chain', payload: { request_id: 'REQ-2026-04-25-0011' } },
      ],
    },
  },
  'B1.2': {
    '未注册能力包': {
      summary: '当前 0 个注册中；3 个待审外部能力包',
      parse_status: 'ok',
      actions: [
        { kind: 'filter', label: '状态：待审', target: 'trust_level', payload: { trust_level: 'untrusted' } },
        { kind: 'invoke', label: '查注册队列', target: 'capability.version.review', payload: {} },
      ],
    },
    '近 7 天 IAM 失败': {
      summary: '近 7 天 IAM 鉴权失败 0 条；接入正常',
      parse_status: 'ok',
      actions: [
        { kind: 'navigate', label: '跳身份治理面板', target: '#/integration-admin/iam-governance' },
      ],
    },
    '看接入故障': {
      summary: '当前接入故障 0；展示最近接入审核记录',
      parse_status: 'ok',
      actions: [
        { kind: 'invoke', label: '查最近接入审核', target: 'capability.version.review', payload: { window_days: 7 } },
      ],
    },
  },
};

export function getFixtureFor(pageAnchor: string, query: string): NLAcceleratorParseResult | null {
  const bucket = NL_ACCELERATOR_FIXTURES[pageAnchor];
  if (!bucket) return null;
  if (bucket[query]) return bucket[query];
  // 模糊匹配：包含关键词的 preset；否则返回 pending 提示
  const norm = query.trim();
  for (const key of Object.keys(bucket)) {
    if (key.includes(norm) || norm.includes(key)) return bucket[key];
  }
  return null;
}
