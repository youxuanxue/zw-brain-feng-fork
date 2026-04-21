/* ---------------------------------------------------------------------------
   政务大脑 GATE-1 原型 · mock 数据
   原则：只承载方向验证所必需的最小数据；不模拟边界 / 错误 / 大数据量
   --------------------------------------------------------------------------- */

// ============================================================
// 场景 1：共享专区数据集 + 申请 + 我的工作台
// ============================================================
window.MOCK_DATASETS = [
  {
    id: 'ds-mzj-immune',
    name: '免疫规划接种数据集（市级）',
    provider: '市卫健委',
    providerOwner: '陈科长',
    zone: '健康专区',
    fields: [
      { name: '接种日期',  type: 'date',     desensitized: false },
      { name: '疫苗类型',  type: 'enum',     desensitized: false },
      { name: '区县',      type: 'enum',     desensitized: false },
      { name: '年龄段',    type: 'enum',     desensitized: false, note: '已脱敏，不含个人标识' },
      { name: '剂次',      type: 'int',      desensitized: false },
    ],
    updatedAt: '2026-04-15',
    approvalRate: 0.92,
    subscriberCount: 17,
    subscribers: ['市发改委', '市统计局', '市疾控中心', '省卫健委', '...等 14 个'],
    desc: '本市预防接种系统按月汇聚，已按个人标识脱敏。可用于公共卫生分析、疫苗供需预测、营商环境健康指标。'
  },
  {
    id: 'ds-mzj-hospital',
    name: '医疗机构基础信息',
    provider: '市卫健委',
    providerOwner: '陈科长',
    zone: '健康专区',
    fields: [
      { name: '机构名称', type: 'str' }, { name: '等级', type: 'enum' },
      { name: '床位数', type: 'int' },   { name: '所在区县', type: 'enum' }
    ],
    updatedAt: '2026-04-10', approvalRate: 0.98, subscriberCount: 23,
    desc: '全市医疗机构静态信息，月度同步。'
  },
  {
    id: 'ds-cdc-flu',
    name: '流感样病例周报（脱敏）',
    provider: '市疾控中心',
    providerOwner: '张主任',
    zone: '健康专区',
    fields: [
      { name: '统计周', type: 'str' }, { name: '区县', type: 'enum' },
      { name: '样本量', type: 'int' }, { name: '阳性率', type: 'float' }
    ],
    updatedAt: '2026-04-14', approvalRate: 0.88, subscriberCount: 9,
    desc: '基于哨点医院的流感监测周报。'
  },
  {
    id: 'ds-mzj-relief',
    name: '城乡低保救助金发放台账',
    provider: '市民政局',
    providerOwner: '刘科长',
    zone: '民生保障专区',
    fields: [
      { name: '发放周期',   type: 'str' },
      { name: '区县',       type: 'enum' },
      { name: '救助类别',   type: 'enum' },
      { name: '发放笔数',   type: 'int' },
      { name: '发放金额',   type: 'decimal', note: '万元' },
      { name: '受益人群分类', type: 'enum',  note: '已脱敏，仅按年龄段 / 困难类别分组' },
    ],
    updatedAt: '2026-04-16',
    approvalRate: 0.95,
    subscriberCount: 22,
    subscribers: ['市发改委', '市统计局', '市财政局', '省民政厅', '...等 19 个'],
    desc: '本市城乡低保 / 特困供养 / 临时救助月度发放台账，已按个人标识脱敏。常用于民生支出分析、节假日资金调度。'
  }
];

// 已提交的申请（场景 1 状态页 + 工作台「我的待办」用）
window.MOCK_REQUESTS = [
  {
    id: 'REQ-2026-04-11-0042',
    datasetId: 'ds-mzj-hospital',
    datasetName: '医疗机构基础信息',
    applicant: '李娟（市发改委）',
    applicantDept: '市发改委综合处',
    purpose: '营商环境季度报告，附件 OA-2026-Q2-009',
    range: '2024-01-01 ~ 2024-12-31',
    expectBy: '2026-04-13',
    status: 'approved',
    submittedAt: '2026-04-11 09:23',
    approvedAt:  '2026-04-12 14:01',
    auditId:     'AE-7c1a9f3b',
    chainAnchor: '0xa3f2c91d8e7b...c91',
  }
];

