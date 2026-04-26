/* ---------------------------------------------------------------------------
   政务数据大脑 v4 高保真 prototype · mock 数据
   目标：R1–R8 真实角色链路 + 法人单位基础信息模板首条黄金旅程
   --------------------------------------------------------------------------- */

window.MOCK_WORKBENCH = {
  r1: {
    greeting: '周处长，上午好',
    subtitle: '你有 1 条 zw-brain 前台专题复用申请待看进度，1 条专题资产订阅建议，1 条减负提示。',
    todos: [
      { id: 'REQ-2026-04-25-0011', title: '法人单位基础信息模板复用申请进入受控准入', status: '审批中', href: '#/p3-request-flow/request/REQ-2026-04-25-0011' },
      { id: 'ZONE-business-ledger', title: '营商环境专区新增“法人基础信息复用”专题包', status: '可查看', href: '#/p7-zones-pack/zone/business' },
    ],
    highlights: ['本周 3 条涉企需求被拦截为“先复用模板再补差异字段”', '法人单位基础信息模板覆盖率 82%', '营商环境专题建议先用共享底座再发起差异采集'],
    aiSummary: {
      summary: '建议你先跟进“法人单位基础信息模板复用申请”，因为这条链已经具备现成模板、审批口径清楚，最快能验证“先复用后补录”的黄金旅程。',
      actions: ['查看模板覆盖率', '查看差异字段清单', '进入申请进度'],
      basis: ['当前需求命中涉企基础信息高频字段', '模板已被多个专题包复用', '差异字段只剩现场经营状态与走访备注'],
    },
  },
  r2: {
    greeting: '刘主任，上午好',
    subtitle: '你有 2 条涉企采集准入待判定，其中 1 条可直接复用模板、1 条需要退回补正。',
    todos: [
      { id: 'REQ-2026-04-25-0011', title: '营商环境专题复用申请待审批', status: '待审批', href: '#/p3-request-flow/review/REQ-2026-04-25-0011' },
      { id: 'REQ-2026-04-24-0007', title: '专项摸排新增采集申请待补正', status: '待补正', href: '#/p3-request-flow/review/REQ-2026-04-24-0007' },
    ],
    highlights: ['本周已拦截重复要数 4 次', '可直接复用模板申请占比 63%', '差异字段平均从 18 项压缩到 4 项'],
    aiSummary: {
      summary: '建议你先通过 REQ-2026-04-25-0011，再把 REQ-2026-04-24-0007 退回补正。前者只需确认差异字段责任边界，后者仍缺少新增采集必要性证明。',
      actions: ['查看复用依据', '查看退回草案', '查看回流要求'],
      basis: ['法人模板已覆盖大部分涉企字段', '新增采集申请未证明现有模板不足', '通过后可直接进入预填任务'],
    },
  },
  r3: {
    greeting: '陈经办，上午好',
    subtitle: '你有 1 条镇街预填任务待补差异字段，1 条退回补充待复核。',
    todos: [
      { id: 'REQ-2026-04-25-0011', title: '营商环境专题预填任务待补录', status: '待补录', href: '#/p3-request-flow/request/REQ-2026-04-25-0011' },
      { id: 'REQ-2026-04-24-0007', title: '专项摸排任务退回补充', status: '待修改', href: '#/p3-request-flow/request/REQ-2026-04-24-0007' },
    ],
    highlights: ['本次任务已自动带出企业基础字段 12 项', '仅需补录 3 项现场差异字段', '一次确认后可同步复用到镇街汇总与区县上报'],
    aiSummary: {
      summary: '这次最重要的不是重新填表，而是核对系统已带出的法人基础字段，只补现场变化项。完成后，审核汇总页会自动生成异常清单。',
      actions: ['查看已预填字段', '查看待补录字段', '查看退回原因'],
      basis: ['统一社会信用代码等字段已来自共享资源池', '差异字段集中在经营状态和走访时间', '审核岗只处理异常项'],
    },
  },
  r4: {
    greeting: '王网格员，上午好',
    subtitle: '你有 1 条社区轻量补录任务，系统已带出法人基础信息，只需补现场变化。',
    todos: [
      { id: 'REQ-2026-04-25-0011', title: '社区端现场补录任务', status: '待补录', href: '#/p3-request-flow/request/REQ-2026-04-25-0011' },
    ],
    highlights: ['已自动带出 10 项基础字段', '仅需补 2 项现场核验字段', '不需要理解共享平台概念，只要确认变化'],
    aiSummary: {
      summary: '系统已经把企业基础信息带出来了，你只要确认“是否正常经营”和“最近走访情况”两项，不需要再重复录入主体基础信息。',
      actions: ['进入轻量任务', '查看已带出字段'],
      basis: ['基础信息来自法人单位基础信息模板', '末端只保留最现场、最动态字段', '提交后自动回流上层汇总'],
    },
  },
  r5: {
    greeting: '赵科长，上午好',
    subtitle: '你有 1 条汇总确认待处理，系统已自动汇总，只剩 2 项差异异常待你确认。',
    todos: [
      { id: 'REQ-2026-04-25-0011', title: '营商环境专题自动汇总待确认', status: '待汇总确认', href: '#/p3-request-flow/review/REQ-2026-04-25-0011' },
    ],
    highlights: ['自动汇总已覆盖 28 家企业', '异常项集中在经营状态不一致与缺失现场备注', '退回补录后可直接形成上报结果'],
    aiSummary: {
      summary: '本次汇总已基本成型，你只需要处理 2 项异常：1 家企业经营状态冲突、1 家企业缺少现场备注。处理完成后即可自动形成上报结果。',
      actions: ['查看异常项', '查看自动汇总结果', '查看来源依据'],
      basis: ['绝大多数字段来自共享模板预填', '人工只需处理差异项', '通过后会生成回流候选'],
    },
  },
  r6: {
    greeting: '孙老师，上午好',
    subtitle: '你有 1 个台账模板待发布更新，1 条字段口径异议待确认。',
    todos: [
      { id: 'LEDGER-jbxx-v1.3', title: '法人单位基础信息模板待发布', status: '待发布', href: '#/p5-provider' },
      { id: 'DSP-2026-04-25-0003', title: '经营状态字段口径异议待核查', status: '待核查', href: '#/p6-compliance-ops/dispute/DSP-2026-04-25-0003' },
    ],
    highlights: ['本周模板复用 9 次', '3 个差异字段已沉淀为回流候选', '字段“经营状态”最常被补录'],
    aiSummary: {
      summary: '建议你优先发布法人模板 v1.3，因为这次基层补录已验证“经营状态”和“走访时间”应纳入下一版正式字段。',
      actions: ['查看回流候选字段', '查看模板版本差异', '查看发布前检查'],
      basis: ['本轮任务暴露了高频差异字段', '回流后可减少下次补录', '模板已具备稳定来源和责任方'],
    },
  },
  r7: {
    greeting: '高主任，上午好',
    subtitle: '你有 1 个 zw-brain 前台专题资产待更新，1 个能力注册包待审核。',
    todos: [
      { id: 'ZONE-business-ledger', title: '营商环境专区待纳入法人模板 v1.3', status: '待更新', href: '#/p7-zones-pack/zone/business' },
      { id: 'PKG-2026-04-25-001', title: 'ledger.entity.base.read 能力包待审核', status: '待审批', href: '#/p8-integration-admin/package/PKG-2026-04-25-001' },
    ],
    highlights: ['共享目录中已有 1 个高频默认复用能力', '外部能力包已全部收敛为只读辅助', 'P8 仅承载管理员控制面'],
    aiSummary: {
      summary: '建议先更新营商环境专区对法人模板的默认入口，再审核只读能力包，保证前台“先发现模板再申请”的入口一致。',
      actions: ['查看专区入口', '查看 capability schema', '查看暴露范围'],
      basis: ['前台专区入口决定首条旅程是否顺滑', '能力包是只读辅助，不是主流程前置', '模板版本已准备更新'],
    },
  },
  r8: {
    greeting: '林督查，上午好',
    subtitle: '你有 1 条重复要数告警、1 条减负指标异常待复核。',
    todos: [
      { id: 'DSP-2026-04-25-0003', title: '重复要数争议待调查', status: '处理中', href: '#/p6-compliance-ops/dispute/DSP-2026-04-25-0003' },
      { id: 'AL-2026-04-25-002', title: '某部门绕开模板重复发起采集', status: '告警', href: '#/dashboard/alert/AL-2026-04-25-002' },
    ],
    highlights: ['本周重复要数率下降到 12%', '仍有 2 个字段被基层反复补录', '营商环境专题减负时长较上周下降 31%'],
    aiSummary: {
      summary: '建议先看“绕开模板重复采集”这条告警，它直接影响减负成效；其次查看经营状态字段为何仍被频繁补录，决定是否推动模板升级。',
      actions: ['查看减负指标', '查看绕行证据', '查看字段热区'],
      basis: ['重复要数直接触发基层负担反弹', '差异补录热区可反向指导模板治理', '本周趋势已具备治理闭环价值'],
    },
  },
};

