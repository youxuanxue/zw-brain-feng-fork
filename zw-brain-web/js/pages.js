window.PAGES = {};

function roleLabel(role) {
  return {
    r1: '上级业务需求发起人',
    r2: '审批承接人员',
    r3: '镇街填报人员',
    r4: '村社区填报人员',
    r5: '审核汇总人员',
    r6: '台账管理员',
    r7: '目录管理员',
    r8: '合规与减负治理',
  }[role] || role;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Count items likely needing human attention on the main chain (best-effort from snapshot). */
function pendingHumanConfirmCount(role) {
  const wb = window.RUNTIME_WORKBENCH && window.RUNTIME_WORKBENCH[role];
  const todos = (wb && wb.todos) || [];
  const busy = todos.filter(t => {
    const s = String((t && t.status) || '');
    return /待|审批|补录|核查|确认|处理中|预警|告警|拦截|异常/.test(s);
  }).length;
  const listLen = (window.RUNTIME_ALERTS || []).length;
  let dashN = 0;
  if (window.RUNTIME_DASHBOARD && window.RUNTIME_DASHBOARD.summary) {
    const p = parseInt(String(window.RUNTIME_DASHBOARD.summary.alerts || '0'), 10);
    if (Number.isFinite(p) && p >= 0) dashN = p;
  }
  const alertBucket = Math.max(listLen, dashN);
  return busy + alertBucket;
}

function humanConfirmPillText(role) {
  const n = pendingHumanConfirmCount(role);
  return n > 0 ? `今日需人工确认 ${n} 项` : '当前暂无待人工确认项（仍以经办人现场核实为准）';
}

function renderDashboardShortcutLink() {
  const href = window.ZW_WEBUI && window.ZW_WEBUI.dashboardHref;
  if (!href) {
    return '<span class="text-body-sm text-zw-mute leading-7">独立大屏入口未配置（运维侧设置 ZW_BRAIN_WEBUI_DASHBOARD_URL）</span>';
  }
  const safe = escapeHtml(href);
  return `<a href="${safe}" target="_blank" rel="noopener noreferrer">我要看独立大屏</a>`;
}

const STATUS_LABELS = {
  open: '待核查',
  escalated: '已升级',
  resolved: '已解决',
  provider_investigating: '提供方核查中',
  ok: '成功',
  warning: '待处理',
  failed: '失败',
  reconciling: '待汇总确认',
  supplementing: '待补录',
  'summary-pending': '待汇总确认',
  completed: '已完成',
  approved: '已上线',
  pending: '待审批',
  'pending-fix': '待补正',
  rejected: '已驳回',
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function backflowStatusKey(status) {
  return {
    '待补录完成': 'pending_supplement',
    '待确认': 'pending_confirmation',
    '已确认': 'confirmed',
    '不适用': 'not_applicable',
  }[status] || status;
}

function statusPill(status) {
  const map = {
    '可复用': 'status-ok',
    '可申请': 'status-ok',
    '可查看': 'status-neutral',
    '可共享': 'status-ok',
    '待审批': 'status-warn',
    '审批中': 'status-warn',
    '待补正': 'status-warn',
    '待补录': 'status-warn',
    '补录中': 'status-warn',
    '待修改': 'status-warn',
    '待汇总确认': 'status-warn',
    '待回流确认': 'status-warn',
    '待发布': 'status-warn',
    '待核查': 'status-warn',
    '待更新': 'status-warn',
    '待处理': 'status-warn',
    '处理中': 'status-warn',
    '告警': 'status-danger',
    '已上线': 'status-ok',
    '已发布': 'status-ok',
    '已完成': 'status-ok',
    '已汇总': 'status-ok',
    '待质检': 'status-warn',
    '待审核': 'status-warn',
    '在线': 'status-ok',
    open: 'status-warn',
    escalated: 'status-danger',
    resolved: 'status-ok',
    provider_investigating: 'status-warn',
    ok: 'status-ok',
    warning: 'status-warn',
    failed: 'status-danger',
    reconciling: 'status-warn',
    supplementing: 'status-warn',
    'summary-pending': 'status-warn',
    completed: 'status-ok',
    approved: 'status-ok',
    pending: 'status-warn',
    'pending-fix': 'status-warn',
    rejected: 'status-danger',
    '已派单': 'status-neutral',
    '筹建中': 'status-neutral',
    '不适用': 'status-neutral',
  };
  return `<span class="status-pill ${map[status] || 'status-neutral'}">${statusLabel(status)}</span>`;
}

function crumbs(items) {
  return `
    <nav class="text-body-sm text-zw-mute mb-2 flex items-center gap-2 flex-wrap crumbs">
      ${items.map((it, i) => i === items.length - 1
        ? `<span class="text-zw-ink">${it.label}</span>`
        : `<a href="${it.href}">${it.label}</a><span class="crumb-sep">/</span>`
      ).join('')}
    </nav>`;
}

function stepBar(steps, activeIdx) {
  return `
    <div class="flex items-center gap-2 text-caption text-zw-mute flex-wrap">
      ${steps.map((s, i) => `
        <span class="step-dot ${i < activeIdx ? 'done' : i === activeIdx ? 'now' : 'todo'}">${i < activeIdx ? '✓' : i + 1}</span>
        <span class="${i === activeIdx ? 'text-zw-ink font-medium' : ''}">${s}</span>
        ${i < steps.length - 1 ? '<span class="opacity-30">───</span>' : ''}
      `).join('')}
    </div>`;
}

function statCards(items) {
  return `
    <div class="grid gov-stats-grid gap-4">
      ${items.map(item => {
        const inner = `
          <div class="gov-stat-label">${item.label}</div>
          <div class="gov-stat-value">${item.value}</div>
          ${item.note ? `<div class="gov-stat-note">${item.note}</div>` : ''}
          ${item.href ? '<div class="gov-stat-action">查看</div>' : ''}`;
        return item.href
          ? `<a href="${item.href}" class="gov-stat-card gov-stat-link">${inner}</a>`
          : `<div class="gov-stat-card">${inner}</div>`;
      }).join('')}
    </div>`;
}

function infoList(items) {
  return `
    <div class="gov-list">
      ${items.map(item => `
        <div class="gov-list-row">
          <div>
            <div class="row-title">${item.title}</div>
            <div class="row-meta">${item.status}</div>
          </div>
          <a href="${item.href}" class="row-actions">查看</a>
        </div>`).join('')}
    </div>`;
}

function renderInlineSummary(summary, actions) {
  return `
    <div class="panel" data-ai-surface="inline-summary">
      <div class="panel-body py-4">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div class="text-body leading-7 text-zw-ink flex-1">${summary}</div>
          ${actions && actions.length ? `<div class="flex flex-wrap gap-2 justify-end">${actions.map(item => `<span class="ai-tag">${item}</span>`).join('')}</div>` : ''}
        </div>
      </div>
    </div>`;
}

function renderDraftCard(title, lines, note) {
  return `
    <div class="draft-card" data-ai-surface="draft-card">
      <div class="draft-title">${title}</div>
      <div class="explain-list">${lines.map(line => `<div>${line}</div>`).join('')}</div>
      ${note ? `<div class="mt-3 text-body-sm text-zw-mute leading-7">${note}</div>` : ''}
    </div>`;
}

function renderFieldState(label, value, state, note) {
  const chip = state === '已预填' || state === '已识别' ? 'chip-ok' : 'chip-ask';
  return `
    <div class="panel p-3 bg-zw-bg-soft rounded-lg">
      <div class="row-meta mb-1">${label}</div>
      <div class="row-title">${value}</div>
      <div class="mt-2 flex items-center gap-2 flex-wrap">
        <span class="chip ${chip}">${state}</span>
        ${note ? `<span class="text-body-sm text-zw-mute">${note}</span>` : ''}
      </div>
    </div>`;
}

function actionNotice(message) {
  return `<span class="action-note">${message}</span>`;
}

function panel(title, subtitle, body, extraClass = '') {
  return `
    <div class="panel ${extraClass}">
      <div class="panel-body">
        <div class="panel-title">${title}</div>
        ${subtitle ? `<div class="panel-subtitle">${subtitle}</div>` : ''}
        <div class="mt-4">${body}</div>
      </div>
    </div>`;
}

function summaryRouteForRole(role, requestId) {
  return role === 'r2' || role === 'r5' ? `#/p3-request-flow/review/${requestId}` : `#/p3-request-flow/request/${requestId}`;
}

function deliveryByRequestId(requestId) {
  return (window.RUNTIME_DELIVERY_TASKS || []).find(item => item.requestId === requestId);
}

function activeRequest() {
  return (window.RUNTIME_REQUESTS || [])[0];
}

function activeDelivery() {
  const request = activeRequest();
  return request ? deliveryByRequestId(request.id) || (window.RUNTIME_DELIVERY_TASKS || [])[0] : (window.RUNTIME_DELIVERY_TASKS || [])[0];
}

function requestStatusLabel(item, role = window.STATE.role) {
  if (!item) return '—';
  if (item.status === 'pending') return role === 'r1' ? '审批中' : '待审批';
  if (item.status === 'supplementing') return role === 'r3' || role === 'r4' ? '待补录' : '补录中';
  if (item.status === 'summary-pending') return '待汇总确认';
  if (item.status === 'completed') return '已汇总';
  if (item.status === 'need-fix') return '待补正';
  if (item.status === 'rejected') return '已驳回';
  return item.status;
}

function deliveryStatusLabel(task, request) {
  if (!task) return '—';
  if (backflowStatusKey(task.backflow?.status) === 'confirmed') return '已完成';
  if (task.status === 'supplementing') return '待补录';
  if (task.status === 'reconciling') {
    return request?.status === 'completed' ? '待回流确认' : '待汇总确认';
  }
  if (task.status === 'completed') return '已完成';
  if (task.status === 'warning') return '待处理';
  return task.status;
}

function packageStatusLabel(item) {
  if (!item) return '—';
  if (item.status === 'pending') return '待审核';
  if (item.status === 'pending-fix') return '待补正';
  if (item.status === 'approved') return '已上线';
  if (item.status === 'rejected') return '已驳回';
  return item.status;
}

function requestStepIndex(item, role = window.STATE.role) {
  if (!item) return 0;
  if (item.status === 'pending') return role === 'r1' ? 2 : 2;
  if (item.status === 'supplementing') return 3;
  if (item.status === 'summary-pending') return 4;
  if (item.status === 'completed') return 5;
  if (item.status === 'need-fix') return 2;
  return 1;
}

function requestActionBar(item, role = window.STATE.role) {
  const isGrassroots = role === 'r3' || role === 'r4';
  if (!item) return '';
  if (!isGrassroots && item.status === 'need-fix') {
    return `
      <button onclick="window.ACTIONS.submitRequest('${item.id}')" class="gov-btn gov-btn-primary">补齐后重新提交</button>
      ${actionNotice('当前需补齐差异字段责任说明')}`;
  }
  if (!isGrassroots && item.status === 'pending') {
    return `
      <a href="#/p3-request-flow/review/${item.id}" class="gov-btn gov-btn-primary">进入审批详情</a>
      ${actionNotice('申请已进入受控准入，当前等待审批承接人员处理')}`;
  }
  if (isGrassroots && item.status === 'supplementing') {
    return `
      <button onclick="window.ACTIONS.submitSupplement('${item.id}')" class="gov-btn gov-btn-primary">提交差异补录</button>
      ${actionNotice('这里只补动态差异字段，不需要重新整表录入')}`;
  }
  if (item.status === 'summary-pending') {
    return `
      <a href="#/p3-request-flow/review/${item.id}" class="gov-btn gov-btn-primary">查看汇总确认</a>
      ${actionNotice('当前链路已进入自动汇总确认，等待审核汇总人员处理异常项')}`;
  }
  if (item.status === 'completed') {
    const delivery = deliveryByRequestId(item.id);
    return `
      <a href="#/p4-delivery-exchange${delivery ? `/task/${delivery.id}` : ''}" class="gov-btn gov-btn-primary">查看回流确认</a>
      ${actionNotice('自动汇总已经确认完成，下一步是供给侧确认回流候选')}`;
  }
  if (item.status === 'rejected') {
    return `
      ${actionNotice('该申请已驳回，如需继续请回到模板复用起点重新收敛需求')}`;
  }
  return `
    ${actionNotice('当前阶段没有新的责任写动作')}`;
}

function businessNavLabel(key) {
  return {
    p1: '首页工作台',
    p2: '数据资源发现',
    p3: '共享申请与审批',
    p4: '交付交换与回流',
    p5: '数据供给管理',
    p6: '合规运营与减负',
    p7: '共享专区 / 专题包',
    p8: '平台接入管理',
  }[key] || key;
}

function isBusinessNavCollapsed() {
  try {
    return window.localStorage.getItem('zw-brain-nav-collapsed') === '1';
  } catch (_) {
    return false;
  }
}

function workbenchDrillHintFromHref(href) {
  if (!href || href === '#') return '进入办理';
  const path = String(href).replace(/^#\/?/, '/');
  if (path.includes('/p3-request-flow/review/')) return '打开审批或汇总办理';
  if (path.includes('/p3-request-flow/request/')) return '打开申请与补录进度';
  if (path.includes('/p2-discovery/resource/')) return '打开目录资源详情';
  if (path.includes('/p4-delivery-exchange/task/')) return '打开交付任务与回流';
  if (path.includes('/p4-delivery-exchange')) return '打开交付交换';
  if (path.includes('/p6-compliance-ops/dispute/')) return '打开争议与责任链';
  if (path.includes('/p6-compliance-ops')) return '打开合规运营';
  if (path.includes('/p5-provider')) return '打开供给与模板治理';
  if (path.includes('/p7-zones-pack/zone/')) return '打开专区详情';
  if (path.includes('/p7-zones-pack')) return '打开共享专区';
  if (path.includes('/p8-integration-admin/package/')) return '打开能力包审核';
  if (path.includes('/p8-integration-admin/iam-governance')) return '打开身份与权限治理';
  if (path.includes('/p8-integration-admin')) return '打开平台接入管理';
  if (path.includes('/dashboard/')) return '打开关联告警视图';
  if (path.includes('/p2-discovery')) return '打开数据资源发现';
  if (path.includes('/p3-request-flow')) return '打开共享申请列表';
  return '进入办理';
}

function renderWorkbenchDrillStrip(todos) {
  const list = Array.isArray(todos) ? todos.filter(t => t && t.href && t.title) : [];
  if (!list.length) {
    return `
    <div class="workbench-drill-strip mt-5" role="region" aria-label="待办深链">
      <div class="workbench-drill-kicker">待办深链</div>
      <div class="workbench-drill-empty">当前暂无由工作台生成的待办深链，请从下方指标卡片进入各业务场景。</div>
    </div>`;
  }
  const cards = list.map(todo => `
    <a href="${escapeHtml(todo.href)}">
      <span>${escapeHtml(todo.status || '待办')}</span>
      <strong>${escapeHtml(todo.title)}</strong>
      <em>${escapeHtml(workbenchDrillHintFromHref(todo.href))}</em>
    </a>`).join('');
  return `
    <div class="workbench-drill-strip mt-5" role="region" aria-label="待办深链">
      <div class="workbench-drill-kicker">待办深链 · 按当前身份工作台待办自动生成</div>
      <div class="workbench-value-grid workbench-value-grid--drill">${cards}</div>
    </div>`;
}

function shell(activeKey, mainHtml) {
  const role = window.STATE.role;
  const navCollapsed = isBusinessNavCollapsed();
  const nav = [
    { key: 'p1', label: '首页工作台', href: '#/p1-workbench', roles: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'], desc: '待办、指标、智能建议' },
    { key: 'p2', label: '数据资源发现', href: '#/p2-discovery', roles: ['r1', 'r2', 'r6', 'r7', 'r8'], desc: '先找模板和专题资产' },
    { key: 'p3', label: '共享申请与审批', href: '#/p3-request-flow', roles: ['r1', 'r2', 'r3', 'r4', 'r5'], desc: '申请、准入、补录、汇总' },
    { key: 'p4', label: '交付交换与回流', href: '#/p4-delivery-exchange', roles: ['r2', 'r5', 'r6', 'r7', 'r8'], desc: '交付回执与模板回流' },
    { key: 'p5', label: '数据供给管理', href: '#/p5-provider', roles: ['r6', 'r7'], desc: '目录、资源、服务治理' },
    { key: 'p6', label: '合规运营与减负', href: '#/p6-compliance-ops', roles: ['r2', 'r5', 'r6', 'r7', 'r8'], desc: '重复要数与证据回放' },
    { key: 'p7', label: '共享专区 / 专题包', href: '#/p7-zones-pack', roles: ['r1', 'r2', 'r6', 'r7', 'r8'], desc: '一表通等场景包入口' },
    { key: 'p8', label: '平台接入管理', href: '#/p8-integration-admin', roles: ['r7'], desc: '外部能力受控接入' },
  ];

  return `
    <div class="product-shell-grid ${navCollapsed ? 'is-shell-nav-collapsed' : ''}">
      <aside class="product-shell-aside">
        <div class="product-shell-stack">
          <div class="panel product-nav-panel">
            <div class="product-nav-collapsed-rail" aria-hidden="${navCollapsed ? 'false' : 'true'}">
              <button type="button"
                      class="product-nav-rail-expand"
                      data-business-nav-toggle
                      aria-controls="product-nav-panel-body"
                      aria-expanded="${navCollapsed ? 'false' : 'true'}"
                      title="展开业务导航（向右）"
                      aria-label="展开业务导航"
                      onclick="window.UI.toggleBusinessNavCollapse()">›</button>
            </div>
            <div class="product-nav-expanded" id="product-nav-panel-body-wrap" aria-hidden="${navCollapsed ? 'true' : 'false'}">
              <div class="panel-body">
                <div class="product-nav-panel-top">
                  <div class="panel-title product-nav-panel-title">业务导航</div>
                  <button type="button"
                          class="product-nav-collapse-btn product-nav-collapse-btn--icon"
                          data-business-nav-toggle
                          aria-controls="product-nav-panel-body"
                          aria-expanded="${navCollapsed ? 'false' : 'true'}"
                          title="收起业务导航（向左）"
                          aria-label="收起业务导航"
                          onclick="window.UI.toggleBusinessNavCollapse()">‹</button>
                </div>
                <div id="product-nav-panel-body" class="product-nav-panel-collapsible">
                  <div class="panel-subtitle">按当前岗位展示能办、待办和已办事项。</div>
                  <div class="product-role-chip">当前身份：${roleLabel(role)}</div>
                  <div class="mt-4 space-y-1.5">
                    ${nav.map(item => {
                    const allowed = item.roles.includes(role);
                    const isActive = item.key === activeKey;
                    return `
                    <a href="${allowed ? item.href : '#'}"
                       ${allowed ? '' : 'onclick="event.preventDefault();window.UI.toast(\'当前身份暂无访问权限\',\'info\')"'}
                       class="product-nav-link ${isActive ? 'is-active' : ''} ${allowed ? '' : 'is-disabled'}">
                      <span><strong>${item.label}</strong><em>${item.desc}</em></span>
                      <span class="product-nav-state">${allowed ? (isActive ? '当前' : '进入') : '受限'}</span>
                    </a>`;
                  }).join('')}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
      <section class="product-shell-main">${mainHtml}</section>
    </div>`;
}

/** 与侧栏 `shell` 内 `nav[].roles` 一致；服务端预加载裁剪见 `zw_brain/domain/web_snapshot_redaction.py` */
window.ZW_PAGE_ACCESS = {
  workbench: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'],
  discovery: ['r1', 'r2', 'r6', 'r7', 'r8'],
  catalogBrowse: ['r1', 'r2', 'r6', 'r7', 'r8'],
  resourceDetail: ['r1', 'r2', 'r6', 'r7', 'r8'],
  requestFlow: ['r1', 'r2', 'r3', 'r4', 'r5'],
  requestDetail: ['r1', 'r2', 'r3', 'r4', 'r5'],
  reviewDetail: ['r1', 'r2', 'r3', 'r4', 'r5'],
  deliveryExchange: ['r2', 'r5', 'r6', 'r7', 'r8'],
  deliveryTaskDetail: ['r2', 'r5', 'r6', 'r7', 'r8'],
  provider: ['r6', 'r7'],
  complianceOps: ['r2', 'r5', 'r6', 'r7', 'r8'],
  disputeDetail: ['r2', 'r5', 'r6', 'r7', 'r8'],
  zonesPack: ['r1', 'r2', 'r6', 'r7', 'r8'],
  zoneDetail: ['r1', 'r2', 'r6', 'r7', 'r8'],
  integrationAdmin: ['r7'],
  iamGovernance: ['r7'],
  packageDetail: ['r7'],
};

window.ZW_PAGE_SHELL = {
  workbench: 'p1',
  discovery: 'p2',
  catalogBrowse: 'p2',
  resourceDetail: 'p2',
  requestFlow: 'p3',
  requestDetail: 'p3',
  reviewDetail: 'p3',
  deliveryExchange: 'p4',
  deliveryTaskDetail: 'p4',
  provider: 'p5',
  complianceOps: 'p6',
  disputeDetail: 'p6',
  zonesPack: 'p7',
  zoneDetail: 'p7',
  integrationAdmin: 'p8',
  iamGovernance: 'p8',
  packageDetail: 'p8',
};

function entityNotFoundShell(activeKey, entityLabel, rawId, backHref, backLabel) {
  const id = escapeHtml(String(rawId || ''));
  const label = escapeHtml(entityLabel);
  const safeBack = backHref ? escapeHtml(backHref) : '#/p1-workbench';
  const backText = escapeHtml(backLabel || '回到首页工作台');
  const main = `
    <div class="bg-white rounded-2xl p-10 text-center border-default shadow-soft">
      <div class="text-display mb-3">未找到${label}</div>
      <p class="text-zw-mute mb-4">不存在或当前身份不可访问：<code>${id}</code></p>
      <a href="${safeBack}" class="inline-block gov-btn gov-btn-primary px-4 py-2 rounded-lg text-caption">${backText}</a>
    </div>`;
  return shell(activeKey, main);
}

window.renderAccessDeniedShell = function (pageKey) {
  const sk = window.ZW_PAGE_SHELL[pageKey] || 'p1';
  const main = `
    <div class="bg-white rounded-2xl p-10 text-center border-default shadow-soft">
      <div class="text-display mb-3">当前身份无权访问此页面</div>
      <p class="text-zw-mute mb-4">请通过业务导航进入你有权限办理的场景，或联系管理员调整岗位授权。</p>
      <a href="#/p1-workbench" class="inline-block gov-btn gov-btn-primary px-4 py-2 rounded-lg text-caption">回到首页工作台</a>
    </div>`;
  return shell(sk, main);
};

function resourceById(id) {
  return window.RUNTIME_DISCOVERY.resources.find(item => item.id === id);
}
function requestById(id) {
  return window.RUNTIME_REQUESTS.find(item => item.id === id);
}
function approvalById(id) {
  return window.RUNTIME_APPROVALS.find(item => item.id === id);
}
function deliveryById(id) {
  return window.RUNTIME_DELIVERY_TASKS.find(item => item.id === id);
}
function disputeById(id) {
  return window.RUNTIME_DISPUTES.find(item => item.id === id);
}
function zoneById(id) {
  return window.RUNTIME_ZONES.find(item => item.id === id);
}
function packageById(id) {
  return window.RUNTIME_CAPABILITY_PACKAGES.find(item => item.id === id);
}

PAGES.workbench = function () {
  const current = window.RUNTIME_WORKBENCH[window.STATE.role] || window.RUNTIME_WORKBENCH.r1;
  const metrics = window.RUNTIME_DASHBOARD.burdenMetrics || [];
  const requests = window.RUNTIME_REQUESTS || [];
  const deliveryTasks = window.RUNTIME_DELIVERY_TASKS || [];
  const primaryRequest = activeRequest();
  const primaryDelivery = activeDelivery();
  const main = `
    <div class="page-hero workbench-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">首页工作台</div>
          <div class="page-hero-title">${current.greeting}</div>
          <div class="page-hero-subtitle">${current.subtitle}</div>
        </div>
        <div class="page-meta">当前身份 · ${roleLabel(window.STATE.role)}</div>
      </div>
      ${renderWorkbenchDrillStrip(current.todos)}
    </div>

    ${statCards([
      { label: '目录资源', value: window.RUNTIME_DISCOVERY.resources.length, note: '围绕涉企基础对象与专题资源', href: '#/p2-discovery' },
      { label: '共享申请', value: requests.length, note: primaryRequest ? requestStatusLabel(primaryRequest, window.STATE.role) : '暂无申请', href: '#/p3-request-flow' },
      { label: '交付任务', value: deliveryTasks.length, note: primaryDelivery ? deliveryStatusLabel(primaryDelivery, primaryRequest) : '暂无任务', href: '#/p4-delivery-exchange' },
      { label: '治理告警', value: window.RUNTIME_ALERTS.length, note: metrics[0] ? `${metrics[0].label} ${metrics[0].value}` : '暂无异常', href: '#/p6-compliance-ops' },
    ])}

    <div class="executive-chain panel">
      <div class="panel-body">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div class="panel-title">政务数据共享主链路</div>
            <div class="panel-subtitle">从发现模板到申请审批、基层补录、审核汇总、交付回流，状态和证据在同一条链上连续呈现。</div>
          </div>
          <span class="guardrail-pill">${humanConfirmPillText(window.STATE.role)}</span>
        </div>
        <div class="chain-rail mt-5">
          <a href="#/p2-discovery"><span>1</span><strong>发现资源</strong><em>先找模板与专题包</em></a>
          <a href="#/p3-request-flow"><span>2</span><strong>申请审批</strong><em>准入判断重复要数</em></a>
          <a href="${primaryRequest ? `#/p3-request-flow/request/${primaryRequest.id}` : '#/p3-request-flow'}"><span>3</span><strong>基层补录</strong><em>只补现场差异</em></a>
          <a href="${primaryDelivery ? `#/p4-delivery-exchange/task/${primaryDelivery.id}` : '#/p4-delivery-exchange'}"><span>4</span><strong>交付回流</strong><em>形成回执与候选字段</em></a>
          <a href="#/p6-compliance-ops"><span>5</span><strong>治理审计</strong><em>减负指标与证据回放</em></a>
        </div>
      </div>
    </div>

    ${renderInlineSummary(current.aiSummary.summary, current.aiSummary.actions)}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('今日待办', '按身份展示可执行事项，直接进入当日业务办理。', infoList(current.todos))}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('智能助手建议', '按证据给出待办排序和处置草稿，关键动作仍由经办人确认。', `
          <div class="text-body leading-7 text-zw-ink">${current.aiSummary.summary}</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">${current.aiSummary.basis.map(item => `• ${item}`).join('<br/>')}</div>
        `)}
        ${panel('常用入口', '从今天要办的事进入。', `
          <div class="customer-entry-grid">
            <a href="#/p2-discovery">我要找可复用数据</a>
            <a href="#/p3-request-flow">我要看申请进度</a>
            <a href="#/p7-zones-pack">我要进入专题包</a>
            ${renderDashboardShortcutLink()}
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p1', main);
};

PAGES.discovery = function () {
  const query = escapeHtml(window.STATE.discoveryQuery || '');
  const ai = window.RUNTIME_DISCOVERY.aiCopilot;
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '数据资源发现' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">数据资源发现</div>
          <div class="page-hero-title">从业务问题出发，优先找到可复用的数据资源。</div>
          <div class="page-hero-subtitle">先查看已沉淀的模板、目录资源和专题包，再带入共享申请。</div>
        </div>
        <div class="page-meta">发现与复用判断</div>
      </div>
    </div>

    <div class="panel" data-ai-surface="search-context">
      <div class="panel-body">
        <div class="panel-title">搜索工作台</div>
        <div class="panel-subtitle">输入业务目标后，系统会重排可复用资源。</div>
        <form onsubmit="window.ACTIONS.setDiscoveryQuery(event)" class="flex gap-3 mt-4">
          <input id="discovery-q" type="text" value="${query}" class="flex-1 px-4 py-3 rounded-lg border-default text-body bg-white field-input" placeholder="例如：停车场信息" />
          <button class="gov-btn gov-btn-primary">重新解析</button>
        </form>
        <div class="mt-4 flex flex-wrap gap-2">
          <span class="chip chip-ok">已识别：涉企专题</span>
          <span class="chip chip-ok">已识别：先复用模板</span>
          <span class="chip chip-ok">已识别：差异补录</span>
          ${ai.missingQuestions.map(item => `<span class="chip chip-ask">${item}</span>`).join('')}
        </div>
        <div class="mt-4 text-body leading-7 text-zw-ink">${ai.summary}</div>
      </div>
    </div>

    <div class="grid grid-cols-12 gap-5">
      <aside class="col-span-3 space-y-5">
        ${panel('目录树', '按对象和主题找，不按后台系统找', `
          <div class="space-y-2 text-body">
            ${window.RUNTIME_DISCOVERY.catalogTree.map(item => {
              const isCatalogEntries = (item.name || '').includes('共享目录条目');
              const inner = `<span>${item.name}</span><span class="text-zw-mute">${item.count}</span>`;
              return isCatalogEntries
                ? `<a href="#/p2-discovery/catalog-browse" class="flex justify-between py-2 border-b border-b-muted hover:bg-zw-tint">${inner}</a>`
                : `<div class="flex justify-between py-2 border-b border-b-muted">${inner}</div>`;
            }).join('')}
          </div>
        `)}
        ${panel('当前缺口', '补齐这些问题后，可直接带入申请材料。', `
          <div class="space-y-2 text-body leading-7 text-zw-mute">
            ${ai.missingQuestions.map(item => `<div>• ${item}</div>`).join('')}
          </div>
        `)}
      </aside>
      <section class="col-span-9 space-y-4">
        ${panel('推荐结果', '把“为什么先用它”说清楚，让新增采集变成例外', `
          <div class="space-y-4">
            ${window.RUNTIME_DISCOVERY.resources.map(item => `
              <a href="#/p2-discovery/resource/${item.id}" class="panel card-hover block">
                <div class="panel-body">
                  <div class="grid grid-cols-12 gap-4 items-start">
                    <div class="col-span-8">
                      <div class="flex items-center gap-2"><div class="panel-title">${item.name}</div>${statusPill(item.status)}</div>
                      <div class="row-meta mt-2">${item.provider} · ${item.zone} · 更新于 ${item.updatedAt} · 覆盖 ${item.coverage}</div>
                      <p class="text-body mt-3 leading-7">${item.desc}</p>
                      <div class="mt-4 text-body-sm text-zw-mute leading-7" data-ai-surface="resource-reason">推荐理由：${item.explain.join('；')}</div>
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-body-sm text-zw-mute">相关度</div>
                      <div class="text-display text-zw-primary mt-1">${item.score}</div>
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-body-sm text-zw-mute">下一步</div>
                      <div class="text-body text-zw-ink leading-7 mt-1">${item.nextHints[0] || '查看详情'}</div>
                    </div>
                  </div>
                </div>
              </a>`).join('')}
          </div>
        `)}
      </section>
    </div>
  `;
  return shell('p2', main);
};

PAGES.catalogBrowse = function () {
  const data = window.RUNTIME_CATALOG_BROWSE || { items: [], total: 0, page: 1, limit: 20 };
  const filters = window.CATALOG_BROWSE_FILTERS || { page: 1, limit: 20, lifecycle: 'active', kind: 'real' };
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 20)));

  const lifecycleChip = (key, label) => `
    <button onclick="window.ACTIONS.setCatalogBrowseFilter('lifecycle','${key}')"
      class="chip ${filters.lifecycle === key ? 'chip-ok' : 'chip-default'}">${label}</button>`;
  const kindChip = (key, label) => `
    <button onclick="window.ACTIONS.setCatalogBrowseFilter('kind','${key}')"
      class="chip ${filters.kind === key ? 'chip-ok' : 'chip-default'}">${label}</button>`;

  const rows = (data.items || []).map(item => `
    <div class="gov-list-row">
      <div class="flex-1">
        <div class="row-title">${escapeHtml(item.title || '(未命名)')}</div>
        <div class="row-meta mt-1">${escapeHtml(item.catalog_code)} · ${escapeHtml(item.owner_org_id || '—')} · ${escapeHtml(item.lifecycle_status || '—')}</div>
      </div>
      <a href="#/p2-discovery/resource/${encodeURIComponent(item.catalog_code)}" class="row-actions">查看详情</a>
    </div>`).join('');

  const empty = data.total === 0 ? `<div class="text-body text-zw-mute py-6 text-center">当前筛选条件下无目录条目。试试切换 lifecycle 或 kind。</div>` : '';

  const main = `
    <div class="page-hero">
      <div class="page-hero-eyebrow">数据资源发现 · 目录检索</div>
      <h1 class="page-hero-title">共享目录条目浏览</h1>
      <div class="page-hero-subtitle">按生命周期与目录类型分页查看已纳入平台的目录条目，可直接跳转到资源详情。当前 ${data.total || 0} 条命中（第 ${data.page || 1} / ${totalPages} 页）。</div>
    </div>

    <div class="panel mt-4">
      <div class="panel-body">
        <div class="panel-title">筛选</div>
        <div class="panel-subtitle">默认展示已生效目录；可按生命周期筛选草稿与待发布条目；类型中的「接口分组」用于查看接口汇聚节点。</div>
        <div class="mt-3 text-body-sm text-zw-mute">生命周期</div>
        <div class="mt-2 flex flex-wrap gap-2">
          ${lifecycleChip('active', '活跃')}
          ${lifecycleChip('approved_pending_publish', '待发布')}
          ${lifecycleChip('draft', '草稿')}
          ${lifecycleChip('pending_review', '审核中')}
          ${lifecycleChip('rejected', '已驳回')}
          ${lifecycleChip('all', '全部')}
        </div>
        <div class="mt-4 text-body-sm text-zw-mute">类型</div>
        <div class="mt-2 flex flex-wrap gap-2">
          ${kindChip('real', '真业务目录')}
          ${kindChip('api-group', 'API 分组')}
          ${kindChip('all', '全部')}
        </div>
      </div>
    </div>

    <div class="panel mt-4">
      <div class="panel-body">
        <div class="panel-title">条目列表</div>
        <div class="gov-list mt-3">${rows}</div>
        ${empty}
      </div>
    </div>

    <div class="panel mt-4">
      <div class="panel-body flex items-center justify-between">
        <div class="text-body-sm text-zw-mute">第 ${data.page || 1} / ${totalPages} 页 · 共 ${data.total || 0} 项</div>
        <div class="flex gap-2">
          <button onclick="window.ACTIONS.setCatalogBrowseFilter('page', Math.max(1, ${data.page || 1} - 1))"
            class="gov-btn gov-btn-secondary" ${(data.page || 1) <= 1 ? 'disabled' : ''}>上一页</button>
          <button onclick="window.ACTIONS.setCatalogBrowseFilter('page', Math.min(${totalPages}, ${data.page || 1} + 1))"
            class="gov-btn gov-btn-secondary" ${(data.page || 1) >= totalPages ? 'disabled' : ''}>下一页</button>
        </div>
      </div>
    </div>
  `;
  return shell('p2', main);
};

PAGES.resourceDetail = function (id) {
  const item = resourceById(id);
  if (!item) return entityNotFoundShell('p2', '数据资源', id, '#/p2-discovery', '返回数据资源发现');
  const approvalRate = item.approvalRate || '—';
  const subscribers = item.subscribers ?? '—';
  const fields = item.fields || [];
  const zoneId = item.zone === '营商环境专区' ? 'business' : item.zone === '治理减负专区' ? 'governance' : 'livelihood';
  const main = `
    ${crumbs([{ label: '数据资源发现', href: '#/p2-discovery' }, { label: item.name }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${item.name}</div>
          <div class="page-hero-subtitle">${item.provider} · ${item.zone} · 更新于 ${item.updatedAt}</div>
        </div>
        ${statusPill(item.status)}
      </div>
    </div>

    ${renderInlineSummary('建议从法人模板发起复用申请，基层只补经营状态、走访时间和现场备注。', item.nextHints)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('核心字段与覆盖', '查看可直接复用的字段、来源和覆盖情况', `<div class="gov-list">${fields.length ? fields.map(field => `<div class="gov-list-row"><div class="row-title">${field}</div><div class="row-meta">标准字段 / 可预填</div></div>`).join('') : '<div class="text-body text-zw-mute py-4">该真目录暂未抽取字段清单，可先查看目录元数据与来源。</div>'}</div>`)}
      ${panel('信任信息与动作', '把来源、覆盖和下一步说清楚，降低“我还要不要重新要数”的判断成本', `
        <div class="space-y-3 text-body">
          <div>覆盖情况：<strong>${item.coverage}</strong></div>
          <div>历史审批通过率：<strong>${approvalRate}</strong></div>
          <div>订阅 / 使用部门：<strong>${subscribers}</strong></div>
          <div class="text-zw-mute">推荐动作：先查看差异字段，再发起标准复用申请。</div>
        </div>
        <div class="mt-5 flex gap-3">
          <button onclick="window.ACTIONS.createRequest('${item.id}')" class="gov-btn gov-btn-primary">发起标准复用申请</button>
          <a href="#/p7-zones-pack/zone/${zoneId}" class="gov-btn gov-btn-secondary">查看所属专题包</a>
        </div>
      `)}
    </div>
  `;
  return shell('p2', main);
};

PAGES.requestFlow = function () {
  const request = activeRequest();
  const draft = request.aiDraft;
  const role = window.STATE.role;
  const isGrassroots = role === 'r3' || role === 'r4';
  const isReviewer = role === 'r2' || role === 'r5';
  const statusLabel = requestStatusLabel(request, role);
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '共享申请与审批' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">共享申请与审批</div>
          <div class="page-hero-title">共享申请、准入审批、基层补录在一条链上办理。</div>
          <div class="page-hero-subtitle">发起人、审批承接、镇街社区和汇总人员看到同一份状态，只在自己负责的环节执行人工确认。</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
      <div class="mt-4">${stepBar(['发现模板', '复用判断', '受控准入', '预填补录', '审核汇总', '回流共享'], requestStepIndex(request, role))}</div>
    </div>

    ${renderInlineSummary(draft.summary, ['查看已预填字段', '查看差异补录', '查看自动汇总预估'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('标准复用申请', '按模板覆盖率、差异字段和责任说明生成申请材料', `
          <div class="grid grid-cols-2 gap-4 text-body" data-ai-surface="request-inline-ai">
            ${renderFieldState('复用模板', request.resourceName, '已识别', '作为涉企默认基础对象')}
            ${renderFieldState('模板覆盖率', request.templateCoverage, '已识别', '多数基础字段可自动带出')}
            <div class="col-span-2">${renderFieldState('业务目标', request.purpose, '已识别', '先复用模板，再补现场差异')}</div>
            <div class="col-span-2">${renderFieldState('差异字段责任说明', '经营状态 / 走访时间 / 现场备注', request.status === 'need-fix' ? '待补正' : '待确认', '需明确由镇街 / 社区补录，审核汇总人员只处理异常项')}</div>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-4">
            ${panel('已预填字段', '这些字段已由共享资源自动带出', `<div class="text-body leading-7 text-zw-mute">${request.prefilledFields.map(item => `• ${item.label}：${item.value}（${item.source}）`).join('<br/>')}</div>`)}
            ${panel('差异补录字段', '现场变化字段进入基层补录', `<div class="text-body leading-7 text-zw-mute">${request.diffFields.map(item => `• ${item.label}：${item.reason}（${item.owner}）`).join('<br/>')}</div>`)}
          </div>
          <div class="mt-4 text-body leading-7 text-zw-ink" data-ai-surface="request-summary-inline">可审摘要：${draft.summary}</div>
          <div class="mt-5 flex gap-3 flex-wrap">
            ${requestActionBar(request, role)}
          </div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel(isGrassroots ? '基层补录提示' : '准入 / 汇总侧栏', isGrassroots ? '镇街 / 社区核对已带出字段并补齐待补项。' : '审批承接人员处理准入，审核汇总人员处理异常项与汇总结果。', `
          <div class="text-body leading-7 text-zw-ink">${isGrassroots ? '本任务已自动带出企业基础字段，你只需核对经营状态、最近走访时间和现场备注。' : isReviewer ? '当前重点是确认差异字段、异常项和自动汇总结果。' : draft.risk}</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">${isReviewer ? request.summaryResult.note : '建议优先复用模板，并确认差异字段和回流要求。'}</div>
        `)}
        ${panel('当前链路队列', '查看各申请当前进度和可处理入口', `
          <div class="gov-list text-body">
            ${window.RUNTIME_REQUESTS.map(item => `
              <a href="${summaryRouteForRole(window.STATE.role, item.id)}" class="gov-list-row card-hover">
                <div><div class="row-title">${item.id}</div><div class="row-meta mt-2">${item.resourceName}</div></div>
                ${statusPill(requestStatusLabel(item, role))}
              </a>`).join('')}
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p3', main);
};

PAGES.requestDetail = function (id) {
  const item = requestById(id);
  if (!item) return entityNotFoundShell('p3', '共享申请', id, '#/p3-request-flow', '返回共享申请与审批');
  const role = window.STATE.role;
  const isGrassroots = role === 'r3' || role === 'r4';
  const diffState = item.status === 'supplementing' ? '待补录' : item.status === 'summary-pending' || item.status === 'completed' ? '已补录' : item.status === 'need-fix' ? '待补正' : '待确认';
  const diffNote = field => item.status === 'summary-pending' || item.status === 'completed'
    ? `${field.reason} · ${field.owner} · ${field.state || '已补录'}`
    : `${field.reason} · ${field.owner}`;
  const main = `
    ${crumbs([{ label: '共享申请与审批', href: '#/p3-request-flow' }, { label: item.id }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${item.id}</div>
          <div class="page-hero-subtitle">${item.resourceName} · ${item.applicantDept}</div>
        </div>
        ${statusPill(requestStatusLabel(item, role))}
      </div>
    </div>

    ${renderInlineSummary(item.aiStatus.summary, [item.aiStatus.nextAction])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('状态时间线', '把“发现 → 申请 → 审批 → 补录 → 汇总 → 回流”作为同一条业务链展示', `
          <div class="timeline">
            ${item.timeline.map(step => `
              <div class="timeline-item">
                <div class="timeline-time">${step.time}</div>
                <div class="timeline-body">
                  <div class="timeline-title">${step.label}</div>
                  <div class="timeline-note">${step.note}</div>
                </div>
              </div>`).join('')}
          </div>
        `)}
        ${panel('已预填字段', '来源透明，帮助基层与审核岗理解哪些值来自共享池、哪些来自模板版本', `
          <div class="grid grid-cols-2 gap-3">${item.prefilledFields.map(field => renderFieldState(field.label, field.value, field.state, field.source)).join('')}</div>
        `)}
        ${panel('待补录 / 差异字段', '只补真正缺失、动态、现场性强的字段', `
          <div class="grid grid-cols-1 gap-3">${item.diffFields.map(field => renderFieldState(field.label, field.value, diffState, diffNote(field))).join('')}</div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel('回执与审计', '查看本次办理的审计编号、可信存证和依据', `
          <div class="space-y-3 text-body">
            <div><span class="audit-chip">审计编号</span> <strong>${item.auditId}</strong></div>
            <div><span class="audit-chip">可信存证</span> <strong>${item.chainAnchor}</strong></div>
            <div class="text-zw-mute">依据：${item.aiStatus.evidence.join('；')}</div>
          </div>
        `)}
        ${panel('回流说明', '查看补录结果如何进入后续复用', `
          <div class="text-body leading-7 text-zw-ink">${item.returnFlow.map(line => `• ${line}`).join('<br/>')}</div>
        `)}
        ${panel(isGrassroots ? '当前补录动作' : '当前链路动作', isGrassroots ? '基层当前处理补录，其他阶段查看进度。' : '申请方当前查看状态、证据和可处理动作。', `
          <div class="flex gap-3 flex-wrap">
            ${requestActionBar(item, role)}
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p3', main);
};

PAGES.reviewDetail = function (id) {
  const request = requestById(id);
  const approval = approvalById(id);
  if (!request || !approval) return entityNotFoundShell('p3', '申请或审批记录', id, '#/p3-request-flow', '返回共享申请与审批');
  const isSummaryStage = request.status === 'summary-pending' || request.status === 'completed';
  const statusLabel = requestStatusLabel(request, window.STATE.role);
  const actionTitle = isSummaryStage ? '汇总确认动作' : '准入判定动作';
  const actionSubtitle = isSummaryStage
    ? '自动汇总确认、退回补正、明确驳回都必须由审核汇总人员显式点击。'
    : '审批承接人员确认后，下发基层补录任务。';
  const primaryAction = request.status === 'pending'
    ? `<button onclick="window.ACTIONS.approveRequest('${request.id}')" class="gov-btn gov-btn-primary">通过并下发补录</button>`
    : request.status === 'summary-pending'
      ? `<button onclick="window.ACTIONS.confirmSummary('${request.id}')" class="gov-btn gov-btn-primary">确认自动汇总</button>`
      : `${actionNotice('当前阶段没有新的主状态写动作')}`;
  const secondaryAction = ['pending', 'summary-pending'].includes(request.status)
    ? `<button onclick="window.ACTIONS.returnForFix('${request.id}')" class="gov-btn gov-btn-warn">退回补正</button>`
    : '';
  const rejectAction = ['pending', 'summary-pending'].includes(request.status)
    ? `<button onclick="window.ACTIONS.rejectRequest('${request.id}')" class="gov-btn gov-btn-danger">驳回</button>`
    : '';
  const main = `
    ${crumbs([{ label: '共享申请与审批', href: '#/p3-request-flow' }, { label: '审核 / 汇总详情' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">审核 / 汇总详情 · ${request.id}</div>
          <div class="page-hero-subtitle">审批承接人员处理准入，审核汇总人员处理异常项与自动汇总。</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(`${approval.suggestion}。${approval.autoSummary}`, ['查看异常项', '查看自动汇总结果', '查看回流要求'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('申请与模板信息', '审批人核对模板覆盖、差异字段和申请目标', `
          <table class="gov-table">
            <tbody>
              <tr><td>复用对象</td><td>${request.resourceName}</td></tr>
              <tr><td>模板覆盖率</td><td>${request.templateCoverage}</td></tr>
              <tr><td>差异字段</td><td>${request.diffFields.map(item => item.label).join(' / ')}</td></tr>
              <tr><td>申请目标</td><td>${request.purpose}</td></tr>
            </tbody>
          </table>
        `)}
        ${panel(isSummaryStage ? '自动汇总结果与异常项' : '准入判断与差异字段', isSummaryStage ? '审核汇总人员确认异常项和自动汇总结果。' : '审批承接人员确认是否下发基层补录。', `
          <div data-ai-surface="review-summary" class="space-y-4 text-body leading-7">
            <div><strong>${isSummaryStage ? '自动汇总结果' : '准入判断'}</strong><div class="mt-2 text-zw-mute">${request.summaryResult.note}</div></div>
            <div><strong>异常项</strong><div class="mt-2 text-zw-mute">${approval.exceptionItems.map(item => `• ${item}`).join('<br/>')}</div></div>
            <div><strong>回流候选</strong><div class="mt-2 text-zw-mute">${request.returnFlow.map(item => `• ${item}`).join('<br/>')}</div></div>
          </div>
        `)}
        ${renderDraftCard('AI 建议的审批 / 汇总意见草稿', [approval.draftNote], '草稿只帮助你更快进入结构化决策，不会替你写入最终结果。')}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('依据与风险', '动作前先看建议依据、风险和影响预估', `
          <div data-ai-surface="approval-inline-ai" class="space-y-4 text-body leading-7">
            <div><strong>建议依据</strong><div class="mt-2 text-zw-mute">${approval.reason.map(item => `• ${item}`).join('<br/>')}</div></div>
            <div><strong>风险提示</strong><div class="mt-2 text-zw-mute">${approval.risk.map(item => `• ${item}`).join('<br/>')}</div></div>
            <div><strong>影响预估</strong><div class="mt-2 text-zw-mute">${approval.impact}</div></div>
            <div><strong>反事实提示</strong><div class="mt-2 text-zw-mute">${approval.counterfactual}</div></div>
            <div><span class="confidence-chip">置信度 ${Math.round(approval.confidence * 100)}%</span></div>
          </div>
        `)}
      </aside>
    </div>
    ${panel(actionTitle, actionSubtitle, `
      <div class="flex gap-3 flex-wrap">
        ${primaryAction}
        ${secondaryAction}
        ${rejectAction}
      </div>
    `)}
  `;
  return shell('p3', main);
};

PAGES.deliveryExchange = function () {
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '交付交换与回流' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">交付交换与回流</div>
          <div class="page-hero-title">看交付是否完成，也看结果如何沉淀为下次默认复用。</div>
          <div class="page-hero-subtitle">补录、自动汇总、交付回执和模板回流在同一条任务线上跟踪。</div>
        </div>
        <div class="page-meta">补录、汇总、回流治理</div>
      </div>
    </div>

    ${panel('任务队列', '任务状态同时表达：是正常预填闭环、准入拦截，还是审计熔断保护', `
      <div data-ai-surface="delivery-queue" class="space-y-4">
        ${window.RUNTIME_DELIVERY_TASKS.map(task => {
          const request = requestById(task.requestId);
          const requestReady = request && request.status === 'completed';
          const backflowKey = backflowStatusKey(task.backflow.status);
          const backflowReady = requestReady && backflowKey !== 'confirmed';
          const statusLabel = deliveryStatusLabel(task, request);
          const actionHint = task.status === 'supplementing'
            ? '当前等待基层完成差异补录。'
            : task.status === 'reconciling' && backflowReady
              ? '汇总已完成，当前等待供给侧确认是否纳入模板。'
              : backflowKey === 'confirmed'
                ? '回流已确认，模板与专题入口应已同步。'
                : task.status === 'warning'
                  ? '当前链路被退回、驳回或存在异常，需要先处理阻断。'
                  : '当前任务处于可追踪状态。';
          return `
          <a href="#/p4-delivery-exchange/task/${task.id}" class="panel card-hover block">
            <div class="panel-body">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="flex items-center gap-2"><div class="panel-title">${task.name}</div>${statusPill(statusLabel)}</div>
                  <div class="row-meta mt-2">${task.id} · ${task.channel} · ${task.owner}</div>
                  <p class="text-body mt-3 leading-7">${task.note}</p>
                  <div class="mt-2 text-body-sm text-zw-mute leading-7">回流状态：${task.backflow.status} · ${actionHint}</div>
                  <div class="mt-4 text-body-sm text-zw-mute leading-7" data-ai-surface="delivery-inline-ai">当前判断：${task.aiSummary.summary}</div>
                </div>
                <div class="text-right text-caption text-zw-mute">最近更新<br/><strong class="text-zw-ink">${task.updatedAt}</strong></div>
              </div>
            </div>
          </a>`;
        }).join('')}
      </div>
    `)}
  `;
  return shell('p4', main);
};

PAGES.deliveryTaskDetail = function (id) {
  const task = deliveryById(id);
  if (!task) return entityNotFoundShell('p4', '交付任务', id, '#/p4-delivery-exchange', '返回交付交换与回流');
  const request = requestById(task.requestId);
  if (!request) return entityNotFoundShell('p4', '关联共享申请', task.requestId, '#/p4-delivery-exchange', '返回交付交换与回流');
  const ai = task.aiSummary;
  const statusLabel = deliveryStatusLabel(task, request);
  const backflowKey = backflowStatusKey(task.backflow.status);
  const canConfirmBackflow = request && request.status === 'completed' && task.receiptStatus === 'reconciled' && backflowKey !== 'confirmed';
  const main = `
    ${crumbs([{ label: '交付交换与回流', href: '#/p4-delivery-exchange' }, { label: task.id }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${task.name}</div>
          <div class="page-hero-subtitle">${task.channel} · ${task.owner} · 关联申请 ${task.requestId}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(ai.summary, [ai.nextAction])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('任务时间线', '查看任务关键状态和责任记录', `
          <div class="timeline">
            ${task.history.map(item => `
              <div class="timeline-item">
                <div class="timeline-time">${item.time}</div>
                <div class="timeline-body">
                  <div class="timeline-title">${item.state}</div>
                  <div class="timeline-note">${item.detail}</div>
                </div>
              </div>`).join('')}
          </div>
        `)}
        ${panel('回流共享说明', '查看本次补录沉淀出的回流候选', `
          <div class="grid grid-cols-2 gap-4 text-body leading-7">
            <div><strong>回流候选对象</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateObject}</div></div>
            <div><strong>回流状态</strong><div class="mt-2 text-zw-mute">${task.backflow.status}</div></div>
            <div class="col-span-2"><strong>候选字段</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateFields.length ? task.backflow.candidateFields.join(' / ') : '—'}</div></div>
            <div class="col-span-2 text-zw-mute">${task.backflow.note}</div>
          </div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel('当前处置建议', '查看处置建议、原因和影响', `
          <div data-ai-surface="delivery-detail-inline" class="text-body leading-7 text-zw-ink">${ai.nextAction}</div>
          <div class="mt-4 text-body-sm text-zw-mute">原因：${ai.cause}</div>
          <div class="mt-2 text-body-sm text-zw-mute">影响：${ai.impact}</div>
        `)}
        ${panel('当前链路动作', '只有在自动汇总已被确认后，台账管理员 / 目录管理员才能显式确认回流生效。', `
          <div class="space-y-3 text-body-sm text-zw-mute leading-7">
            <div>申请状态：${requestStatusLabel(request, window.STATE.role)}</div>
            <div>回流候选：${task.backflow.status}</div>
            <div>回执状态：${task.receiptStatus || '待对账'}</div>
          </div>
          <div class="mt-5 flex gap-3 flex-wrap">
            ${task.receiptStatus === 'reconciled'
              ? `${actionNotice('当前交付回执已完成对账')}`
              : `<button onclick="window.ACTIONS.reconcileDeliveryReceipt('${task.id}')" class="gov-btn gov-btn-secondary">对账交付回执</button>`}
            ${task.status === 'failed'
              ? `<button onclick="window.ACTIONS.triggerDeliveryRecovery('${task.id}')" class="gov-btn gov-btn-secondary">触发恢复</button>`
              : ''}
            ${canConfirmBackflow
              ? `<button onclick="window.ACTIONS.confirmBackflow('${task.id}')" class="gov-btn gov-btn-primary">确认回流共享</button>`
              : backflowKey === 'confirmed'
                ? `${actionNotice('回流确认已生效')}`
                : `${actionNotice('当前还未满足回流确认条件：需先完成汇总确认和交付回执对账，且不能重复确认已生效回流')}`}
            <a href="#/p5-provider" class="gov-btn gov-btn-secondary">查看模板治理</a>
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p4', main);
};


PAGES.provider = function () {
  const ai = window.RUNTIME_PROVIDER.aiGovernance;
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '数据供给管理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">数据供给管理</div>
          <div class="page-hero-title">维护可复用的目录、模板和预填服务。</div>
          <div class="page-hero-subtitle">台账管理员和目录管理员处理发布、修正、暂停和回流候选。</div>
        </div>
        <div class="page-meta">模板治理与发布</div>
      </div>
    </div>

    ${statCards(window.RUNTIME_PROVIDER.overview)}

    <div class="grid grid-cols-3 gap-5">
      ${panel('目录治理', '处理目录发布与说明修正', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.catalogs.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.owner} · ${item.issue}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}<button onclick="window.ACTIONS.manageCatalogEntry('${item.id}', '${item.status === '已发布' ? 'revise' : 'publish'}')" class="gov-btn gov-btn-secondary">${item.status === '已发布' ? '修正文案' : '发布'}</button></div></div>`).join('')}</div>
      `)}
      ${panel('资源 / 模板治理', '处理资源发布、暂停共享和模板更新', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.resources.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.type} · 更新于 ${item.updatedAt}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}<button onclick="window.ACTIONS.manageResourceAsset('${item.id}', '${item.status === '可共享' ? 'suspend' : 'publish'}')" class="gov-btn gov-btn-secondary">${item.status === '可共享' ? '暂停共享' : '发布共享'}</button></div></div>`).join('')}</div>
      `)}
      ${panel('服务治理', '查看预填、回流服务的在线状态和调用压力', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.services.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">实时调用 ${item.qps} 次 / 分钟 · ${item.note}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}${item.status === '在线' ? `<button onclick="window.ACTIONS.suspendProviderService('${item.id}')" class="gov-btn gov-btn-secondary">暂停</button>` : `<button onclick="window.ACTIONS.publishProviderService('${item.id}')" class="gov-btn gov-btn-secondary">发布</button>`}</div></div>`).join('')}</div>
      `)}
    </div>

    ${panel('治理重点', '按影响面排序今日治理重点', `
      <div data-ai-surface="provider-governance" class="text-body leading-7 text-zw-ink">${ai.summary}</div>
      <div class="mt-4 text-body-sm text-zw-mute leading-7">${ai.priorities.map(item => `• ${item}`).join('<br/>')}</div>
    `)}
  `;
  return shell('p5', main);
};

PAGES.complianceOps = function () {
  const metrics = window.RUNTIME_DASHBOARD.burdenMetrics;
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '合规运营与减负' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">合规运营与减负</div>
          <div class="page-hero-title">盯住重复要数、绕行采集和基层负担反弹。</div>
          <div class="page-hero-subtitle">合规治理关注减负结果、争议证据、审计回放和模板升级线索。</div>
        </div>
        <div class="page-meta">减负治理与证据</div>
      </div>
    </div>

    ${panel('减负指标', '先看减负结果，再钻取证据和工单链路', `
      <div class="grid grid-cols-4 gap-4">
        ${metrics.map(item => `<a href="#/p6-compliance-ops" class="gov-stat-card gov-stat-link"><div class="gov-stat-label">${item.label}</div><div class="gov-stat-value">${item.value}</div><div class="mt-2 text-caption text-zw-mute">${item.trend}</div><div class="mt-3 text-caption font-bold text-zw-link">查看证据</div></a>`).join('')}
      </div>
    `)}

    ${renderInlineSummary(window.RUNTIME_AUDIT_AI.summary, ['查看重复要数争议', '查看差异补录热区', '查看审计回放'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-4 space-y-5">
        ${panel('争议与绕行', '先看哪些行为会增加基层负担，再进入证据核查', `
          <div class="space-y-3 text-body">
            ${window.RUNTIME_DISPUTES.map(item => `<a href="#/p6-compliance-ops/dispute/${item.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between"><div class="panel-title text-body">${item.title}</div>${statusPill(item.status)}</div><div class="row-meta mt-2">${item.id} · ${item.owner}</div><div class="mt-3 text-body-sm text-zw-mute leading-7" data-ai-surface="dispute-inline-ai">初步判断：${item.aiSummary}</div></div></a>`).join('')}
          </div>
        `)}
        ${panel('告警 → 工单 → 知识建议', '每个告警都关联工单、责任人和处置建议', `
          <div class="space-y-3 text-body">
            ${window.RUNTIME_ALERTS.map(alert => {
              const ticket = window.RUNTIME_TICKETS.find(item => item.id === alert.linkedTicket);
              const kb = window.RUNTIME_KNOWLEDGE_ARTICLES.find(item => item.id === alert.knowledge);
              return `<div class="panel"><div class="panel-body"><div class="flex items-center justify-between"><div class="panel-title text-body">${alert.title}</div>${statusPill('处理中')}</div><div class="row-meta mt-2">责任人：${alert.owner}</div><div class="mt-3 leading-7">${alert.summary}</div><div class="mt-3 text-body-sm text-zw-mute">工单：${ticket ? ticket.title : '—'}</div><div class="mt-1 text-body-sm text-zw-mute">知识建议：${kb ? kb.title : '—'}</div><div class="mt-3 text-body-sm text-zw-mute leading-7" data-ai-surface="alert-inline-ai">研判：${alert.aiAdvice}</div></div></div>`;
            }).join('')}
          </div>
        `)}
      </section>
      <section class="col-span-8 space-y-5">
        ${panel('审计回放', '按时间回放原始证据和处理结果', `
          <table class="gov-table">
            <thead><tr><th>时间</th><th>事件</th><th>目标</th><th>主体</th><th>结果</th></tr></thead>
            <tbody>
              ${window.RUNTIME_AUDIT_EVENTS.map(item => `<tr><td>${item.time}</td><td>${item.type}</td><td>${item.target}</td><td>${item.actor}</td><td>${statusPill(item.result)}</td></tr>`).join('')}
            </tbody>
          </table>
        `)}
        ${panel('当前治理判断', '结合证据判断是否需要制度或模板调整', `
          <div data-ai-surface="compliance-inline-ai" class="text-body leading-7 text-zw-ink">${window.RUNTIME_AUDIT_AI.summary}</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">${window.RUNTIME_AUDIT_AI.evidence.map(item => `• ${item}`).join('<br/>')}</div>
        `)}
      </section>
    </div>
  `;
  return shell('p6', main);
};

PAGES.disputeDetail = function (id) {
  const item = disputeById(id);
  if (!item) return entityNotFoundShell('p6', '争议事项', id, '#/p6-compliance-ops', '返回合规运营与减负');
  const main = `
    ${crumbs([{ label: '合规运营与减负', href: '#/p6-compliance-ops' }, { label: item.id }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${item.title}</div>
          <div class="page-hero-subtitle">处理人：${item.owner}</div>
        </div>
        ${statusPill(item.status)}
      </div>
    </div>

    <div class="panel" data-ai-surface="dispute-inline-summary">
      <div class="panel-body py-4">
        <div class="text-body leading-7 text-zw-ink">${item.aiSummary}</div>
      </div>
    </div>

    ${panel('争议处理时间线', '查看争议来源、处理进展和下一步动作', `
      <div class="timeline">
        ${item.timeline.map(step => `
          <div class="timeline-item">
            <div class="timeline-time">${step.time}</div>
            <div class="timeline-body">
              <div class="timeline-title">${step.label}</div>
              <div class="timeline-note">${step.note}</div>
            </div>
          </div>`).join('')}
      </div>
      <div class="mt-5 flex gap-3 flex-wrap">
        <button onclick="window.ACTIONS.progressDispute('${item.id}')" class="gov-btn gov-btn-primary">推进调查</button>
        <button onclick="window.ACTIONS.escalateDispute('${item.id}')" class="gov-btn gov-btn-secondary">升级治理</button>
      </div>
    `)}
    ${item.evidenceReplay ? panel('原始证据与关联链路', '回放原始证据、审计事件、工单和知识建议。', `
      <div class="grid grid-cols-2 gap-4 text-body">
        <div class="panel"><div class="panel-body"><div class="panel-title text-body">证据时间线</div><div class="timeline mt-4">
          ${(item.evidenceReplay.evidenceChain || []).map(step => `<div class="timeline-item"><div class="timeline-time">${step.time}</div><div class="timeline-body"><div class="timeline-title">${step.label}</div><div class="timeline-note">${step.detail}</div></div></div>`).join('') || '<div class="text-zw-mute">暂无原始证据</div>'}
        </div></div></div>
        <div class="panel"><div class="panel-body"><div class="panel-title text-body">关联审计事件</div><div class="mt-4 space-y-3">
          ${(item.evidenceReplay.auditEvents || []).map(evt => `<div><div class="flex items-center gap-2 flex-wrap"><span class="audit-chip">${evt.result}</span><span>${evt.time} · ${evt.type}</span></div><div class="mt-1 text-body-sm text-zw-mute leading-7">${evt.actor} → ${evt.target}</div></div>`).join('') || '<div class="text-zw-mute">暂无审计事件</div>'}
        </div></div></div>
      </div>
      <div class="grid grid-cols-2 gap-4 text-body mt-4">
        <div class="panel"><div class="panel-body"><div class="panel-title text-body">处置工单</div><div class="mt-3 space-y-3">
          ${(item.evidenceReplay.tickets || []).map(ticket => `<div><div class="flex items-center justify-between gap-3"><strong>${ticket.title}</strong>${statusPill(ticket.status)}</div><div class="row-meta mt-1">${ticket.id} · ${ticket.owner}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">${ticket.note}</div></div>`).join('') || '<div class="text-zw-mute">暂无处置工单</div>'}
        </div></div></div>
        <div class="panel"><div class="panel-body"><div class="panel-title text-body">知识建议</div><div class="mt-3 space-y-3">
          ${(item.evidenceReplay.knowledgeArticles || []).map(article => `<div><strong>${article.title}</strong><div class="row-meta mt-1">${article.id}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">${article.summary}</div></div>`).join('') || '<div class="text-zw-mute">暂无知识建议</div>'}
        </div></div></div>
      </div>
    `) : ''}
  `;
  return shell('p6', main);
};


PAGES.zonesPack = function () {
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '共享专区 / 专题包' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">共享专区 / 专题包</div>
          <div class="page-hero-title">进入一表通、营商环境、治理减负等高频专题。</div>
          <div class="page-hero-subtitle">选择专题后可直接查看资产、发起复用申请或订阅更新。</div>
        </div>
        <div class="page-meta">专题场景入口</div>
      </div>
    </div>

    ${panel('专题包列表', '选择今天要处理的专题场景', `
      <div class="grid grid-cols-3 gap-5">
        ${window.RUNTIME_ZONES.map(zone => `<a href="#/p7-zones-pack/zone/${zone.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-2"><div class="panel-title text-body">${zone.name}</div>${statusPill(zone.status)}</div><p class="text-body mt-3 leading-7">${zone.desc}</p><div class="mt-4 row-meta">资产 ${zone.assets.length} 项 · 订阅部门 ${zone.subscribers}</div><div class="mt-4 text-body-sm text-zw-mute leading-7">适用问题：${zone.aiGuide}</div></div></a>`).join('')}
      </div>
    `)}
  `;
  return shell('p7', main);
};

PAGES.zoneDetail = function (id) {
  const zone = zoneById(id);
  if (!zone) return entityNotFoundShell('p7', '专题包', id, '#/p7-zones-pack', '返回共享专区 / 专题包');
  const main = `
    ${crumbs([{ label: '共享专区 / 专题包', href: '#/p7-zones-pack' }, { label: zone.name }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${zone.name}</div>
          <div class="page-hero-subtitle">${zone.desc}</div>
        </div>
        ${statusPill(zone.status)}
      </div>
    </div>

    ${renderInlineSummary('专题包已汇集常用资产、复用入口、订阅信息和可信记录。', zone.nextActions)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('包含资产', '让用户一眼看到这个专题包里有什么可以直接用', `<ul class="space-y-2 text-body leading-7 list-disc pl-5">${zone.assets.map(item => `<li>${item}</li>`).join('')}</ul>`)}
      ${panel('信任信息与价值', '查看订阅、来源、更新和可信记录', `
        <ul class="space-y-2 text-body leading-7 list-disc pl-5">
          ${zone.trust.map(item => `<li>${item}</li>`).join('')}
          <li>可用动作：查看详情、发起复用申请、订阅专区更新。</li>
        </ul>
        <div class="mt-5"><button onclick="window.ACTIONS.publishZoneTopicProjection('${zone.id}')" class="gov-btn gov-btn-primary">发布正式投影</button></div>
      `)}
    </div>
  `;
  return shell('p7', main);
};

PAGES.integrationAdmin = function () {
  const packages = window.RUNTIME_CAPABILITY_PACKAGES || [];
  const pendingCount = packages.filter(item => item.status === 'pending' || item.status === 'pending-fix').length;
  const rejectedCount = packages.filter(item => item.status === 'rejected').length;
  const readOnlyCount = packages.filter(item => item.requiresHuman === false).length;
  const main = `
    ${crumbs([{ label: '首页工作台', href: '#/p1-workbench' }, { label: '平台接入管理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">平台接入管理</div>
          <div class="page-hero-title">审核外部能力的接入范围和上线条件。</div>
          <div class="page-hero-subtitle">目录管理员在这里处理待审能力、租户范围、权限策略和审计要求。</div>
        </div>
        <div class="page-meta">受控接入</div>
      </div>
    </div>

    ${statCards([
      { label: '待审核能力', value: pendingCount, note: '待补租户范围和审计级别' },
      { label: '辅助能力', value: readOnlyCount, note: '可进入待上线清单' },
      { label: '已驳回越权', value: rejectedCount, note: '已阻断越权动作' },
      { label: '人工确认', value: '强制', note: '管理员待确认' },
    ])}

    ${renderInlineSummary('当前优先处理法人基础信息查询能力：待补齐租户可见范围后再进入上线审核。', ['查看待审能力包', '查看暴露范围', '查看退回草案'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7">
        ${panel('能力包注册队列', '处理待上线、待补正和已驳回的外部能力', `
          <div class="space-y-3 text-body">
            ${packages.map(item => `<a href="#/p8-integration-admin/package/${item.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-3"><div class="panel-title text-body">${formatPackageName(item.slug)}</div>${statusPill(packageStatusLabel(item))}</div><div class="row-meta mt-2">${item.source}</div><div class="mt-3">${item.desc}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">审核状态：${packageStatusLabel(item)} · 暴露面 ${formatExposure(item.exposure)}</div><div class="mt-3 text-body-sm text-zw-mute leading-7" data-ai-surface="package-inline-ai">系统审核意见：${item.aiReview.summary}</div></div></a>`).join('')}
          </div>
        `)}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('身份与权限治理', '查看 IAF 绑定、投影、租户策略、导入问题和裁决证据', `
          <div class="text-body leading-7 text-zw-ink">从统一能力契约读取治理总览，直接查看身份、授权与策略证据。</div>
          <a href="#/p8-integration-admin/iam-governance" class="gov-btn gov-btn-secondary mt-4 inline-block">打开治理总览</a>
        `)}
        ${panel('上线核对项', '上线前核对来源、范围、权限和回退方案', `
          <ul class="space-y-2 text-body leading-7 list-disc pl-5">
            <li>能力名称 / 版本 / 来源</li>
            <li>租户范围 / 权限策略 / 审计级别</li>
            <li>是否需要人工确认</li>
            <li>兼容范围 / 对外暴露范围</li>
            <li>影响说明 / 回退目标</li>
          </ul>
        `)}
        ${panel('审核提示', '先确认它能帮助经办人提效，再确认不会越权办理。', `
          <div data-ai-surface="integration-inline-ai" class="text-body leading-7 text-zw-ink">可上线能力应帮助草拟、解释、汇总、推荐或适配；涉及提交、审批、回执对账、版本登记、租户策略生效的能力需要退回或驳回。</div>
        `)}
      </aside>
    </div>
  `;
  return shell('p8', main);
};

PAGES.iamGovernance = function () {
  const data = window.RUNTIME_IAM_GOVERNANCE || { summary: {}, actors: [], roles: [], orgs: [], tenant_policies: [], import_issues: [], audit_events: [], policy_probe: null };
  const summary = data.summary || {};
  const actors = data.actors || [];
  const policies = data.tenant_policies || [];
  const issues = data.import_issues || [];
  const audit = data.audit_events || [];
  const probe = data.policy_probe;
  const main = `
    ${crumbs([{ label: '平台接入管理', href: '#/p8-integration-admin' }, { label: '身份与权限治理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">IAF IAM 治理</div>
          <div class="page-hero-title">查看本地投影、租户策略与裁决证据。</div>
          <div class="page-hero-subtitle">这里只读展示 zw-brain 授权事实，不复刻旧 BSP 菜单、按钮或权限树。</div>
        </div>
        <div class="page-meta">${escapeHtml(data.tenant_id || 'sd-default')}</div>
      </div>
    </div>

    ${statCards([
      { label: '用户投影', value: summary.actor_count || 0, note: `绑定状态 ${JSON.stringify(summary.binding_status_counts || {})}` },
      { label: '组织 / 区划', value: `${summary.org_count || 0} / ${summary.region_count || 0}`, note: '本地只读投影' },
      { label: '角色 / 策略', value: `${summary.role_count || 0} / ${summary.policy_count || 0}`, note: 'Capability policy' },
      { label: '导入问题', value: summary.issue_count || 0, note: 'fail-closed 报告' },
    ])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('IAF 绑定与 Actor 投影', '查看 bound / disabled / unmatched / iam_account_missing', `
          <div class="space-y-3 text-body">
            ${actors.map(item => `<div class="panel"><div class="panel-body"><div class="flex items-center justify-between gap-3"><div class="panel-title text-body">${escapeHtml(item.display_name || item.external_actor_id)}</div>${statusPill(item.status)}</div><div class="row-meta mt-2">${escapeHtml(item.external_actor_id)} · 组织 ${escapeHtml(item.org_code || '—')}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">角色：${(item.role_codes_json || []).map(escapeHtml).join('、') || '无'} · 绑定：${escapeHtml((item.profile_json && item.profile_json.binding_status) || item.status)}</div></div></div>`).join('') || '<div class="text-body text-zw-mute">暂无 Actor 投影</div>'}
          </div>
        `)}
        ${panel('租户 Capability Policy', '查看当前租户能力策略', `
          <table class="gov-table"><tbody>
            ${policies.map(item => `<tr><td>${escapeHtml(item.package_slug)}</td><td>${statusPill(item.policy_status)}</td><td>${escapeHtml((item.policy_json && (item.policy_json.exposedSurfaces || []).join('、')) || '—')}</td></tr>`).join('') || '<tr><td colspan="3">暂无租户策略</td></tr>'}
          </tbody></table>
        `)}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('Policy 裁决探针', '基于当前样本 actor 与租户策略调用 tenant.policy.evaluate', probe ? `
          <div class="text-body leading-7">裁决：${probe.allowed ? '允许' : '拒绝'} · ${escapeHtml(probe.decision_reason || '—')}</div>
          <div class="text-body-sm text-zw-mute leading-7 mt-2">能力：${escapeHtml(probe.capability_id || '—')} · 暴露面：${escapeHtml(probe.surface || '—')} · 审计：${escapeHtml(probe.audit_class || '—')}</div>
        ` : '<div class="text-body text-zw-mute">暂无可探测策略</div>')}
        ${panel('导入问题', '未绑定 IAM、权限未映射、组织关系缺失均 fail-closed', `
          <div class="space-y-2 text-body-sm leading-7">
            ${issues.map(item => `<div>${statusPill('warning')} ${escapeHtml(item.type)} · ${escapeHtml(item.table || '—')} · ${escapeHtml(item.legacy_ref || '—')}</div>`).join('') || '<div class="text-zw-mute">暂无导入问题</div>'}
          </div>
        `)}
        ${panel('审计证据', '策略裁决与导入操作均进入审计总线', `
          <div class="space-y-2 text-body-sm leading-7">
            ${audit.slice(-6).map(item => `<div>${escapeHtml(item.skill_id)}.${escapeHtml(item.phase)} · ${escapeHtml(item.actor || '—')}</div>`).join('') || '<div class="text-zw-mute">暂无治理审计事件</div>'}
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p8', main);
};

PAGES.packageDetail = function (id) {
  const item = packageById(id);
  if (!item) return entityNotFoundShell('p8', '能力包', id, '#/p8-integration-admin', '返回平台接入管理');
  const ai = item.aiReview;
  const statusLabel = packageStatusLabel(item);
  const canApprove = item.status !== 'approved' && item.status !== 'rejected';
  const canReturn = item.status !== 'approved' && item.status !== 'rejected';
  const canReject = item.status !== 'approved' && item.status !== 'rejected';
  const canConfigureExposure = item.versionStatus === 'registered';
  const canApplyTenantPolicy = item.versionStatus === 'registered' && !(item.tenantPolicy && item.tenantPolicy.policyStatus === 'enabled');
  const main = `
    ${crumbs([{ label: '平台接入管理', href: '#/p8-integration-admin' }, { label: item.slug }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${formatPackageName(item.slug)}</div>
          <div class="page-hero-subtitle">${item.source} · 暴露面：${formatExposure(item.exposure)}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(ai.summary, ['查看缺失项', '查看安全项', '查看退回意见'])}

    <div class="grid grid-cols-2 gap-5">
      ${panel('能力包信息', '核对来源、范围、权限和待补项', `
        <table class="gov-table"><tbody>
          <tr><td>审核状态</td><td>${statusLabel}</td></tr>
          <tr><td>版本状态</td><td>${item.versionStatus || 'draft'}</td></tr>
          <tr><td>登记版本</td><td>${item.registeredVersion || '—'}</td></tr>
          <tr><td>租户范围</td><td>${item.tenantScope || '—'}</td></tr>
          <tr><td>权限策略</td><td>${item.authPolicy || '—'}</td></tr>
          <tr><td>兼容面</td><td>${formatExposure(item.compatibility || item.exposure)}</td></tr>
          <tr><td>审计级别</td><td>${item.auditClass}</td></tr>
          <tr><td>人工确认</td><td>${item.requiresHuman ? '需要' : '不需要'}</td></tr>
          <tr><td>描述</td><td>${item.desc}</td></tr>
        </tbody></table>
        <div class="mt-4 text-body-sm text-zw-mute leading-7">缺失项：${ai.missing.length ? ai.missing.join('；') : '无'}</div>
        <div class="mt-2 text-body-sm text-zw-mute leading-7">安全项：${ai.safe.length ? ai.safe.join('；') : '—'}</div>
        <div class="mt-2 text-body-sm text-zw-mute leading-7">租户策略：${item.tenantPolicy ? `${item.tenantPolicy.tenantId} / ${item.tenantPolicy.policyStatus}` : '未生效'}</div>
      `)}
      ${renderDraftCard('AI 草拟的审核意见', [ai.draft], '审核助手只给草案；批准、退回和驳回仍由管理员点击确认。')}
    </div>
    ${panel('审核动作', '管理员确认后生效', `
      <div class="flex gap-3 flex-wrap">
        ${canApprove
          ? `<button onclick="window.ACTIONS.approvePackage('${item.id}')" class="gov-btn gov-btn-primary">批准</button>`
          : `${actionNotice('当前能力包已处于终态')}`}
        ${item.status === 'approved' && item.versionStatus !== 'registered'
          ? `<button onclick="window.ACTIONS.registerPackageVersion('${item.id}')" class="gov-btn gov-btn-secondary">登记版本</button>`
          : ''}
        ${canConfigureExposure
          ? `<button onclick="window.ACTIONS.configurePackageExposure('${item.id}', '${(item.exposure || []).includes('a2a') ? 'tighten' : 'expand'}')" class="gov-btn gov-btn-secondary">${(item.exposure || []).includes('a2a') ? '收紧暴露面' : '扩展暴露面'}</button>`
          : ''}
        ${canApplyTenantPolicy
          ? `<button onclick="window.ACTIONS.applyPackageTenantPolicy('${item.id}')" class="gov-btn gov-btn-secondary">生效租户策略</button>`
          : ''}
        ${canReturn
          ? `<button onclick="window.ACTIONS.returnPackageFix('${item.id}')" class="gov-btn gov-btn-warn">退回补充</button>`
          : ''}
        ${canReject
          ? `<button onclick="window.ACTIONS.rejectPackage('${item.id}')" class="gov-btn gov-btn-danger">驳回</button>`
          : ''}
      </div>
    `)}
  `;
  return shell('p8', main);
};

function formatPackageName(slug) {
  return {
    'ledger.entity.base.read': '法人基础信息只读查询能力',
    'ledger.diff.recommend': '差异字段回流建议能力',
    'ledger.bulk.submit': '批量提交能力（已驳回）',
  }[slug] || slug;
}

function formatExposure(values) {
  const map = { api: '接口', cli: '命令行', mcp: '工具接入', a2a: '智能体协同' };
  return (values || []).map(item => map[item] || item).join(' / ');
}