// 我的待办（场景 1 工作台用，扮演「提供方管理员」角色时显示）
window.MOCK_TODO_REVIEWS = [
  {
    id: 'REQ-2026-04-17-0061',
    applicant: '市统计局 林处长',
    applicantDept: '市统计局综合统计处',
    datasetId: 'ds-mzj-immune',
    dataset: '免疫规划接种数据集（市级）',
    purpose: '编制 2026 一季度公共卫生统计公报，附件 OA-2026-Q1-208',
    range: '2026-01-01 ~ 2026-03-31',
    expectBy: '2026-04-19',
    submittedAt: '2026-04-17 16:42',
    urgent: true,
    historyApprovedFromSameDept: 8,
    historyRejectedFromSameDept: 0,
  },
  {
    id: 'REQ-2026-04-18-0072',
    applicant: '省卫健委 数据中心',
    applicantDept: '省卫健委统计信息中心',
    datasetId: 'ds-mzj-hospital',
    dataset: '医疗机构基础信息',
    purpose: '更新省级医疗机构台账，年度刷新',
    range: '2026-04-01 ~ 2026-04-18',
    expectBy: '2026-04-25',
    submittedAt: '2026-04-18 09:17',
    urgent: false,
    historyApprovedFromSameDept: 35,
    historyRejectedFromSameDept: 1,
  },
];

// ============================================================
// 场景 2：大屏指挥中心数据
// ============================================================

// 24 小时数据流通量（柱+折线）
window.MOCK_DASHBOARD_FLOW = (function () {
  const hours = [];
  const flow  = [];
  const now   = new Date();
  for (let i = 23; i >= 0; i--) {
    const h = new Date(now.getTime() - i * 3600 * 1000);
    hours.push(`${String(h.getHours()).padStart(2, '0')}:00`);
    // 模拟工作时段高峰（14 点）
    const base = h.getHours() >= 9 && h.getHours() <= 17 ? 800 : 200;
    flow.push(base + Math.floor(Math.random() * 600) + (h.getHours() === 14 ? 400 : 0));
  }
  return { hours, flow };
})();

// Skill 调用 QPS 滚动趋势
window.MOCK_DASHBOARD_QPS = (function () {
  const arr = [];
  for (let i = 0; i < 30; i++) arr.push(40 + Math.floor(Math.random() * 30));
  return { current: 47, peakToday: 156, trend: arr };
})();

window.MOCK_DASHBOARD_SUMMARY = {
  agentsOnline: 23,
  provincialChannel: 'ok',     // 省厅通道
  nationalChannel:   'ok',     // 国家通道
  alerts: [
    {
      id: 'AL-7732',
      severity: 'mid',
      skill: 'compliance.audit',
      summary: 'P99 响应时间 920ms（阈值 800ms）',
      since: '13:42',
      diagnosis: '今日审计量同比 +60%，触发慢查询；建议为 audit_event.actor_id 加索引。',
      ticket: '—'
    },
    {
      id: 'AL-7733',
      severity: 'mid',
      skill: 'national.relay.upload',
      summary: '国家平台侧响应慢（>3s）',
      since: '13:51',
      diagnosis: '国家共享平台侧上行通道拥塞；本侧无故障；已开工单。',
      ticket: 'GW-7732'
    }
  ],
  aiSuggestion: {
    title: '检测到「市民政局救助金发放」Skill 调用激增',
    body: '过去 6 小时被调用 412 次（同比 +180%），可能与即将到来的清明节救助金集中发放有关。',
    actions: [
      '临时提升该 Skill 的资源池配额至 2 倍（预计成本：+18 元/小时）',
      '通知值班管理员关注审批积压（目前队列已积 47 条）'
    ],
    confidence: 0.86,
    basedOn: ['skill.invocation.stats(t-6h)', 'calendar.holiday(2026-04-05)', 'historical.pattern(2025-04)']
  }
};