window.MOCK_DISCOVERY = {
  zones: [
    { id: 'business', name: '营商环境专区' },
    { id: 'governance', name: '治理减负专区' },
    { id: 'livelihood', name: '民生保障专区' },
  ],
  aiCopilot: {
    summary: '已把你的问题识别为“涉企专题 + 优先复用法人单位基础信息模板 + 只补现场差异字段”。当前最合适的下一步，是先查看法人单位基础信息台账模板的覆盖率和差异字段。',
    missingQuestions: ['是否限定镇街 / 社区范围？', '是否需要附带现场经营状态与走访备注？'],
    nextActions: ['查看模板详情', '直接发起复用申请', '先进入营商环境专区'],
    evidence: ['输入文本明确出现“复用法人单位基础信息台账模板”', '命中涉企基础对象高频字段', '该模板是营商环境专题的默认起点'],
  },
  resources: [
    {
      id: 'res-jbxx-ledger',
      name: '法人单位基础信息台账模板',
      provider: '区政数局 / 市场监管局联合维护',
      zone: '营商环境专区',
      status: '可复用',
      score: 98,
      updatedAt: '2026-04-25',
      subscribers: 31,
      approvalRate: '97%',
      desc: '面向涉企场景的默认基础信息复用对象，已覆盖统一社会信用代码、企业名称、法定代表人、行业代码、登记机关等高频字段。',
      fields: ['统一社会信用代码', '企业名称', '法定代表人', '行业代码', '成立日期', '登记机关', '经营场所', '注册资本', '经营状态', '最近走访时间'],
      explain: ['当前需求首先应复用该模板，而不是重新发起整表采集', '模板已覆盖多数企业基础字段', '仅需补少量现场差异字段即可形成任务'],
      nextHints: ['查看覆盖率与差异字段', '作为预填底座发起申请', '查看模板版本与来源'],
      coverage: '82%',
    },
    {
      id: 'res-market-activity',
      name: '市场主体活跃度月度汇总',
      provider: '市市场监管局',
      zone: '营商环境专区',
      status: '可申请',
      score: 88,
      updatedAt: '2026-04-23',
      subscribers: 19,
      approvalRate: '93%',
      desc: '适合营商环境趋势分析，但不替代法人主体基础信息模板本身。',
      fields: ['统计月', '区县', '新增主体数', '注销主体数', '净增长'],
      explain: ['适合做趋势结果，但不是当前复用起点', '更适合作为模板复用后的专题补充'],
      nextHints: ['作为专题补充资源查看'],
      coverage: '趋势汇总',
    },
    {
      id: 'res-company-visit',
      name: '企业走访差异补录视图',
      provider: '镇街协同填报链路',
      zone: '治理减负专区',
      status: '可查看',
      score: 81,
      updatedAt: '2026-04-24',
      subscribers: 11,
      approvalRate: '—',
      desc: '聚合基层补录频次最高的现场差异字段，用于反向指导模板升级与减负治理。',
      fields: ['经营状态', '最近走访时间', '现场备注'],
      explain: ['用于观察哪些字段仍需基层反复补录', '适合进入治理视角，不是普通需求的起点'],
      nextHints: ['查看减负热区'],
      coverage: '治理视图',
    },
  ],
  catalogTree: [
    { name: '涉企基础对象', count: 6 },
    { name: '营商环境专题', count: 9 },
    { name: '共享目录资源', count: 18 },
    { name: '治理减负视图', count: 4 },
  ],
};

