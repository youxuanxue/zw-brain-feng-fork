(function () {
  'use strict';

  const ROLE_NAMES = {
    r1: 'R1 上级业务需求发起人',
    r2: 'R2 审批承接人员',
    r3: 'R3 镇街填报人员',
    r4: 'R4 村社区填报人员',
    r5: 'R5 审核汇总人员',
    r6: 'R6 台账管理员',
    r7: 'R7 目录管理员',
    r8: 'R8 合规与减负治理',
  };

  const ACTOR_NAMES = {
    r1: '周处长',
    r2: '刘主任',
    r3: '陈经办',
    r4: '王网格员',
    r5: '赵科长',
    r6: '孙老师',
    r7: '高主任',
    r8: '林督查',
  };

  window.STATE = {
    role: 'r1',
    discoveryQuery: '我要为本周营商环境专题复用法人单位基础信息台账模板，优先自动带出企业基础字段，只补现场差异字段。',
    brainOutage: false,
  };

  const ROUTES = [
    { test: /^#\/p1-workbench$/, page: 'workbench', nav: 'prototype' },
    { test: /^#\/p2-discovery$/, page: 'discovery', nav: 'prototype' },
    { test: /^#\/p2-discovery\/resource\/(.+)$/, page: 'resourceDetail', nav: 'prototype' },
    { test: /^#\/p3-request-flow$/, page: 'requestFlow', nav: 'prototype' },
    { test: /^#\/p3-request-flow\/request\/(.+)$/, page: 'requestDetail', nav: 'prototype' },
    { test: /^#\/p3-request-flow\/review\/(.+)$/, page: 'reviewDetail', nav: 'prototype' },
    { test: /^#\/p4-delivery-exchange$/, page: 'deliveryExchange', nav: 'prototype' },
    { test: /^#\/p4-delivery-exchange\/task\/(.+)$/, page: 'deliveryTaskDetail', nav: 'prototype' },
    { test: /^#\/p5-provider$/, page: 'provider', nav: 'prototype' },
    { test: /^#\/p6-compliance-ops$/, page: 'complianceOps', nav: 'prototype' },
    { test: /^#\/p6-compliance-ops\/dispute\/(.+)$/, page: 'disputeDetail', nav: 'prototype' },
    { test: /^#\/p7-zones-pack$/, page: 'zonesPack', nav: 'prototype' },
    { test: /^#\/p7-zones-pack\/zone\/(.+)$/, page: 'zoneDetail', nav: 'prototype' },
    { test: /^#\/p8-integration-admin$/, page: 'integrationAdmin', nav: 'prototype' },
    { test: /^#\/p8-integration-admin\/package\/(.+)$/, page: 'packageDetail', nav: 'prototype' },
    { test: /^#\/dashboard$/, page: 'dashboard', nav: 'dashboard' },
    { test: /^#\/dashboard\/alert\/(.+)$/, page: 'dashboardAlert', nav: 'dashboard' },
    { test: /^#\/$/, page: 'workbench', nav: 'prototype' },
  ];

  function pad(value) {
    return String(value).padStart(2, '0');
  }

  function nowDate() {
    const date = new Date();
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function nowDateTime() {
    const date = new Date();
    return `${nowDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function nowShortTime() {
    const date = new Date();
    return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function newAuditId() {
    const date = new Date();
    return `AE-${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
  }

  function newChainAnchor() {
    return `0x${Math.random().toString(16).slice(2, 10)}...${Math.random().toString(16).slice(2, 6)}`;
  }

  function requestById(id) {
    return window.MOCK_REQUESTS.find(item => item.id === id);
  }

  function approvalById(id) {
    return window.MOCK_APPROVALS.find(item => item.id === id);
  }

  function deliveryById(id) {
    return window.MOCK_DELIVERY_TASKS.find(item => item.id === id);
  }

  function deliveryByRequestId(id) {
    return window.MOCK_DELIVERY_TASKS.find(item => item.requestId === id);
  }

  function packageById(id) {
    return window.MOCK_CAPABILITY_PACKAGES.find(item => item.id === id);
  }

  function actorName() {
    return ACTOR_NAMES[window.STATE.role] || window.STATE.role;
  }

  function requestStatusText(item, role) {
    if (!item) return '—';
    if (item.status === 'pending') return role === 'r1' ? '审批中' : '待审批';
    if (item.status === 'supplementing') return role === 'r3' || role === 'r4' ? '待补录' : '补录中';
    if (item.status === 'summary-pending') return '待汇总确认';
    if (item.status === 'completed') return '已汇总';
    if (item.status === 'need-fix') return '待补正';
    if (item.status === 'rejected') return '已驳回';
    return item.status;
  }

  function packageStatusText(item) {
    if (!item) return '—';
    if (item.status === 'pending') return '待审核';
    if (item.status === 'pending-fix') return '待补正';
    if (item.status === 'approved') return '已上线';
    if (item.status === 'rejected') return '已驳回';
    return item.status;
  }

  function setTodoStatus(role, id, status) {
    const bucket = window.MOCK_WORKBENCH[role];
    if (!bucket) return;
    const todo = bucket.todos.find(item => item.id === id);
    if (todo) todo.status = status;
  }

  function addAuditEvent(type, target, result) {
    window.MOCK_AUDIT_EVENTS.push({
      id: newAuditId(),
      time: `${pad(new Date().getMonth() + 1)}-${pad(new Date().getDate())} ${pad(new Date().getHours())}:${pad(new Date().getMinutes())}`,
      actor: actorName(),
      type,
      target,
      result,
      chain: result === 'failed' ? 'n/a' : newChainAnchor(),
    });
  }

  function syncWorkbench() {
    const request0011 = requestById('REQ-2026-04-25-0011');
    const request0007 = requestById('REQ-2026-04-24-0007');
    const task0011 = deliveryById('DLV-2026-04-25-0011');
    const package001 = packageById('PKG-2026-04-25-001');

    setTodoStatus('r1', 'REQ-2026-04-25-0011', requestStatusText(request0011, 'r1'));
    setTodoStatus('r2', 'REQ-2026-04-25-0011', requestStatusText(request0011, 'r2'));
    setTodoStatus('r2', 'REQ-2026-04-24-0007', requestStatusText(request0007, 'r2'));
    setTodoStatus('r3', 'REQ-2026-04-25-0011', requestStatusText(request0011, 'r3'));
    setTodoStatus('r3', 'REQ-2026-04-24-0007', requestStatusText(request0007, 'r3'));
    setTodoStatus('r4', 'REQ-2026-04-25-0011', requestStatusText(request0011, 'r4'));
    setTodoStatus('r5', 'REQ-2026-04-25-0011', requestStatusText(request0011, 'r5'));
    setTodoStatus('r6', 'LEDGER-jbxx-v1.3', task0011 && task0011.backflow.status === '已确认' ? '已发布' : '待发布');
    setTodoStatus('r7', 'ZONE-business-ledger', task0011 && task0011.backflow.status === '已确认' ? '已上线' : '待更新');
    setTodoStatus('r7', 'PKG-2026-04-25-001', packageStatusText(package001));
  }

  function syncBackflowViews() {
    const task = deliveryById('DLV-2026-04-25-0011');
    const confirmed = task && task.backflow.status === '已确认';
    const discovery = window.MOCK_DISCOVERY.resources.find(item => item.id === 'res-jbxx-ledger');

    window.MOCK_PROVIDER.overview[0].value = confirmed ? 'v1.3' : 'v1.2 → v1.3';
    window.MOCK_PROVIDER.overview[2].value = confirmed ? '0' : String(task.backflow.candidateFields.length);
    window.MOCK_PROVIDER.catalogs[0].issue = confirmed ? 'v1.3 版本说明已同步' : '需补充 v1.3 版本说明';
    window.MOCK_PROVIDER.catalogs[1].status = confirmed ? '已发布' : '待质检';
    window.MOCK_PROVIDER.catalogs[1].issue = confirmed ? '默认复用入口已更新' : '需更新默认复用入口说明';
    window.MOCK_PROVIDER.resources[0].updatedAt = confirmed ? nowDate() : '2026-04-25';
    window.MOCK_PROVIDER.resources[1].status = confirmed ? '可共享' : '待审核';
    window.MOCK_PROVIDER.aiGovernance.summary = confirmed
      ? '法人模板 v1.3 已确认吸收高频差异字段，下一步重点转为持续监测补录热区和维护专题入口一致性。'
      : '建议优先发布法人模板 v1.3，并把“经营状态”“最近走访时间”纳入正式字段候选；其次更新营商环境专题目录中的默认复用入口说明。';

    if (discovery) {
      discovery.coverage = confirmed ? '89%' : '82%';
      discovery.updatedAt = confirmed ? nowDate() : '2026-04-25';
      discovery.explain = confirmed
        ? ['当前需求可直接复用 v1.3 模板，基层补录字段进一步收缩', '经营状态与最近走访时间已纳入正式字段', '专题入口与模板版本已同步更新']
        : ['当前需求首先应复用该模板，而不是重新发起整表采集', '模板已覆盖多数企业基础字段', '仅需补少量现场差异字段即可形成任务'];
    }

    window.MOCK_ZONES[0].trust = confirmed
      ? ['来源等级：高', '模板版本：v1.3，默认入口已同步', '责任方：区政数局 / 市场监管局']
      : ['来源等级：高', '模板版本：v1.2，v1.3 待发布', '责任方：区政数局 / 市场监管局'];

    window.MOCK_DASHBOARD.summary.alerts = confirmed ? '1' : '2';
    window.MOCK_DASHBOARD.burdenMetrics[1].value = confirmed ? '1 / 单任务' : '3 / 单任务';
    window.MOCK_DASHBOARD.burdenMetrics[1].trend = confirmed ? '较基线 -84%' : '较基线 -72%';
    window.MOCK_DASHBOARD.burdenMetrics[2].value = confirmed ? '96%' : '93%';
    window.MOCK_DASHBOARD.burdenMetrics[2].trend = confirmed ? '较上周 +14pt' : '较上周 +11pt';
    window.MOCK_DASHBOARD.burdenMetrics[3].value = confirmed ? '0' : '2';
    window.MOCK_DASHBOARD.burdenMetrics[3].trend = confirmed ? '已纳入模板' : '本周新增';
    window.MOCK_DASHBOARD.suggestions.body = confirmed
      ? '当前黄金链路已经闭环到模板升级，基层补录字段明显收缩。下一步重点盯住仍绕开模板发起采集的部门。'
      : '当前黄金链路已经跑通，但仍有部门绕开法人模板发起新增采集，同时经营状态字段持续高频补录，建议优先做制度提醒和模板升级。';
    window.MOCK_DASHBOARD.suggestions.evidence = confirmed
      ? ['经营状态与最近走访时间已并入模板 v1.3', '基层补录字段数已下降到 1 / 单任务', '仍有 1 条绕行类告警需要制度治理']
      : ['本周重复要数率已降至 12%，但仍有 1 条高风险绕行告警', '经营状态字段近 7 日补录 14 次', '法人模板复用后基层填报时长下降 31%'];
    window.MOCK_DASHBOARD.suggestions.nextAction = confirmed ? '继续盯住绕行告警并复盘专题入口执行情况。' : '先看绕行告警，再推动模板 v1.3 升级。';
  }

  function syncStateViews() {
    syncWorkbench();
    syncBackflowViews();
  }

  function dispatch() {
    const hash = window.location.hash || '#/p1-workbench';
    let matched = null;
    let captures = [];

    for (const route of ROUTES) {
      const result = hash.match(route.test);
      if (result) {
        matched = route;
        captures = result.slice(1);
        break;
      }
    }

    if (!matched) {
      document.getElementById('app').innerHTML = renderNotFound(hash);
      highlightNav(null);
      updateHealth();
      return;
    }

    const page = window.PAGES && window.PAGES[matched.page];
    if (typeof page !== 'function') {
      document.getElementById('app').innerHTML = renderError(`页面渲染函数缺失：${matched.page}`);
      return;
    }

    document.getElementById('app').innerHTML = page.apply(null, captures);
    highlightNav(matched.nav);
    updateHealth();
    window.scrollTo(0, 0);

    const onMount = window.PAGES && window.PAGES[matched.page + '_onMount'];
    if (typeof onMount === 'function') {
      onMount.apply(null, captures);
    }
  }

  function highlightNav(navKey) {
    document.querySelectorAll('.nav-tab').forEach(el => {
      if (el.dataset.nav === navKey) el.classList.add('active');
      else el.classList.remove('active');
    });
  }

  function updateHealth() {
    const brain = document.getElementById('health-brain');
    const dash = document.getElementById('health-dashboard');
    if (brain) {
      brain.className = window.STATE.brainOutage ? 'text-amber-300' : 'text-green-300';
      brain.textContent = window.STATE.brainOutage ? '△' : '✓';
    }
    if (dash) {
      dash.className = 'text-green-300';
      dash.textContent = '✓';
    }
  }

  function renderNotFound(hash) {
    return `
      <div class="bg-white rounded-lg p-10 text-center border border-zw-line">
        <div class="text-2xl mb-3">404</div>
        <p class="text-zw-mute mb-4">没有匹配的路由：<code>${hash}</code></p>
        <a href="#/p1-workbench" class="inline-block bg-zw-primary text-white px-4 py-2 rounded text-sm">回到工作台</a>
      </div>`;
  }

  function renderError(message) {
    return `<div class="bg-red-50 border border-red-200 text-red-700 p-4 rounded">${message}</div>`;
  }

  window.__dispatchPrototype = dispatch;

  window.UI = {
    toast(message, type = 'info') {
      const toast = document.createElement('div');
      const color = type === 'error' ? 'bg-red-600' : type === 'success' ? 'bg-green-600' : 'bg-zw-primary';
      toast.className = `fixed top-20 right-6 ${color} text-white px-4 py-2 rounded shadow-lg z-50 text-sm`;
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2200);
    },
    roleLabel(role) {
      return ROLE_NAMES[role] || role;
    },
    can(roles) {
      return !roles || roles.includes(window.STATE.role);
    },
  };

  window.ACTIONS = {
    setDiscoveryQuery(event) {
      event.preventDefault();
      const input = document.getElementById('discovery-q');
      window.STATE.discoveryQuery = input ? input.value.trim() : '';
      if (!window.STATE.discoveryQuery) {
        window.UI.toast('请输入要检索的涉企需求', 'error');
        return;
      }
      window.UI.toast('已按真实业务语义重排复用建议', 'success');
      dispatch();
    },
    submitRequest(requestId = 'REQ-2026-04-25-0011') {
      const request = requestById(requestId);
      if (!request) {
        window.UI.toast('未找到申请单', 'error');
        return;
      }
      if (request.status !== 'need-fix') {
        window.location.hash = `#/p3-request-flow/request/${requestId}`;
        return;
      }

      request.status = 'pending';
      request.submittedAt = nowDateTime();
      request.auditId = newAuditId();
      request.chainAnchor = 'pending';
      request.timeline.push({
        label: '已补齐后重新提交',
        time: nowDateTime(),
        note: '申请已重新进入受控准入，等待审批承接人员判定。',
      });
      request.aiStatus.summary = '申请已按“模板复用 + 差异补录”方式重新提交，当前重新回到受控准入阶段。';
      request.aiStatus.nextAction = '建议审批承接人员重新核对差异字段责任边界。';

      const delivery = deliveryByRequestId(requestId);
      if (delivery) {
        delivery.status = 'warning';
        delivery.updatedAt = nowDateTime();
        delivery.note = '申请已重新提交，等待准入判定后再决定是否进入基层补录链路。';
        delivery.history.push({ time: nowShortTime(), state: '重新提交待判定', detail: '补齐后重新进入受控准入，未直接下发基层任务。' });
        delivery.aiSummary.summary = '当前仍处于准入判定前，不应提前下发基层任务。';
        delivery.aiSummary.nextAction = '请先完成审批承接，再决定是否进入补录链路。';
      }

      addAuditEvent('request.resubmit', requestId, 'ok');
      syncStateViews();
      window.UI.toast('已重新提交并进入受控准入', 'success');
      window.location.hash = `#/p3-request-flow/request/${requestId}`;
    },
    approveRequest(requestId) {
      const request = requestById(requestId);
      const approval = approvalById(requestId);
      const delivery = deliveryByRequestId(requestId);
      if (!request || request.status !== 'pending') {
        window.UI.toast('当前状态不能直接通过', 'error');
        return;
      }

      request.status = 'supplementing';
      request.chainAnchor = request.chainAnchor === 'pending' ? newChainAnchor() : request.chainAnchor;
      request.timeline.push({
        label: '审批通过并下发补录',
        time: nowDateTime(),
        note: '已进入镇街 / 社区差异补录阶段，基层只需补现场差异字段。',
      });
      request.aiStatus.summary = '申请已通过准入判定，系统正在按模板预填并等待基层补录差异字段。';
      request.aiStatus.nextAction = '请 R3 / R4 核对预填字段后提交差异补录。';

      if (approval) {
        approval.suggestion = '建议通过';
        approval.impact = '已创建基层预填任务，待补录完成后进入自动汇总确认。';
      }

      if (delivery) {
        delivery.status = 'supplementing';
        delivery.updatedAt = nowDateTime();
        delivery.note = '预填任务已下发，等待 R3 / R4 完成差异补录。';
        delivery.history.push({ time: nowShortTime(), state: '预填任务已下发', detail: '系统已把共享模板字段下发到基层，只保留差异字段待补录。' });
        delivery.aiSummary.summary = '任务已进入“预填下发 → 差异补录”阶段，当前不需要人工拼表。';
        delivery.aiSummary.nextAction = '请基层完成经营状态、最近走访时间和现场备注补录。';
        delivery.aiSummary.cause = '审批已通过，模板字段可直接作为补录底座。';
        delivery.aiSummary.impact = '补录完成后会自动生成汇总结果并沉淀回流候选。';
        delivery.backflow.status = '待补录完成';
        delivery.backflow.note = '待基层补录和审核汇总完成后，再决定是否纳入模板。';
      }

      addAuditEvent('request.approve', requestId, 'ok');
      syncStateViews();
      dispatch();
      window.UI.toast('已通过并下发基层补录任务', 'success');
    },
    returnForFix(requestId) {
      const request = requestById(requestId);
      const approval = approvalById(requestId);
      const delivery = deliveryByRequestId(requestId);
      if (!request || !['pending', 'summary-pending'].includes(request.status)) {
        window.UI.toast('当前状态不能退回补正', 'error');
        return;
      }

      request.status = 'need-fix';
      request.timeline.push({
        label: '已退回补正',
        time: nowDateTime(),
        note: '要求重新说明差异字段责任边界或补齐异常项说明。',
      });
      request.aiStatus.summary = '申请已退回补正，当前不进入下一状态。';
      request.aiStatus.nextAction = '请补齐差异字段说明后重新提交。';

      if (approval) {
        approval.suggestion = '建议补正';
        approval.impact = '退回补正后，补录与汇总链路暂停，不继续向前推进。';
      }

      if (delivery) {
        delivery.status = 'warning';
        delivery.updatedAt = nowDateTime();
        delivery.note = '当前链路已退回补正，未继续推进补录或汇总。';
        delivery.history.push({ time: nowShortTime(), state: '退回补正', detail: '因责任边界或异常项说明不足，链路暂停。' });
        delivery.aiSummary.summary = '这不是执行失败，而是人工决定链路回退补正。';
        delivery.aiSummary.nextAction = '请申请方或基层先补齐说明，再重新进入下一步。';
        delivery.backflow.status = '不适用';
        delivery.backflow.note = '当前未形成可确认的回流候选。';
      }

      addAuditEvent('request.return-for-fix', requestId, 'warning');
      syncStateViews();
      dispatch();
      window.UI.toast('已退回补正', 'success');
    },
    rejectRequest(requestId) {
      const request = requestById(requestId);
      const delivery = deliveryByRequestId(requestId);
      if (!request || !['pending', 'summary-pending'].includes(request.status)) {
        window.UI.toast('当前状态不能驳回', 'error');
        return;
      }

      request.status = 'rejected';
      request.timeline.push({
        label: '已驳回申请',
        time: nowDateTime(),
        note: '因重复要数或越界采集风险被终止。',
      });
      request.aiStatus.summary = '该申请已被明确驳回，不再继续进入补录和汇总链路。';
      request.aiStatus.nextAction = '如需继续，请改为模板复用 + 差异补录模式重新发起。';

      if (delivery) {
        delivery.status = 'warning';
        delivery.updatedAt = nowDateTime();
        delivery.note = '申请已驳回，链路终止。';
        delivery.history.push({ time: nowShortTime(), state: '申请驳回', detail: '因重复要数或越界采集风险，任务未继续推进。' });
        delivery.aiSummary.summary = '这是一次被明确终止的链路，不应伪装成业务成功。';
        delivery.aiSummary.nextAction = '如需重启，请先回到模板复用起点重新收敛需求。';
        delivery.backflow.status = '不适用';
        delivery.backflow.note = '驳回后不生成回流候选。';
      }

      addAuditEvent('request.reject', requestId, 'warning');
      syncStateViews();
      dispatch();
      window.UI.toast('已驳回该申请', 'success');
    },
    submitSupplement(requestId) {
      const request = requestById(requestId);
      const delivery = deliveryByRequestId(requestId);
      if (!request || request.status !== 'supplementing') {
        window.UI.toast('当前还不在补录阶段', 'error');
        return;
      }

      request.status = 'summary-pending';
      request.diffFields = [
        { label: '经营状态', value: '正常经营', reason: '现场状态变化快', owner: 'R3/R4 补录', state: '已补录' },
        { label: '最近走访时间', value: nowDate(), reason: '共享池无现场时间', owner: 'R4 补录', state: '已补录' },
        { label: '现场备注', value: '已完成走访核验，无新增异常。', reason: '仅末端掌握', owner: 'R3/R4 补录', state: '已补录' },
      ];
      request.summaryResult.note = '基层差异字段已全部回收，系统已生成自动汇总结果，待 R5 确认异常项。';
      request.timeline.push({
        label: '差异补录已提交',
        time: nowDateTime(),
        note: '基层已提交现场差异字段，系统已自动进入汇总确认阶段。',
      });
      request.aiStatus.summary = '差异补录已提交，系统已完成自动汇总并等待 R5 处理异常项。';
      request.aiStatus.nextAction = '请 R5 查看自动汇总结果并确认异常项。';

      if (delivery) {
        delivery.status = 'reconciling';
        delivery.updatedAt = nowDateTime();
        delivery.note = '基层补录已完成，自动汇总结果待审核汇总人员确认。';
        delivery.history.push({ time: nowShortTime(), state: '基层补录完成', detail: '差异字段已回收，系统已生成汇总草稿和回流候选。' });
        delivery.aiSummary.summary = '链路已进入“自动汇总 → 异常确认 → 回流候选”阶段。';
        delivery.aiSummary.nextAction = '请 R5 确认异常项，再由 R6 / R7 决定是否纳入模板。';
        delivery.aiSummary.cause = '基层只补差异字段，因此系统可直接生成汇总结果。';
        delivery.aiSummary.impact = '确认完成后可把高频差异字段推进到模板治理侧。';
        delivery.backflow.status = '待确认';
        delivery.backflow.note = '差异字段已具备来源与责任方，待汇总确认后进入供给侧确认。';
      }

      addAuditEvent('supplement.submit', requestId, 'ok');
      syncStateViews();
      dispatch();
      window.UI.toast('差异补录已提交，进入汇总确认', 'success');
    },
    confirmSummary(requestId) {
      const request = requestById(requestId);
      const delivery = deliveryByRequestId(requestId);
      if (!request || request.status !== 'summary-pending') {
        window.UI.toast('当前还不能确认汇总', 'error');
        return;
      }

      request.status = 'completed';
      request.summaryResult.note = 'R5 已确认自动汇总结果，链路进入回流候选确认。';
      request.timeline.push({
        label: '已确认自动汇总',
        time: nowDateTime(),
        note: '异常项已处理完成，回流候选进入供给侧确认阶段。',
      });
      request.aiStatus.summary = '自动汇总已确认，当前只剩回流候选是否正式纳入模板。';
      request.aiStatus.nextAction = '请 R6 / R7 确认回流候选并同步模板版本与专题入口。';

      if (delivery) {
        delivery.status = 'reconciling';
        delivery.updatedAt = nowDateTime();
        delivery.note = '汇总已确认，等待 R6 / R7 决定回流是否正式生效。';
        delivery.history.push({ time: nowShortTime(), state: '汇总确认完成', detail: '异常项已由 R5 确认，任务转入回流确认。' });
        delivery.aiSummary.summary = '业务汇总已经闭环，当前重心转到模板治理和回流生效。';
        delivery.aiSummary.nextAction = '请确认是否把经营状态和最近走访时间纳入模板 v1.3。';
        delivery.aiSummary.cause = '自动汇总结果已被人工确认，可进入供给侧治理动作。';
        delivery.aiSummary.impact = '回流确认后，下次类似需求的基层补录字段会进一步下降。';
        delivery.backflow.status = '待确认';
        delivery.backflow.note = '回流候选已具备业务证据，待台账管理员与目录管理员确认。';
      }

      addAuditEvent('summary.confirm', requestId, 'ok');
      syncStateViews();
      dispatch();
      window.UI.toast('已确认自动汇总，进入回流确认', 'success');
    },
    confirmBackflow(taskId) {
      const task = deliveryById(taskId);
      const request = task ? requestById(task.requestId) : null;
      if (!task || !request || request.status !== 'completed' || task.backflow.status === '已确认') {
        window.UI.toast('当前还不能确认回流', 'error');
        return;
      }

      task.status = 'completed';
      task.updatedAt = nowDateTime();
      task.note = '高频差异字段已确认纳入法人单位基础信息模板 v1.3。';
      task.history.push({ time: nowShortTime(), state: '回流确认完成', detail: '经营状态与最近走访时间已正式纳入模板 v1.3。' });
      task.aiSummary.summary = '这条链路已经从一次性补录沉淀成下一次可直接复用的模板能力。';
      task.aiSummary.nextAction = '请回到 P5 / P7 检查模板版本与专题入口是否同步完成。';
      task.aiSummary.cause = '高频差异字段已经过一次真实业务验证，并具备明确来源与责任方。';
      task.aiSummary.impact = '下次类似需求将进一步减少基层补录工作量。';
      task.backflow.status = '已确认';
      task.backflow.note = '经营状态、最近走访时间已纳入法人单位基础信息模板 v1.3。';

      addAuditEvent('backflow.confirm', task.backflow.candidateObject, 'ok');
      syncStateViews();
      dispatch();
      window.UI.toast('已确认回流并同步模板治理视图', 'success');
    },
    approvePackage(packageId) {
      const item = packageById(packageId);
      if (!item || item.status === 'approved') {
        window.UI.toast('当前无需重复批准', 'error');
        return;
      }
      item.status = 'approved';
      item.aiReview.summary = '该能力包已通过审核，并限制在只读辅助暴露面内生效。';
      item.aiReview.draft = '审核结论：批准上线，继续保持只读辅助能力边界，不得声明主状态写权。';
      addAuditEvent('package.approve', packageId, 'ok');
      syncStateViews();
      dispatch();
      window.UI.toast('能力包已批准上线', 'success');
    },
    returnPackageFix(packageId) {
      const item = packageById(packageId);
      if (!item) {
        window.UI.toast('未找到能力包', 'error');
        return;
      }
      item.status = 'pending-fix';
      item.aiReview.summary = '该能力包需要先补齐租户范围或 side effects 声明，当前不进入上线。';
      addAuditEvent('package.return-for-fix', packageId, 'warning');
      syncStateViews();
      dispatch();
      window.UI.toast('能力包已退回补充', 'success');
    },
    rejectPackage(packageId) {
      const item = packageById(packageId);
      if (!item) {
        window.UI.toast('未找到能力包', 'error');
        return;
      }
      item.status = 'rejected';
      item.aiReview.summary = '该能力包因越界写权或暴露面设计不合规被驳回。';
      item.aiReview.draft = '审核结论：驳回。请回到单一契约并撤销越界写权声明后再重新提交。';
      addAuditEvent('package.reject', packageId, 'warning');
      syncStateViews();
      dispatch();
      window.UI.toast('能力包已驳回', 'success');
    },
    toggleOutage() {
      window.STATE.brainOutage = !window.STATE.brainOutage;
      dispatch();
    },
    noop(message) {
      window.UI.toast(message || '该操作在原型中仅演示主旅程与边界', 'info');
    },
  };

  document.getElementById('role-switch').addEventListener('change', event => {
    window.STATE.role = event.target.value;
    dispatch();
  });

  window.addEventListener('hashchange', dispatch);
  window.addEventListener('DOMContentLoaded', () => {
    syncStateViews();
    const switcher = document.getElementById('role-switch');
    if (switcher) switcher.value = window.STATE.role;
    if (!window.location.hash) {
      window.location.hash = '#/p1-workbench';
    } else {
      dispatch();
    }
  });
})();