// ============================================================
// 场景 3：Agent 入口的 Skill 注册表（MCP 视角）
// 选取覆盖 K1-K12 主要写/读路径的代表性 Skill；不全列以避免目录页过长
// ============================================================
window.MOCK_SKILLS = [
  // -------- catalog 域（K1） --------
  {
    id: 'catalog.search', domain: 'catalog', kCovers: ['K1'],
    desc: '按关键词、领域、提供方等条件检索数据目录',
    version: '1.2.0', stability: 'stable',
    subscriberCount: 142, owner: '平台 / 数据治理组',
    inputSchema: {
      type: 'object',
      required: ['q'],
      properties: {
        q:        { type: 'string', description: '检索关键词或自然语言短句', example: '低保' },
        zone:     { type: 'string', description: '可选：限定到某个共享专区', example: '民生保障专区' },
        topK:     { type: 'integer', default: 10, description: '返回前 K 条' }
      }
    },
    outputSchema: {
      type: 'object',
      properties: {
        items: { type: 'array', items: { type: 'object', properties: {
          id: { type: 'string' }, name: { type: 'string' }, provider: { type: 'string' },
          score: { type: 'number' }
        }}}
      }
    }
  },
  {
    id: 'catalog.register', domain: 'catalog', kCovers: ['K1'],
    desc: '把一份新的表 / 文件 / 接口注册成共享目录（写操作，触发审计 + 上链）',
    version: '1.0.3', stability: 'stable',
    subscriberCount: 31, owner: '平台 / 数据治理组', isWrite: true,
    inputSchema: {
      type: 'object', required: ['name', 'provider', 'resource_type', 'resource_ref'],
      properties: {
        name:          { type: 'string',  example: '免疫规划接种数据集（市级）' },
        provider:      { type: 'string',  example: '市卫健委' },
        resource_type: { type: 'string',  enum: ['table', 'file', 'api'] },
        resource_ref:  { type: 'string',  description: '指向 K2 资源的 URI', example: 'res://hubei/cdc/immune_v3' },
        zone_tag:      { type: 'string',  description: '可选：归属共享专区', example: '健康专区' }
      }
    },
    outputSchema: { type: 'object', properties: { catalog_id: { type: 'string' }, audit_id: { type: 'string' }, chain_anchor: { type: 'string' } } }
  },
  // -------- resource 域（K2 + K3） --------
  {
    id: 'service.publish', domain: 'resource', kCovers: ['K3'],
    desc: '把已注册目录发布为可用 API（写操作）',
    version: '1.1.0', stability: 'stable',
    subscriberCount: 19, owner: '平台 / 融合服务组', isWrite: true,
    inputSchema: {
      type: 'object', required: ['catalog_id', 'auth_policy'],
      properties: {
        catalog_id:  { type: 'string',  example: 'cat-mzj-immune' },
        auth_policy: { type: 'string',  enum: ['ticket', 'oauth', 'cert'] },
        rate_limit:  { type: 'integer', default: 100, description: 'req/min' }
      }
    },
    outputSchema: { type: 'object', properties: { service_url: { type: 'string' }, audit_id: { type: 'string' } } }
  },
  // -------- request 域（K4） --------
  {
    id: 'request.submit', domain: 'request', kCovers: ['K4'],
    desc: '提交一条数据使用申请（写操作，触发审计 + 上链）',
    version: '1.1.0', stability: 'stable',
    subscriberCount: 67, owner: '平台 / 申请审批组',
    isWrite: true,
    inputSchema: {
      type: 'object', required: ['dataset_id', 'purpose', 'use_dept'],
      properties: {
        dataset_id: { type: 'string' },
        purpose:    { type: 'string', minLength: 10 },
        use_dept:   { type: 'string' },
        range:      { type: 'object' },
        expect_by:  { type: 'string', format: 'date' }
      }
    },
    outputSchema: {
      type: 'object',
      properties: {
        request_id:   { type: 'string' },
        audit_id:     { type: 'string' },
        chain_anchor: { type: 'string', description: '异步锚定，可能初始为 pending' }
      }
    }
  },
  {
    id: 'request.review', domain: 'request', kCovers: ['K4'],
    desc: '提供方对申请做出审批决定（通过 / 驳回 / 补正），写操作',
    version: '1.0.2', stability: 'stable',
    subscriberCount: 24, owner: '平台 / 申请审批组', isWrite: true,
    inputSchema: {
      type: 'object', required: ['request_id', 'decision'],
      properties: {
        request_id: { type: 'string', example: 'REQ-2026-04-17-0061' },
        decision:   { type: 'string', enum: ['approve', 'reject', 'request_changes'] },
        reason:     { type: 'string', description: 'reject / request_changes 时必填' }
      }
    },
    outputSchema: { type: 'object', properties: { status: { type: 'string' }, audit_id: { type: 'string' } } }
  },
  {
    id: 'request.status.query', domain: 'request', kCovers: ['K4'],
    desc: '按 request_id 查询数据申请的当前状态、审批人、预计完成时间',
    version: '1.0.4', stability: 'stable',
    subscriberCount: 89, owner: '平台 / 申请审批组',
    inputSchema: {
      type: 'object', required: ['request_id'],
      properties: { request_id: { type: 'string', example: 'REQ-2026-04-18-0073' } }
    },
    outputSchema: {
      type: 'object',
      properties: {
        status:       { type: 'string', enum: ['pending', 'approved', 'rejected', 'in_exchange', 'delivered'] },
        approved_at:  { type: 'string', format: 'date-time' },
        approver:     { type: 'string' },
        data_url:     { type: 'string', description: '仅 status=delivered 时存在' }
      }
    }
  },
  // -------- exchange 域（K5） --------
  {
    id: 'exchange.run', domain: 'exchange', kCovers: ['K5'],
    desc: '为已审批的申请配置增量 / 全量数据交换任务并启动（写操作）',
    version: '1.0.1', stability: 'stable',
    subscriberCount: 17, owner: '平台 / 数据交换组', isWrite: true,
    inputSchema: {
      type: 'object', required: ['request_id', 'mode'],
      properties: {
        request_id: { type: 'string', example: 'REQ-2026-04-11-0042' },
        mode:       { type: 'string', enum: ['incremental', 'full'] },
        cron:       { type: 'string', description: 'incremental 时建议提供', example: '0 2 * * *' }
      }
    },
    outputSchema: { type: 'object', properties: { task_id: { type: 'string' }, audit_id: { type: 'string' } } }
  },
  // -------- compliance 域（K8） --------
  {
    id: 'compliance.audit', domain: 'compliance', kCovers: ['K8'],
    desc: '按时间窗口 / 主体 / 数据集查询审计事件（K9 审计总线只读视图）',
    version: '1.3.0', stability: 'stable',
    subscriberCount: 41, owner: '平台 / 合规督导组', readOnly: true,
    inputSchema: {
      type: 'object',
      properties: {
        actor_id:   { type: 'string', description: '主体 ID（人 / Agent / 部门）' },
        from:       { type: 'string', format: 'date-time' },
        to:         { type: 'string', format: 'date-time' },
        dataset_id: { type: 'string' }
      }
    },
    outputSchema: { type: 'object', properties: { events: { type: 'array' }, total: { type: 'integer' } } }
  },
  {
    id: 'dispute.handle', domain: 'compliance', kCovers: ['K8'],
    desc: '处理一条数据使用异议（写操作；可触发回收 / 整改 / 升级）',
    version: '0.9.4', stability: 'beta',
    subscriberCount: 8, owner: '平台 / 合规督导组', isWrite: true,
    inputSchema: {
      type: 'object', required: ['dispute_id', 'action'],
      properties: {
        dispute_id: { type: 'string' },
        action:     { type: 'string', enum: ['accept', 'escalate', 'reject', 'request_revoke'] },
        note:       { type: 'string' }
      }
    },
    outputSchema: { type: 'object', properties: { status: { type: 'string' }, audit_id: { type: 'string' } } }
  },
  // -------- national 域（K7） --------
  {
    id: 'national.relay.query', domain: 'national', kCovers: ['K7'],
    desc: '查询国家共享平台下行任务状态（只读）',
    version: '0.9.1', stability: 'beta',
    subscriberCount: 12, owner: '平台 / 国家通道组', readOnly: true,
    inputSchema: { type: 'object', required: ['task_id'], properties: { task_id: { type: 'string' } } },
    outputSchema: { type: 'object', properties: { status: { type: 'string' }, progress: { type: 'number' } } }
  },
  // -------- zone 域（K11） --------
  {
    id: 'zone.subscribe', domain: 'zone', kCovers: ['K11'],
    desc: '订阅共享专区，新数据集发布时收到事件推送',
    version: '1.0.0', stability: 'stable',
    subscriberCount: 38, owner: '平台 / 共享专区组',
    isWrite: true,
    inputSchema: { type: 'object', required: ['zone_id'], properties: { zone_id: { type: 'string' } } },
    outputSchema: { type: 'object', properties: { subscription_id: { type: 'string' } } }
  },
  // -------- dashboard 域（K12） --------
  {
    id: 'dashboard.realtime', domain: 'dashboard', kCovers: ['K12'],
    desc: '聚合大屏所需实时指标（数据流通量 / Skill QPS / Agent 在线数 / 国家通道 / 异常）',
    version: '1.0.0', stability: 'stable',
    subscriberCount: 5, owner: '平台 / 大屏组',
    readOnly: true,
    inputSchema: { type: 'object', properties: {} },
    outputSchema: { type: 'object', properties: {
      flow_24h: { type: 'array' }, qps_current: { type: 'integer' }, agents_online: { type: 'integer' },
      provincial_channel: { type: 'string' }, national_channel: { type: 'string' }, alerts: { type: 'array' }
    }}
  },
];