window.MOCK_REQUESTS = [
  {
    id: 'REQ-2026-04-25-0011',
    resourceId: 'res-jbxx-ledger',
    resourceName: '法人单位基础信息台账模板',
    applicant: '周处长（市营商环境专班）',
    applicantDept: '市营商环境专班',
    purpose: '为本周营商环境专题复用法人单位基础字段，只补现场差异字段。',
    range: '营商环境专题 · 镇街 / 社区协同',
    expectedBy: '2026-04-27',
    status: 'pending',
    submittedAt: '2026-04-25 09:14',
    auditId: 'AE-2026-04-25-0914',
    chainAnchor: 'pending',
    templateCoverage: '82%',
    prefilledFields: [
      { label: '统一社会信用代码', value: '91370000MA3XXXXXX1', source: '共享资源池 / 市场监管登记', state: '已预填' },
      { label: '企业名称', value: '山东云启科技有限公司', source: '法人模板 v1.2', state: '已预填' },
      { label: '法定代表人', value: '李某某', source: '法人模板 v1.2', state: '已预填' },
      { label: '行业代码', value: 'I6510', source: '法人模板 v1.2', state: '已预填' },
      { label: '登记机关', value: '市市场监管局', source: '共享资源池', state: '已预填' },
    ],
    diffFields: [
      { label: '经营状态', value: '待镇街确认', reason: '现场状态变化快', owner: 'R3/R4 补录' },
      { label: '最近走访时间', value: '待补录', reason: '共享池无现场时间', owner: 'R4 补录' },
      { label: '现场备注', value: '待补录', reason: '仅末端掌握', owner: 'R3/R4 补录' },
    ],
    reviewFocus: ['是否允许按模板先复用后补录', '差异字段责任边界是否清楚', '补录结果是否要求回流模板候选'],
    summaryResult: {
      totalEntities: 28,
      autoMerged: 26,
      exceptions: 2,
      note: '自动汇总已形成区县上报草稿，只剩异常项待审核汇总人员确认。',
    },
    returnFlow: [
      '通过后自动创建镇街 / 社区预填任务',
      '补录完成后自动生成汇总结果',
      '高频差异字段进入回流候选池',
    ],
    timeline: [
      { label: '已发现可复用模板', time: '2026-04-25 09:02', note: '系统识别涉企需求，优先命中法人单位基础信息模板' },
      { label: '已生成标准复用申请', time: '2026-04-25 09:14', note: '进入受控准入并生成 audit_id AE-2026-04-25-0914' },
      { label: '待审批承接人员判定', time: '2026-04-25 09:20', note: '重点确认差异字段责任边界和回流要求' },
      { label: '待基层补录', time: '—', note: '审批通过后自动下发预填任务' },
      { label: '待审核汇总', time: '—', note: '系统先自动汇总，再由 R5 只处理异常项' },
    ],
    aiDraft: {
      recognized: ['已识别专题：营商环境', '已识别起点：法人单位基础信息模板', '已识别策略：先复用再补差异字段'],
      needConfirm: ['是否限定镇街 / 社区范围', '是否需要把高频差异字段纳入回流候选'],
      missing: ['现场经营状态是否需要逐家确认', '是否要求附带走访备注'],
      risk: '新增采集必要性低，主要风险在于差异字段责任边界不清会导致后续退回补录。',
      attachments: ['建议附“只补差异字段、不新增整表”的说明', '建议明确补录完成后进入模板回流候选池'],
      summary: '本申请拟优先复用法人单位基础信息模板，以共享资源池预填大部分企业基础字段，仅把现场经营状态、走访时间和备注交由基层补录。',
    },
    aiStatus: {
      summary: '申请已经从“我要一张新表”收敛成“先复用法人模板，再补差异字段”的结构化流程。当前只等 R2 判定差异边界。',
      nextAction: '建议先查看已预填字段与待补录字段，确保审批通过后可直接进入基层任务。',
      evidence: ['模板覆盖率 82%', '差异字段仅剩 3 项', '已生成标准复用申请并进入受控准入'],
    },
  },
  {
    id: 'REQ-2026-04-24-0007',
    resourceId: 'res-jbxx-ledger',
    resourceName: '法人单位基础信息台账模板',
    applicant: '某专项摸排专班',
    applicantDept: '区级专项摸排专班',
    purpose: '拟新增一张涉企摸排表，但未说明为何现有模板不足。',
    range: '临时摸排',
    expectedBy: '2026-04-26',
    status: 'need-fix',
    submittedAt: '2026-04-24 15:22',
    auditId: 'AE-2026-04-24-1522',
    chainAnchor: '0x9a12...bc4',
    templateCoverage: '76%',
    prefilledFields: [
      { label: '统一社会信用代码', value: '已存在', source: '法人模板 v1.2', state: '已预填' },
      { label: '企业名称', value: '已存在', source: '法人模板 v1.2', state: '已预填' },
    ],
    diffFields: [
      { label: '拟新增采集必要性说明', value: '缺失', reason: '未证明现有模板不足', owner: 'R1 补充' },
      { label: '差异字段责任人', value: '缺失', reason: '未定义谁补录', owner: 'R2 退回补正' },
    ],
    reviewFocus: ['是否属于重复要数', '是否需要整表新增还是局部补差异'],
    summaryResult: {
      totalEntities: 0,
      autoMerged: 0,
      exceptions: 0,
      note: '尚未进入基层任务。',
    },
    returnFlow: ['补齐必要性说明后再重进审批'],
    timeline: [
      { label: '已提交申请', time: '2026-04-24 15:22', note: '系统识别到已命中法人模板但申请仍请求新增整表' },
      { label: '已退回补正', time: '2026-04-24 17:10', note: '要求证明新增采集必要性并说明差异字段责任边界' },
    ],
    aiDraft: {
      recognized: ['命中法人模板高频字段'],
      needConfirm: ['是否真的需要新增整表'],
      missing: ['新增采集必要性说明', '差异字段清单与责任人'],
      risk: '如果直接通过，会形成重复要数并增加基层负担。',
      attachments: ['补充现有模板不能覆盖的字段清单', '补充新增采集责任边界'],
      summary: '当前申请更像把已有模板场景重新发成新表，建议退回补正。',
    },
    aiStatus: {
      summary: '该申请已被识别为可能重复要数，系统建议先补齐现有模板不足证据。',
      nextAction: '建议申请方改成“模板复用 + 差异字段补件”而不是新增整表。',
      evidence: ['已命中法人模板', '新增必要性说明缺失'],
    },
  },
];