// ============================================================
// §7.3 第 3 页：资源管理（catalog/resource/service 三栏）
// ============================================================
window.MOCK_RESOURCES = [
  { id: 'res-mzj-immune-v3',  name: 'imm_record_v3',         type: 'table', source: 'PostgreSQL', dsn: 'pg://hubei/cdc/db1', state: 'connected',  lastProbeAt: '2026-04-18 06:00', rowCount: 8_421_902, owner: '市卫健委' },
  { id: 'res-mzj-hospital',   name: 'hospital_master',       type: 'table', source: 'MySQL',      dsn: 'mysql://hubei/health/db', state: 'connected', lastProbeAt: '2026-04-18 06:00', rowCount: 2_104, owner: '市卫健委' },
  { id: 'res-cdc-flu',        name: 'flu_weekly_xlsx',       type: 'file',  source: 'OSS',        dsn: 'oss://gov-share/cdc/flu/2026/', state: 'connected', lastProbeAt: '2026-04-18 06:00', rowCount: 18, owner: '市疾控中心' },
  { id: 'res-mzj-relief',     name: 'relief_ledger',         type: 'table', source: 'PostgreSQL', dsn: 'pg://hubei/civil/db', state: 'connected',  lastProbeAt: '2026-04-18 06:00', rowCount: 3_217_440, owner: '市民政局' },
  { id: 'res-cdc-flu-api',    name: 'flu-realtime-api',      type: 'api',   source: 'HTTP',       dsn: 'https://internal.gov.local/cdc/flu/realtime', state: 'degraded', lastProbeAt: '2026-04-18 06:00', rowCount: null, owner: '市疾控中心' },
];

window.MOCK_SERVICES = [
  { id: 'svc-immune-query',   name: 'immune-query',          catalogId: 'ds-mzj-immune',  url: 'https://api.gov.local/share/immune/v1', auth: 'ticket', rateLimit: 200, qpsNow: 47,  publishedAt: '2026-04-02', state: 'live'   },
  { id: 'svc-hospital-list',  name: 'hospital-list',         catalogId: 'ds-mzj-hospital', url: 'https://api.gov.local/share/hospital/v1', auth: 'oauth', rateLimit: 100, qpsNow: 12,  publishedAt: '2026-03-18', state: 'live'   },
  { id: 'svc-relief-monthly', name: 'relief-monthly',        catalogId: 'ds-mzj-relief',  url: 'https://api.gov.local/share/relief/v1', auth: 'cert',  rateLimit: 60,  qpsNow: 8,   publishedAt: '2026-04-10', state: 'live'   },
  { id: 'svc-flu-weekly',     name: 'flu-weekly',            catalogId: 'ds-cdc-flu',     url: 'https://api.gov.local/share/flu/v1',     auth: 'ticket', rateLimit: 50,  qpsNow: 0,   publishedAt: '2026-04-14', state: 'paused' },
];

// ============================================================
// §7.3 第 5 页：数据交换任务
// ============================================================
window.MOCK_EXCHANGE_TASKS = [
  {
    id: 'EX-2026-Q2-014',
    requestId: 'REQ-2026-04-11-0042',
    datasetId: 'ds-mzj-hospital',
    datasetName: '医疗机构基础信息',
    consumer: '市发改委综合处',
    mode: 'incremental', cron: '0 2 * * *',
    state: 'healthy',
    lastRunAt: '2026-04-18 02:00:13',
    lastBytes: 2.4 * 1024 * 1024,
    lastDurationMs: 1820,
    history: [
      { at: '2026-04-18 02:00', ok: true,  bytes: 2.4*1024*1024, ms: 1820 },
      { at: '2026-04-17 02:00', ok: true,  bytes: 2.5*1024*1024, ms: 1745 },
      { at: '2026-04-16 02:00', ok: true,  bytes: 2.3*1024*1024, ms: 1910 },
      { at: '2026-04-15 02:00', ok: true,  bytes: 2.4*1024*1024, ms: 1788 },
      { at: '2026-04-14 02:00', ok: false, bytes: 0,             ms: 0, err: '上游连接超时' },
      { at: '2026-04-13 02:00', ok: true,  bytes: 2.2*1024*1024, ms: 2010 },
    ]
  },
  {
    id: 'EX-2026-Q2-018',
    requestId: 'REQ-2026-04-08-0033',
    datasetId: 'ds-mzj-immune',
    datasetName: '免疫规划接种数据集（市级）',
    consumer: '市统计局综合统计处',
    mode: 'full', cron: '—',
    state: 'failed',
    lastRunAt: '2026-04-17 14:22',
    lastBytes: 0,
    lastDurationMs: 8120,
    history: [
      { at: '2026-04-17 14:22', ok: false, bytes: 0, ms: 8120, err: 'audit_event 写入失败 → 终止（D4 上半熔断）' },
      { at: '2026-04-15 09:08', ok: true,  bytes: 41*1024*1024, ms: 6240 },
    ]
  },
  {
    id: 'EX-2026-Q2-021',
    requestId: 'REQ-2026-04-12-0058',
    datasetId: 'ds-mzj-relief',
    datasetName: '城乡低保救助金发放台账',
    consumer: '市财政局预算处',
    mode: 'incremental', cron: '0 3 1 * *',
    state: 'healthy',
    lastRunAt: '2026-04-01 03:00:42',
    lastBytes: 8.7 * 1024 * 1024,
    lastDurationMs: 4210,
    history: [
      { at: '2026-04-01 03:00', ok: true, bytes: 8.7*1024*1024, ms: 4210 },
      { at: '2026-03-01 03:00', ok: true, bytes: 8.5*1024*1024, ms: 4187 },
    ]
  },
];