window.MOCK_APPROVALS = [
  {
    id: 'REQ-2026-04-25-0011',
    suggestion: '建议通过',
    confidence: 0.94,
    reason: ['法人单位基础信息模板已覆盖大部分涉企基础字段', '本次只新增 3 个现场差异字段，符合减负原则', '回流要求已明确，可沉淀下次复用能力'],
    risk: ['需明确经营状态由谁补录并谁来确认', '需保留补录结果回流候选的责任边界'],
    counterfactual: '如果申请方要求重新采一整张涉企表，而不是先复用模板，应转为补正或驳回。',
    impact: '通过后将自动创建镇街 / 社区预填任务，并在补录完成后生成自动汇总结果。',
    actions: ['通过', '退回补正', '驳回'],
    draftNote: '建议审批意见：同意以法人单位基础信息模板作为预填底座，仅对经营状态、最近走访时间和现场备注发起差异补录；补录结果纳入回流候选。',
    exceptionItems: ['企业 A 经营状态需现场确认', '企业 B 缺少最近走访时间'],
    autoSummary: '系统已预估自动汇总覆盖 28 家企业，异常项 2 家。',
  },
  {
    id: 'REQ-2026-04-24-0007',
    suggestion: '建议补正',
    confidence: 0.89,
    reason: ['未证明现有模板不足', '新增整表会造成重复要数', '差异字段责任边界缺失'],
    risk: ['直接通过会增加基层重复填报', '后续审核汇总无法区分预填字段和新增字段'],
    counterfactual: '如果补齐模板不足字段清单，并改为差异补录流程，可转正常审批。',
    impact: '退回补正可避免无效下派任务和后续合规争议。',
    actions: ['退回补正', '驳回'],
    draftNote: '建议补正：请说明现有法人模板无法覆盖的具体字段，并按“模板复用 + 差异补录”重提。',
    exceptionItems: ['新增采集必要性证明缺失'],
    autoSummary: '未进入自动汇总链。',
  },
];