// ============================================================
// §7.3 第 6 页：异议处理
// ============================================================
window.MOCK_DISPUTES = [
  {
    id: 'DSP-2026-04-15-007',
    requestId: 'REQ-2026-04-08-0033',
    datasetId: 'ds-mzj-immune',
    datasetName: '免疫规划接种数据集（市级）',
    raisedBy: '市统计局 林处长',
    raisedDept: '市统计局',
    raisedAt: '2026-04-15 10:42',
    status: 'open',
    severity: 'mid',
    summary: '2024 Q4 数据中 3 个区县字段（黄陂区 / 蔡甸区 / 江夏区）记录缺失',
    detail: '比对 2024 Q1-Q3 平均每月 23 万条，2024-12 仅 8 万条；缺失部分疑似采集端数据延迟未补齐。已联系市卫健委信息中心。',
    suggestion: '请提供方在 3 个工作日内补送 2024-10 至 2024-12 的完整记录，或正式说明缺失原因并出具数据可用性声明。',
    timeline: [
      { at: '2026-04-15 10:42', actor: '林处长',   action: '提交异议' },
      { at: '2026-04-15 16:08', actor: '陈科长',   action: '已查证：12 月数据延迟入库，正在补采，预计 4-19 完成' },
    ]
  },
  {
    id: 'DSP-2026-04-12-004',
    requestId: 'REQ-2026-04-05-0019',
    datasetId: 'ds-mzj-hospital',
    datasetName: '医疗机构基础信息',
    raisedBy: '省卫健委 数据中心',
    raisedDept: '省卫健委',
    raisedAt: '2026-04-12 09:18',
    status: 'resolved',
    severity: 'low',
    summary: '机构「等级」字段在 7 条三甲医院记录中误录为「二级」',
    detail: '与省里的医疗机构台账校对发现 7 条记录等级编码错误。',
    suggestion: '修正后重发本周增量。',
    resolvedAt: '2026-04-13 11:30',
    timeline: [
      { at: '2026-04-12 09:18', actor: '省数据中心', action: '提交异议' },
      { at: '2026-04-12 14:02', actor: '陈科长',     action: '已确认数据错误，提交修正' },
      { at: '2026-04-13 11:30', actor: '陈科长',     action: '修正完成，重新交付，关闭异议' },
    ]
  },
  {
    id: 'DSP-2026-04-10-002',
    requestId: 'REQ-2026-03-22-0007',
    datasetId: 'ds-mzj-relief',
    datasetName: '城乡低保救助金发放台账',
    raisedBy: '某区民政局 王副局长',
    raisedDept: '某区民政局',
    raisedAt: '2026-04-10 17:35',
    status: 'escalated',
    severity: 'high',
    summary: '怀疑申请方将救助名册用于商业营销',
    detail: '收到群众反映，被某金融机构精准营销「低保贷款」产品；时间窗与申请方拉取数据时间高度重合。',
    suggestion: '建议平台合规组介入审计回溯申请方的下游使用链路；必要时启动 K8 上链事后核验 + 合规追责。',
    escalatedTo: '平台合规组',
    timeline: [
      { at: '2026-04-10 17:35', actor: '王副局长',   action: '提交异议（高严重）' },
      { at: '2026-04-11 09:00', actor: '刘科长',     action: '初步核查：申请用途与实际使用场景不符，升级到平台合规组' },
    ]
  },
];