window.MOCK_DELIVERY_TASKS = [
  {
    id: 'DLV-2026-04-25-0011',
    requestId: 'REQ-2026-04-25-0011',
    name: '法人模板预填任务下发与回流任务',
    channel: '预填下发 + 汇总回流',
    status: 'reconciling',
    owner: '市营商环境专班 → 镇街 / 社区 → 区县汇总',
    updatedAt: '2026-04-25 14:48',
    note: '预填任务已下发并回收 26/28 家企业，待审核汇总确认异常项。',
    history: [
      { time: '09:44', state: '审批通过', detail: '系统确认“先复用模板再补差异字段”并自动生成预填任务' },
      { time: '10:18', state: '基层补录进行中', detail: 'R3/R4 仅补经营状态、走访时间和现场备注' },
      { time: '13:52', state: '自动汇总完成', detail: '已形成 28 家企业汇总草稿，异常 2 家' },
      { time: '14:48', state: '回流待确认', detail: '高频差异字段进入模板回流候选池，等待 R5/R6 确认' },
    ],
    aiSummary: {
      summary: '这条任务已不再是单次交付，而是“预填下发 → 差异补录 → 自动汇总 → 回流候选”闭环。当前主要等待异常项确认和回流决定。',
      nextAction: '建议先由 R5 确认 2 项异常，再由 R6/R7 决定是否把经营状态纳入模板 v1.3。',
      cause: '模板已承担大部分字段，任务重心转为差异确认与回流治理。',
      impact: '若今天完成回流确认，下次类似需求可进一步减少基层补录。',
    },
    backflow: {
      candidateObject: '法人单位基础信息模板 v1.3',
      candidateFields: ['经营状态', '最近走访时间'],
      status: '待确认',
      note: '字段来源与责任方已具备，待台账管理员确认是否正式纳入。',
    },
  },
  {
    id: 'DLV-2026-04-24-0008',
    requestId: 'REQ-2026-04-24-0007',
    name: '重复要数疑似任务',
    channel: '准入拦截',
    status: 'warning',
    owner: '审批承接人员 → 合规治理',
    updatedAt: '2026-04-24 17:10',
    note: '因重复要数风险被拦截，未实际下发基层任务。',
    history: [
      { time: '15:22', state: '申请提交', detail: '系统识别到拟新增整表与现有法人模板高度重叠' },
      { time: '17:10', state: '准入拦截', detail: '退回补正，未进入基层填报链路' },
    ],
    aiSummary: {
      summary: '这是一次合规意义上的“成功拦截”，不是任务失败。平台识别出它会造成重复要数，因此在准入阶段终止。',
      nextAction: '建议申请方改为模板复用模式重提。',
      cause: '新增整表未证明必要性，且与现有模板重复度高。',
      impact: '避免了基层再次录入同类企业基础信息。',
    },
    backflow: {
      candidateObject: '无',
      candidateFields: [],
      status: '不适用',
      note: '未进入执行链。',
    },
  },
  {
    id: 'DLV-2026-04-23-0004',
    requestId: 'REQ-2026-04-23-0099',
    name: '审计回放补投任务',
    channel: '内部修复',
    status: 'failed',
    owner: '平台审计总线',
    updatedAt: '2026-04-23 16:01',
    note: 'audit_event 写入失败即熔断终止，未产生假成功。',
    history: [
      { time: '15:56', state: '开始执行', detail: '准备补投回放所需审计事件' },
      { time: '16:01', state: '失败终止', detail: 'audit_event 写入失败 → 熔断终止' },
    ],
    aiSummary: {
      summary: '这是审计优先的主动熔断，不是“看起来失败但其实业务已成功”。平台在缺失审计回执时拒绝继续推进。',
      nextAction: '建议先修复审计写入链，再重新执行补投任务。',
      cause: '审计总线写入失败触发保护。',
      impact: '不修复会阻断所有需要写审计回执的责任动作。',
    },
    backflow: {
      candidateObject: '无',
      candidateFields: [],
      status: '不适用',
      note: '该任务不涉及业务回流。',
    },
  },
];