// ============================================================
// §7.3 第 7 页：合规督导 + 审计回溯（K8 / K9）
// ============================================================
window.MOCK_AUDIT_EVENTS = (function () {
  const arr = [];
  const actors = [
    { id: 'u-li-juan',          name: '李娟（市发改委）',    type: 'human' },
    { id: 'u-lin-chuzhang',     name: '林处长（市统计局）',  type: 'human' },
    { id: 'u-chen-kezhang',     name: '陈科长（市卫健委）',  type: 'human' },
    { id: 'agent-sheng-cust',   name: '省级一网统办客服 Agent', type: 'agent' },
    { id: 'svc-relay',          name: 'national.relay 系统', type: 'system' },
  ];
  const actions = [
    { skill: 'catalog.search',        label: '检索目录',     verb: 'read'  },
    { skill: 'request.submit',        label: '提交申请',     verb: 'write' },
    { skill: 'request.review',        label: '审批申请',     verb: 'write' },
    { skill: 'exchange.run',          label: '执行交换',     verb: 'write' },
    { skill: 'compliance.audit',      label: '审计查询',     verb: 'read'  },
    { skill: 'national.relay.query',  label: '国家任务查询', verb: 'read'  },
  ];
  // 生成 28 条；保证有 1 条「上链锚定失败 + 重试成功」的混合状态
  const baseDate = new Date('2026-04-18T17:00:00');
  for (let i = 0; i < 28; i++) {
    const a  = actors[i % actors.length];
    const ac = actions[(i * 3) % actions.length];
    const t  = new Date(baseDate.getTime() - i * 17 * 60 * 1000);
    arr.push({
      id: 'AE-' + (0xa3f000 + i).toString(16),
      at: t.toISOString().slice(0, 19).replace('T', ' '),
      actor: a, action: ac,
      datasetId: i % 4 === 0 ? 'ds-mzj-immune' : i % 4 === 1 ? 'ds-mzj-hospital' : i % 4 === 2 ? 'ds-mzj-relief' : 'ds-cdc-flu',
      requestId: ac.verb === 'write' ? 'REQ-2026-04-' + String(8 + (i % 12)).padStart(2, '0') + '-' + String(1 + i).padStart(4, '0') : null,
      chainAnchor: ac.verb === 'write'
        ? (i === 5 ? { state: 'retry-ok', value: '0xc91a' + i.toString(16) + '...' } : { state: 'anchored', value: '0xa3f' + i.toString(16) + '...c91' })
        : null,
    });
  }
  return arr;
})();