window.MOCK_PROVIDER = {
  overview: [
    { label: '模板版本', value: 'v1.2 → v1.3' },
    { label: '本周复用次数', value: '9' },
    { label: '回流候选字段', value: '2' },
    { label: '待处理异议', value: '1' },
  ],
  catalogs: [
    { id: 'cat-jbxx', name: '涉企基础对象目录', status: '已发布', owner: '区政数局', issue: '需补充 v1.3 版本说明' },
    { id: 'cat-business', name: '营商环境专题目录', status: '待质检', owner: '市营商环境专班', issue: '需更新默认复用入口说明' },
  ],
  resources: [
    { id: 'res-jbxx-ledger', name: '法人单位基础信息台账模板', status: '可共享', type: '标准模板', updatedAt: '2026-04-25' },
    { id: 'res-company-visit', name: '企业走访差异补录视图', status: '待审核', type: '治理视图', updatedAt: '2026-04-24' },
    { id: 'res-market-activity', name: '市场主体活跃度月度汇总', status: '可共享', type: '专题资源', updatedAt: '2026-04-23' },
  ],
  services: [
    { id: 'svc-ledger-prefill', name: '法人模板预填服务', qps: 28, status: '在线', note: '支撑镇街 / 社区差异补录任务' },
    { id: 'svc-ledger-backflow', name: '模板回流候选生成服务', qps: 9, status: '在线', note: '按补录热区生成字段回流建议' },
  ],
  aiGovernance: {
    summary: '建议优先发布法人模板 v1.3，并把“经营状态”“最近走访时间”纳入正式字段候选；其次更新营商环境专题目录中的默认复用入口说明。',
    priorities: ['模板：确认 v1.3 字段集与来源说明', '目录：更新“先复用模板再补差异字段”的入口文案', '服务：保持预填与回流服务 SLA 稳定'],
    draft: '可生成“模板升级 + 专题入口更新 + 回流候选确认”的治理草案，待人工确认后执行。',
    evidence: ['经营状态是本周最高频补录字段', '模板复用已验证减负效果', '营商环境专题入口是前台主链路关键触点'],
  },
};

window.MOCK_DISPUTES = [
  {
    id: 'DSP-2026-04-25-0003',
    title: '某部门绕开法人模板重复发起涉企采集',
    severity: 'high',
    status: 'open',
    owner: '区减负治理组',
    timeline: [
      { time: '09:22', label: '系统发现重复要数风险', note: '新申请与法人模板字段重叠度 78%' },
      { time: '09:35', label: '进入治理调查', note: '已绑定申请链路、审批意见和基层反馈证据' },
    ],
    aiSummary: '初步判断这不是数据质量问题，而是绕开 zw-brain 默认复用能力发起新增采集。建议优先查看审批前证据和基层负担反馈。',
  },
  {
    id: 'DSP-2026-04-24-0006',
    title: '经营状态字段口径不一致',
    severity: 'mid',
    status: 'escalated',
    owner: '区台账治理组',
    timeline: [
      { time: '2026-04-24 10:11', label: '提出异议', note: '镇街反馈现场经营状态与模板口径不一致' },
      { time: '2026-04-24 16:42', label: '升级核查', note: '建议纳入 v1.3 字段修订' },
    ],
    aiSummary: '这类问题适合通过模板升级治理，而不是反复留给基层补录。',
  },
  {
    id: 'DSP-2026-04-23-0002',
    title: '走访备注缺失导致汇总退回',
    severity: 'low',
    status: 'resolved',
    owner: '镇街审核汇总组',
    timeline: [
      { time: '2026-04-23 11:20', label: '退回补录', note: '2 家企业缺失现场备注' },
      { time: '2026-04-23 14:06', label: '已修正', note: '补录完成并通过汇总确认' },
    ],
    aiSummary: '这是典型差异补录问题，说明自动汇总主链已成立，人工只处理异常项。',
  },
];