// ============================================================
// §7.3 第 8 页：Skill 市场（Skill 注册申请）
// ============================================================
window.MOCK_SKILL_PROPOSALS = [
  {
    id: 'PROP-2026-04-17-002',
    skillId: 'population.query',
    domain:  'catalog',
    proposer: '市公安局 人口数据中心 王工',
    proposerDept: '市公安局',
    submittedAt: '2026-04-17 14:22',
    status: 'pending',
    isWrite: false,
    summary: '常住人口属性查询（年龄段 / 籍贯 / 学历，已脱敏）— 用于人口流动分析',
    inputSchema: { type: 'object', required: ['region'], properties: { region: { type: 'string' }, year: { type: 'integer' } } },
    outputSchema: { type: 'object', properties: { items: { type: 'array' }, total: { type: 'integer' } } },
    reviewerNotes: '',
  },
  {
    id: 'PROP-2026-04-15-006',
    skillId: 'tax.summary.read',
    domain:  'compliance',
    proposer: '市税务局 数据规划处 赵工',
    proposerDept: '市税务局',
    submittedAt: '2026-04-15 11:08',
    status: 'pending',
    isWrite: false,
    summary: '行业纳税汇总（按 GB/T 4754 分类，季度粒度）— 用于营商环境月报',
    inputSchema: { type: 'object', required: ['industry_code', 'quarter'], properties: { industry_code: { type: 'string' }, quarter: { type: 'string' } } },
    outputSchema: { type: 'object', properties: { tax_total: { type: 'number' }, top_payers: { type: 'array' } } },
    reviewerNotes: '建议增加 PII 校验测试用例；input 是否需要支持区县维度',
  },
  {
    id: 'PROP-2026-04-08-001',
    skillId: 'edu.enroll.bulk_update',
    domain:  'request',
    proposer: '市教育局 信息中心',
    proposerDept: '市教育局',
    submittedAt: '2026-04-08 16:30',
    status: 'rejected',
    isWrite: true,
    summary: '批量更新中考报名信息（写操作）',
    rejectedAt: '2026-04-09 10:12',
    rejectReason: '不符合「最小 API 表面」原则——bulk 写应拆为「单条审批 + 提交 → exchange」标准流；且 N4 政策不允许业务写直接走 Agent 入口',
  },
];

// ============================================================
// §7.3 第 9 页：平台运营面板
// ============================================================
window.MOCK_RUNTIME_KPI = {
  totalSkills:        12,
  liveServices:        4,
  callsToday:      17_428,
  auditEventsToday: 9_237,
  rejectRate:       0.063,
  poolUtilization: { compute: 0.41, ai: 0.27, network: 0.18, db: 0.34 },
  callsTrend7d:    [12_804, 13_112, 14_006, 13_877, 15_240, 16_188, 17_428],
  topSkills: [
    { id: 'compliance.audit',       calls: 4218 },
    { id: 'request.status.query',   calls: 3104 },
    { id: 'catalog.search',         calls: 2987 },
    { id: 'dashboard.realtime',     calls: 1876 },
    { id: 'national.relay.query',   calls: 1244 },
    { id: 'request.submit',         calls:  712 },
    { id: 'zone.subscribe',         calls:  398 },
    { id: 'exchange.run',           calls:  201 },
  ],
};

// ============================================================
// §7.3 第 10 页：共享专区列表（K11）
// ============================================================
window.MOCK_ZONES = [
  { id: 'health',    name: '健康专区',     owner: '市卫健委 + 市疾控中心', datasetIds: ['ds-mzj-immune','ds-mzj-hospital','ds-cdc-flu'], subscriberDeptCount: 22, updatedAt: '2026-04-15', desc: '汇集免疫接种 / 医疗机构 / 传染病监测三类公共卫生数据，月度同步，默认按区县和年龄段脱敏。' },
  { id: 'minsheng',  name: '民生保障专区', owner: '市民政局',             datasetIds: ['ds-mzj-relief'],                           subscriberDeptCount: 22, updatedAt: '2026-04-16', desc: '低保 / 特困供养 / 临时救助月度发放台账。' },
  { id: 'business',  name: '营商环境专区', owner: '市发改委',             datasetIds: [],                                          subscriberDeptCount:  5, updatedAt: '—',          desc: '（筹建中）拟汇集涉企政策、园区运营、企业开办时长等指标。' },
  { id: 'city-mgr',  name: '城市治理专区', owner: '市政府办公厅',         datasetIds: [],                                          subscriberDeptCount:  0, updatedAt: '—',          desc: '（规划中）一网统管涉及的城市运行体征数据。' },
];