window.MOCK_AUDIT_EVENTS = [
  { id: 'AE-2026-04-25-0902', time: '04-25 09:02', actor: 'system', type: 'discovery.template-match', target: 'res-jbxx-ledger', result: 'ok', chain: 'pending' },
  { id: 'AE-2026-04-25-0914', time: '04-25 09:14', actor: '周处长', type: 'request.submit', target: 'REQ-2026-04-25-0011', result: 'ok', chain: 'pending' },
  { id: 'AE-2026-04-25-0944', time: '04-25 09:44', actor: '刘主任', type: 'request.approve', target: 'REQ-2026-04-25-0011', result: 'ok', chain: '0x91af...' },
  { id: 'AE-2026-04-25-1018', time: '04-25 10:18', actor: 'system', type: 'prefill.dispatch', target: 'DLV-2026-04-25-0011', result: 'ok', chain: '0x821c...' },
  { id: 'AE-2026-04-25-1352', time: '04-25 13:52', actor: 'system', type: 'summary.auto-merge', target: 'REQ-2026-04-25-0011', result: 'ok', chain: '0x9f2a...' },
  { id: 'AE-2026-04-25-1448', time: '04-25 14:48', actor: 'system', type: 'backflow.candidate-generated', target: 'LEDGER-jbxx-v1.3', result: 'warning', chain: '0x7ca1...' },
  { id: 'AE-2026-04-24-1710', time: '04-24 17:10', actor: '刘主任', type: 'request.return-for-fix', target: 'REQ-2026-04-24-0007', result: 'warning', chain: '0x771b...' },
  { id: 'AE-2026-04-23-1601', time: '04-23 16:01', actor: 'system', type: 'audit.replay', target: 'DLV-2026-04-23-0004', result: 'failed', chain: 'n/a' },
];

window.MOCK_AUDIT_AI = {
  summary: '当前证据链可以分成三类：模板优先复用的成功闭环、重复要数被准入拦截的治理事件，以及因审计写入失败而主动熔断的保护事件。',
  evidence: ['发现 → 申请 → 审批 → 预填 → 自动汇总 → 回流候选构成完整黄金链路', '重复要数事件在准入前被拦截，减少基层负担', '审计补投失败被明确阻断，没有形成假成功'],
};

window.MOCK_ALERTS = [
  {
    id: 'AL-2026-04-25-002',
    severity: 'mid',
    title: '某部门绕开模板重复发起涉企采集',
    summary: '系统检测到新增采集与法人模板字段重叠度 78%，疑似绕开 zw-brain 默认复用能力。',
    diagnosis: '更像制度执行偏离，而不是技术故障。应先查审批前是否已提示可复用模板。',
    linkedTicket: 'TK-2026-04-25-014',
    knowledge: 'KB-REDUCE-BURDEN-02',
    owner: '减负治理专班',
    aiAdvice: '建议先看该申请是否已被系统推荐为复用 zw-brain 法人模板，再查看基层是否因此收到重复填报任务。',
  },
  {
    id: 'AL-2026-04-25-003',
    severity: 'mid',
    title: '经营状态字段仍高频补录',
    summary: '近 7 日经营状态字段被基层补录 14 次，高于阈值。',
    diagnosis: '说明模板覆盖仍不足，应评估是否纳入 v1.3 正式字段。',
    linkedTicket: 'TK-2026-04-25-015',
    knowledge: 'KB-TEMPLATE-BACKFLOW-01',
    owner: '台账治理组',
    aiAdvice: '建议把经营状态字段纳入回流候选，并查看是否存在口径不一致问题。',
  },
];

window.MOCK_TICKETS = [
  {
    id: 'TK-2026-04-25-014',
    title: '重复要数绕行调查工单',
    status: '处理中',
    owner: '减负治理专班',
    note: '核查审批前是否已提示法人模板，并确认基层是否收到重复任务。',
  },
  {
    id: 'TK-2026-04-25-015',
    title: '经营状态字段回流评估工单',
    status: '已派单',
    owner: '台账治理组',
    note: '评估是否纳入模板 v1.3 与对应来源口径。',
  },
];

window.MOCK_KNOWLEDGE_ARTICLES = [
  {
    id: 'KB-REDUCE-BURDEN-02',
    title: '重复要数绕行调查手册',
    summary: '适用于“系统已提示可复用模板，但业务方仍发起新增采集”的治理场景。',
  },
  {
    id: 'KB-TEMPLATE-BACKFLOW-01',
    title: '模板回流候选评估手册',
    summary: '适用于高频差异补录字段是否纳入正式模板版本的评估场景。',
  },
];

window.MOCK_ZONES = [
  {
    id: 'business',
    name: '营商环境专区',
    status: '已上线',
    desc: '围绕涉企专题，把法人单位基础信息模板作为 zw-brain 默认复用起点，并聚合趋势资源、申请入口与订阅。',
    assets: ['法人单位基础信息台账模板', '市场主体活跃度月度汇总', '企业走访差异补录视图'],
    subscribers: 31,
    aiGuide: '如果你的任务和企业主体、审批效能、助企政策有关，应先从这里发现可复用的法人基础对象。',
    nextActions: ['查看法人模板详情', '发起模板复用申请', '订阅专区更新'],
    trust: ['来源等级：高', '模板版本：v1.2，v1.3 待发布', '责任方：区政数局 / 市场监管局'],
  },
  {
    id: 'governance',
    name: '治理减负专区',
    status: '已上线',
    desc: '围绕重复要数、差异补录热区和回流候选，形成面向 R8 的持续治理观察面。',
    assets: ['重复要数拦截视图', '差异补录热区', '模板回流候选池'],
    subscribers: 12,
    aiGuide: '如果你关心减负成效、绕行行为和高频补录字段，应优先看这里。',
    nextActions: ['查看减负指标', '查看绕行证据'],
    trust: ['来源等级：治理读模型', '更新频率：每日', '责任方：减负治理专班'],
  },
  {
    id: 'livelihood',
    name: '民生保障专区',
    status: '筹建中',
    desc: '作为后续第二条黄金链路候选，当前保留主题入口，但不抢占法人模板首条主旅程。',
    assets: ['民生对象模板候选', '低保主题分析汇总'],
    subscribers: 7,
    aiGuide: '当前仍以营商环境专题和法人基础对象为第一刀，民生场景放在下一波扩展。',
    nextActions: ['查看候选资产'],
    trust: ['来源等级：筹建中', '责任方：民生条线'],
  },
];

window.MOCK_CAPABILITY_PACKAGES = [
  {
    id: 'PKG-2026-04-25-001',
    slug: 'ledger.entity.base.read',
    source: '区政数局 / 外部 ANP',
    status: 'pending',
    exposure: ['api', 'cli', 'mcp'],
    auditClass: 'read-sensitive',
    requiresHuman: false,
    desc: '只读暴露法人单位基础信息模板的标准字段查询与版本说明，不拥有提交、审批或回流写权。',
    aiReview: {
      summary: '结构上基本完整，适合作为外部只读辅助能力回注册，但仍需补充 tenant_scope 与默认可见范围说明。',
      missing: ['tenant_scope 说明不够清晰', '缺少默认暴露范围解释'],
      safe: ['只读能力', '无主状态写权', '不替代平台审批与回流动作'],
      draft: '建议退回补充：请明确跨租户可见范围，并补充默认暴露面说明。',
    },
  },
  {
    id: 'PKG-2026-04-24-002',
    slug: 'ledger.diff.recommend',
    source: '减负治理专班 / 外部 ANP',
    status: 'pending-fix',
    exposure: ['api', 'mcp'],
    auditClass: 'read-normal',
    requiresHuman: false,
    desc: '对高频差异补录字段生成推荐解释与回流建议，属于减摩辅助，不直接写回模板版本。',
    aiReview: {
      summary: '继续补充 side effects 声明后可转正常审批。当前需要更清楚地说明“只推荐、不生效”。',
      missing: ['side effects 声明不完整'],
      safe: ['不拥有 register-version 或 apply-tenant-policy 写权'],
      draft: '建议补充：明确该能力只输出推荐结果，正式模板升级仍由平台管理员控制面确认。',
    },
  },
  {
    id: 'PKG-2026-04-23-006',
    slug: 'ledger.bulk.submit',
    source: '某外部建设方',
    status: 'rejected',
    exposure: ['api'],
    auditClass: 'write-critical',
    requiresHuman: true,
    desc: '试图批量提交预填任务并直接推进状态，因越界拥有主状态写权被驳回。',
    aiReview: {
      summary: '驳回是合理的：它越界触碰了 submit、review-and-decide 与回流生效三条红线。',
      missing: ['逐步确认路径', '平台内建写权边界说明'],
      safe: [],
      draft: '建议重构为“只读推荐 + 结构化草稿”，不要直接声明批量提交或回流生效能力。',
    },
  },
];

window.MOCK_DASHBOARD = {
  summary: {
    flowToday: '28',
    qps: '37',
    agentsOnline: '18',
    alerts: '2',
    national: '正常',
  },
  trendHours: ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00'],
  trendValues: [8, 12, 21, 28, 23, 17],
  burdenMetrics: [
    { label: '重复要数率', value: '12%', trend: '较上周 -6pt' },
    { label: '基层补录字段数', value: '3 / 单任务', trend: '较基线 -72%' },
    { label: '自动汇总覆盖率', value: '93%', trend: '较上周 +11pt' },
    { label: '回流候选字段', value: '2', trend: '本周新增' },
  ],
  suggestions: {
    title: '指挥辅助结论：盯住“绕开模板重复采集”与“经营状态高频补录”',
    body: '当前黄金链路已经跑通，但仍有部门绕开法人模板发起新增采集，同时经营状态字段持续高频补录，建议优先做制度提醒和模板升级。',
    evidence: ['本周重复要数率已降至 12%，但仍有 1 条高风险绕行告警', '经营状态字段近 7 日补录 14 次', '法人模板复用后基层填报时长下降 31%'],
    nextAction: '先看绕行告警，再推动模板 v1.3 升级。',
    owner: 'R8 合规治理 / R6 台账管理员 / R7 目录管理员',
  },
};
