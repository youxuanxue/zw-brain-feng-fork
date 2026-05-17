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

function safeHashHref(value, fallback = '#/p1-workbench') {
  const text = String(value || '');
  if (/^#\/[A-Za-z0-9_./:-]*$/.test(text)) return text;
  return fallback;
}

/**
 * B2 — fold raw audit hashes / UUIDs out of the primary content position.
 * `formatIdShort` returns a human-friendly short label (e.g. "申请-3ade3")
 * for 24+ char hex IDs, leaves human-readable IDs (REQ-..., REV-...) alone.
 */
function formatIdShort(value, prefix = '记录') {
  const s = String(value || '');
  if (!s) return '';
  // Any opaque machine identifier longer than 18 chars without spaces is
  // unreadable as a primary label — collapse to "{prefix}-{last-5-alphanum}".
  // Covers UUIDs ("018f2944..."), unified social credit codes
  // ("11370000MB284651XL2001..."), slash-separated catalog codes
  // ("307013370000308002000000/000045"), etc.
  const compact = s.replace(/[-/\s]/g, '');
  if (compact.length >= 18 && /^[A-Za-z0-9]+$/.test(compact) && !/^[A-Z]+-?\d{0,4}$/i.test(s)) {
    return `${prefix}-${compact.slice(-5).toUpperCase()}`;
  }
  return s;
}

/**
 * B3 — when a grassroots user (R3/R4) views a field's owner, never expose
 * the cross-role role code (R3/R4/R5). Map it to a role-neutral phrase so a
 * R3 user does not see "R4 补录" and vice versa. Non-grassroots users still
 * see the breakdown because they coordinate across the team.
 */
function ownerForViewer(rawOwner, viewerRole) {
  const s = String(rawOwner || '').trim();
  if (!s) return '';
  const isGrassroots = viewerRole === 'r3' || viewerRole === 'r4';
  if (!isGrassroots) return s;
  // R3 / R4 only ever see their own bucket: "现场补录".
  if (/R[345]/i.test(s)) return '现场补录';
  return s;
}

/** Inline chip that hides a full hash behind a copy affordance. */
function evidenceChip(label, fullValue) {
  const v = String(fullValue || '');
  if (!v) return '';
  const safe = escapeHtml(v);
  const short = escapeHtml(v.length > 14 ? `${v.slice(0, 6)}…${v.slice(-4)}` : v);
  return `<span class="audit-chip" title="${safe}" data-copy="${safe}" onclick="window.UI.copyToClipboard(this.getAttribute('data-copy'))" style="cursor:pointer">${escapeHtml(label)} ${short}</span>`;
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
    return '<span class="text-body-sm text-zw-mute leading-7">独立大屏入口暂未开放，请先在审计证据页查看治理状态。</span>';
  }
  const safe = escapeHtml(href);
  return `<a href="${safe}" target="_blank" rel="noopener noreferrer">查看独立大屏</a>`;
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
  return `<span class="status-pill ${map[status] || 'status-neutral'}">${escapeHtml(statusLabel(status))}</span>`;
}

function crumbs(items) {
  return `
    <nav class="text-body-sm text-zw-mute mb-2 flex items-center gap-2 flex-wrap crumbs">
      ${items.map((it, i) => i === items.length - 1
        ? `<span class="text-zw-ink">${escapeHtml(it.label)}</span>`
        : `<a href="${safeHashHref(it.href || '#/p1-workbench')}">${escapeHtml(it.label)}</a><span class="crumb-sep">/</span>`
      ).join('')}
    </nav>`;
}

function stepBar(steps, activeIdx) {
  return `
    <div class="flex items-center gap-2 text-caption text-zw-mute flex-wrap">
      ${steps.map((s, i) => `
        <span class="step-dot ${i < activeIdx ? 'done' : i === activeIdx ? 'now' : 'todo'}">${i < activeIdx ? '✓' : i + 1}</span>
        <span class="${i === activeIdx ? 'text-zw-ink font-medium' : ''}">${escapeHtml(s)}</span>
        ${i < steps.length - 1 ? '<span class="opacity-30">───</span>' : ''}
      `).join('')}
    </div>`;
}

function statCards(items) {
  return `
    <div class="grid gov-stats-grid gap-4">
      ${items.map(item => {
        const inner = `
          <div class="gov-stat-label">${escapeHtml(item.label)}</div>
          <div class="gov-stat-value">${escapeHtml(item.value)}</div>
          ${item.note ? `<div class="gov-stat-note">${escapeHtml(item.note)}</div>` : ''}
          ${item.href ? '<div class="gov-stat-action">查看</div>' : ''}`;
        return item.href
          ? `<a href="${safeHashHref(item.href)}" class="gov-stat-card gov-stat-link">${inner}</a>`
          : `<div class="gov-stat-card">${inner}</div>`;
      }).join('')}
    </div>`;
}

function infoList(items) {
  return `
    <div class="gov-list">
      ${(items || []).map(item => `
        <div class="gov-list-row">
          <div>
            <div class="row-title">${escapeHtml(item.title)}</div>
            <div class="row-meta">${escapeHtml(item.status)}</div>
          </div>
          <a href="${safeHashHref(item.href)}" class="row-actions">查看</a>
        </div>`).join('')}
    </div>`;
}

function renderInlineSummary(summary, actions) {
  return `
    <div class="panel" data-ai-surface="inline-summary">
      <div class="panel-body py-4">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div class="text-body leading-7 text-zw-ink flex-1">${escapeHtml(summary)}</div>
          ${actions && actions.length ? `<div class="flex flex-wrap gap-2 justify-end">${actions.map(item => `<span class="ai-tag">${escapeHtml(item)}</span>`).join('')}</div>` : ''}
        </div>
      </div>
    </div>`;
}

function renderDraftCard(title, lines, note) {
  return `
    <div class="draft-card" data-ai-surface="draft-card">
      <div class="draft-title">${escapeHtml(title)}</div>
      <div class="explain-list">${(lines || []).map(line => `<div>${escapeHtml(line)}</div>`).join('')}</div>
      ${note ? `<div class="mt-3 text-body-sm text-zw-mute leading-7">${escapeHtml(note)}</div>` : ''}
    </div>`;
}

function renderFieldState(label, value, state, note) {
  const chip = state === '已预填' || state === '已识别' ? 'chip-ok' : 'chip-ask';
  return `
    <div class="panel p-3 bg-zw-bg-soft rounded-lg">
      <div class="row-meta mb-1">${escapeHtml(label)}</div>
      <div class="row-title">${escapeHtml(value)}</div>
      <div class="mt-2 flex items-center gap-2 flex-wrap">
        <span class="chip ${chip}">${escapeHtml(state)}</span>
        ${note ? `<span class="text-body-sm text-zw-mute">${escapeHtml(note)}</span>` : ''}
      </div>
    </div>`;
}

function renderFieldBindingEvidence(item) {
  const summary = item.fieldBindingSummary;
  const bindings = item.fieldBindings || [];
  if (!summary && !bindings.length) return '';
  const diagnosis = summary ? summary.diagnosis || 'attention_required' : 'attention_required';
  const rows = bindings.length ? bindings.map(binding => {
    const replay = (binding.replay && binding.replay.steps) || [];
    const sourceColumn = binding.explain && binding.explain.source_column ? binding.explain.source_column : '—';
    const catalogTitle = binding.catalog_item_title || binding.catalog_item_code || binding.mapping_code;
    return `
      <div class="gov-list-row">
        <div>
          <div class="row-title">${escapeHtml(catalogTitle)} → ${escapeHtml(sourceColumn)}</div>
          <div class="row-meta mt-2">${escapeHtml(binding.mapping_code)} · ${escapeHtml(binding.evidence_ref || binding.source_ref || '无证据编号')} · 置信度 ${escapeHtml(binding.confidence_level || '—')}</div>
          <div class="mt-2 text-body-sm text-zw-mute leading-7">解释：${escapeHtml((binding.explain && binding.explain.summary) || '已建立目录项到资源字段的绑定。')}</div>
          <div class="mt-2 text-body-sm text-zw-mute leading-7">回放：${replay.map(step => `${step.step}:${step.ref || step.status}`).map(escapeHtml).join(' → ')}</div>
        </div>
        ${statusPill(binding.diagnosis && binding.diagnosis.ok ? 'ok' : 'warning')}
      </div>`;
  }).join('') : '<div class="text-body text-zw-mute py-4">当前目录还没有可回放的字段绑定记录，可把需要的字段作为缺口写入申请。</div>';
  return panel('字段绑定解释', `诊断：${diagnosis} · 活跃 ${summary ? summary.active : 0} / 共 ${summary ? summary.total : bindings.length} 条`, `<div class="gov-list">${rows}</div>`);
}

function renderResourceEvidencePanels(item) {
  const access = item.accessPolicy || {};
  const sensitive = item.sensitivePolicy || {};
  const gap = item.reuseGapHint || {};
  const assets = item.resourceAssets || [];
  const snapshots = item.schemaSnapshots || [];
  const mappings = item.legacyMappings || [];
  return `
    <div class="grid grid-cols-2 gap-5 mt-5">
      ${panel('共享条件与安全策略', '先确认能不能复用，再决定申请范围', `
        <div class="space-y-3 text-body leading-7">
          <div>提供方：<strong>${escapeHtml(access.provider || item.provider || '—')}</strong></div>
          <div>区域范围：<strong>${escapeHtml(access.regionCode || item.regionCode || item.zone || '—')}</strong></div>
          <div>共享条件：<strong>${escapeHtml(access.shareCondition || '按受控申请审批')}</strong></div>
          <div>共享方式：<strong>${escapeHtml(access.shareWay || '—')}</strong></div>
          <div>敏感策略：<strong>${escapeHtml(sensitive.display || '查询与导出侧按字段敏感级别脱敏。')}</strong></div>
          <div class="text-zw-mute">字段敏感级别：${escapeHtml((sensitive.fieldSensitiveLevels || []).join(' / ') || '未标注')}</div>
        </div>
      `)}
      ${panel('复用与缺口判断', '明确已有证据和仍需补充的内容', `
        <div class="text-body leading-7 text-zw-ink">${escapeHtml(gap.message || '先查看字段证据，再把缺口写入最小申请。')}</div>
        <div class="mt-3 text-body-sm text-zw-mute">可复用字段：${escapeHtml(String(gap.readyFieldCount ?? (item.fields || []).length))} 项</div>
        <div class="mt-2 text-body-sm text-zw-mute">缺口字段：${escapeHtml((gap.gapFields || []).join(' / ') || '暂无')}</div>
      `)}
    </div>
    <div class="grid grid-cols-2 gap-5 mt-5">
      ${panel('资源与 schema 证据', '查看资源状态、schema 快照和来源表绑定', `
        <div class="gov-list">
          ${assets.length ? assets.map(asset => `<div class="gov-list-row"><div><div class="row-title">${escapeHtml(asset.title || asset.resource_code)}</div><div class="row-meta">${escapeHtml(asset.resource_code)} · ${escapeHtml(asset.resource_kind || '—')} · ${escapeHtml(asset.lifecycle_status || '—')}</div></div>${statusPill(asset.lifecycle_status || 'active')}</div>`).join('') : '<div class="text-body text-zw-mute py-4">当前目录暂无资源资产记录。</div>'}
          ${snapshots.length ? snapshots.map(snapshot => `<div class="gov-list-row"><div><div class="row-title">schema 快照 ${escapeHtml(snapshot.snapshot_ref)}</div><div class="row-meta">${escapeHtml(snapshot.resource_code)} · ${escapeHtml(snapshot.binding_code || '—')} · ${escapeHtml(snapshot.source_ref || '—')}</div></div>${statusPill('可查看')}</div>`).join('') : ''}
        </div>
      `)}
      ${panel('旧平台回指证据', '用于现场核验：这条读面来自真实旧平台导入', `
        <div class="gov-list">
          ${mappings.length ? mappings.slice(0, 8).map(mapping => `<div class="gov-list-row"><div><div class="row-title">${escapeHtml(mapping.legacy_system)} · ${escapeHtml(mapping.legacy_object_type)}</div><div class="row-meta">${escapeHtml(mapping.legacy_object_ref)} → ${escapeHtml(mapping.canonical_type)}:${escapeHtml(mapping.canonical_ref)}</div></div>${statusPill(mapping.mapping_status || 'mapped')}</div>`).join('') : '<div class="text-body text-zw-mute py-4">当前读面暂无 legacy_object_mapping 回指。</div>'}
        </div>
      `)}
    </div>`;
}

function actionNotice(message) {
  return `<span class="action-note">提示：${escapeHtml(message)}</span>`;
}

function panel(title, subtitle, body, extraClass = '') {
  return `
    <div class="panel ${extraClass}">
      <div class="panel-body">
        <div class="panel-title">${escapeHtml(title)}</div>
        ${subtitle ? `<div class="panel-subtitle">${escapeHtml(subtitle)}</div>` : ''}
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

/** Sidebar labels + canonical section titles (breadcrumbs / page kickers must stay in sync with this). */
const PRODUCT_SHELL_NAV = [
  // P0 (M0 迁移验收) 是实施工具，不在客户产品导航里。
  // 实施工程师 / 平台运维通过直接访问 #/p0-migration-acceptance 进入；
  // 客户 R7/R8 不应在导航中看到此入口，也不应处理冲突这类技术债。
  {
    key: 'p1',
    sectionTitle: '数据共享工作台',
    navLabel: '数据共享工作台',
    href: '#/p1-workbench',
    roles: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'],
    desc: '搜索、待办、证据入口',
  },
  {
    key: 'p2',
    sectionTitle: '数据资源发现',
    navLabel: '找可复用数据',
    href: '#/p2-discovery',
    roles: ['r1', 'r2', 'r6', 'r7', 'r8'],
    desc: '先找资源和专题资产',
  },
  {
    key: 'p3',
    sectionTitle: '共享申请与审批',
    navLabel: '办共享申请',
    href: '#/p3-request-flow',
    roles: ['r1', 'r2', 'r3', 'r4', 'r5'],
    desc: '申请、审批、补差异',
  },
  {
    key: 'p4',
    sectionTitle: '交付交换与回流',
    navLabel: '看交付回执',
    href: '#/p4-delivery-exchange',
    roles: ['r2', 'r5', 'r6', 'r7', 'r8'],
    desc: '交付、对账、回流',
  },
  {
    key: 'p5',
    sectionTitle: '维护数据供给',
    navLabel: '维护数据供给',
    href: '#/p5-provider',
    roles: ['r6', 'r7'],
    desc: '目录、资源、服务上架',
  },
  {
    key: 'p6',
    sectionTitle: '合规运营与减负',
    navLabel: '查审计证据',
    href: '#/p6-compliance-ops',
    roles: ['r2', 'r5', 'r6', 'r7', 'r8'],
    desc: '重复要数与证据回放',
  },
  {
    key: 'p7',
    sectionTitle: '共享专区 / 专题包',
    navLabel: '进专题包',
    href: '#/p7-zones-pack',
    roles: ['r1', 'r2', 'r6', 'r7', 'r8'],
    desc: '一表通等场景入口',
  },
  {
    key: 'p8',
    sectionTitle: '受控接入治理',
    navLabel: '管受控接入',
    href: '#/p8-integration-admin',
    roles: ['r7'],
    desc: '外部能力上线边界',
  },
];

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
  if (path.includes('/p8-integration-admin')) return '打开受控接入治理';
  if (path.includes('/dashboard/')) return '打开关联告警视图';
  if (path.includes('/p2-discovery')) return '打开数据资源发现';
  if (path.includes('/p3-request-flow')) return '打开共享申请列表';
  return '进入办理';
}

function renderWorkbenchDrillStrip(todos) {
  const list = Array.isArray(todos) ? todos.filter(t => t && t.href && t.title) : [];
  if (!list.length) {
    return `
    <div class="workbench-drill-strip mt-5" role="region" aria-label="待办快捷入口">
      <div class="workbench-drill-kicker">待办快捷入口</div>
      <div class="workbench-drill-empty">当前没有可一键直达的待办，请从上方办理卡片或指标进入对应场景。</div>
    </div>`;
  }
  const cards = list.map(todo => `
    <a href="${escapeHtml(todo.href)}">
      <span>${escapeHtml(todo.status || '待办')}</span>
      <strong>${escapeHtml(todo.title)}</strong>
      <em>${escapeHtml(workbenchDrillHintFromHref(todo.href))}</em>
    </a>`).join('');
  return `
    <div class="workbench-drill-strip mt-5" role="region" aria-label="待办快捷入口">
      <div class="workbench-drill-kicker">待办快捷入口 · 由当前工作台待办生成</div>
      <div class="workbench-value-grid workbench-value-grid--drill">${cards}</div>
    </div>`;
}

function shell(activeKey, mainHtml) {
  const role = window.STATE.role;
  const navCollapsed = isBusinessNavCollapsed();
  const nav = PRODUCT_SHELL_NAV.map(item => ({
    key: item.key,
    label: item.navLabel,
    href: item.href,
    roles: item.roles,
    desc: item.desc,
  }));

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
                  <div class="product-role-chip">当前身份：${roleLabel(role)}</div>
                  ${(() => {
                    // W7.5: 入口少时（≤3）不显示长说明，避免说明 vs 内容比例失衡；多于 3 个才显示
                    const visibleCount = nav.filter(item => item.roles.includes(role)).length;
                    return visibleCount > 3 ? '<div class="panel-subtitle mt-3">按当前身份只展示能办理、可查看和需要人工确认的入口。</div>' : '';
                  })()}
                  <div class="mt-4 space-y-1.5">
                    ${nav.filter(item => item.roles.includes(role)).map(item => {
                      // W6.3: 隐藏受限项，不显示灰色"受限"残影 — 避免一半导航都是"我不能办"
                      const isActive = item.key === activeKey;
                      return `
                    <a href="${item.href}"
                       class="product-nav-link ${isActive ? 'is-active' : ''}">
                      <span><strong>${item.label}</strong><em>${item.desc}</em></span>
                      <span class="product-nav-state">${isActive ? '当前' : '进入'}</span>
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

/** 与侧栏 `PRODUCT_SHELL_NAV[].roles` 一致；服务端预加载裁剪见 `zw_brain/domain/web_snapshot_redaction.py` */
window.ZW_PAGE_ACCESS = {
  // P0 (M0 迁移验收) 是实施工具，仅 admin（平台实施工程师）可直接访问。
  // 客户角色 r7/r8 既不在导航看到它，也不能直接访问。
  // 客户验收日实施工程师以 admin 身份打开本页让客户高层看一眼，不交互。
  migrationAcceptance: ['admin'],
  workbench: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'],
  login: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'],
  discovery: ['r1', 'r2', 'r6', 'r7', 'r8'],
  catalogBrowse: ['r1', 'r2', 'r6', 'r7', 'r8'],
  resourceDetail: ['r1', 'r2', 'r6', 'r7', 'r8'],
  requestFlow: ['r1', 'r2', 'r3', 'r4', 'r5'],
  requestDetail: ['r1', 'r2', 'r3', 'r4', 'r5'],
  reviewDetail: ['r2', 'r5'],
  deliveryExchange: ['r2', 'r5', 'r6', 'r7', 'r8'],
  deliveryTaskDetail: ['r2', 'r5', 'r6', 'r7', 'r8'],
  provider: ['r6', 'r7'],
  providerWizardReverseCatalog: ['r6'],
  providerWizardApiService: ['r6'],
  providerWizardQualityRule: ['r6'],
  providerInboxFieldDecision: ['r7'],
  providerInboxFieldDecisionDetail: ['r7'],
  providerInboxHookupReview: ['r7'],
  providerInboxDemandMatch: ['r7'],
  providerInboxDemandMatchDetail: ['r7'],
  complianceOps: ['r2', 'r5', 'r6', 'r7', 'r8'],
  disputeDetail: ['r2', 'r5', 'r6', 'r7', 'r8'],
  zonesPack: ['r1', 'r2', 'r6', 'r7', 'r8'],
  zoneDetail: ['r1', 'r2', 'r6', 'r7', 'r8'],
  integrationAdmin: ['r7'],
  iamGovernance: ['r7'],
  packageDetail: ['r7'],
};

window.ZW_PAGE_SHELL = {
  migrationAcceptance: 'p0',
  workbench: 'p1',
  login: 'p1',
  discovery: 'p2',
  catalogBrowse: 'p2',
  resourceDetail: 'p2',
  requestFlow: 'p3',
  requestDetail: 'p3',
  reviewDetail: 'p3',
  deliveryExchange: 'p4',
  deliveryTaskDetail: 'p4',
  provider: 'p5',
  providerWizardReverseCatalog: 'p5',
  providerWizardApiService: 'p5',
  providerWizardQualityRule: 'p5',
  providerInboxFieldDecision: 'p5',
  providerInboxFieldDecisionDetail: 'p5',
  providerInboxHookupReview: 'p5',
  providerInboxDemandMatch: 'p5',
  providerInboxDemandMatchDetail: 'p5',
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
  const backText = escapeHtml(backLabel || '回到数据共享工作台');
  const main = `
    <div class="state-card">
      <div class="page-kicker">未找到${label}</div>
      <div class="page-hero-title">这条记录当前不可办理。</div>
      <p class="page-hero-subtitle">可能已下线、编号有误，或当前身份没有查看范围。你可以返回上一办理入口，继续查找可复用数据或查看已有进度。</p>
      <div class="state-meta">记录编号：<code>${id}</code></div>
      <div class="mt-5 flex gap-3 flex-wrap">
        <a href="${safeBack}" class="gov-btn gov-btn-primary">${backText}</a>
        <a href="#/p1-workbench" class="gov-btn gov-btn-secondary">回到数据共享工作台</a>
      </div>
    </div>`;
  return shell(activeKey, main);
}

window.renderAccessDeniedShell = function (pageKey) {
  const sk = window.ZW_PAGE_SHELL[pageKey] || 'p1';
  const main = `
    <div class="state-card">
      <div class="page-kicker">当前身份不可办理</div>
      <div class="page-hero-title">这个入口暂不属于你的岗位范围。</div>
      <p class="page-hero-subtitle">系统只展示你可以负责的申请、审批、交付或审计动作。请返回数据共享工作台，从当前身份可办理的入口继续。</p>
      <div class="state-meta">当前身份：${roleLabel(window.STATE.role)}</div>
      <div class="mt-5 flex gap-3 flex-wrap">
        <a href="#/p1-workbench" class="gov-btn gov-btn-primary">查看我能办理的事项</a>
        <a href="#/p2-discovery" class="gov-btn gov-btn-secondary">先找可复用数据</a>
      </div>
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
function asList(value) {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null || value === '') return [];
  return [value];
}
function businessValue(value, fallback = '—') {
  if (value === undefined || value === null || value === '') return fallback;
  return escapeHtml(value);
}
function businessList(items, fallback = '—') {
  const list = asList(items).filter(item => item !== undefined && item !== null && item !== '');
  return list.length ? list.map(escapeHtml).join(' / ') : fallback;
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

PAGES.migrationAcceptance = function () {
  const state = window.RUNTIME_MIGRATION_ACCEPTANCE;
  if (!state) {
    return shell('p0', `
      ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: 'M0 迁移验收' }])}
      <div class="state-card">
        <div class="page-kicker">M0 迁移验收</div>
        <div class="page-hero-title">正在加载迁移状态…</div>
        <p class="page-hero-subtitle">从 legacy_object_mapping 与 adapter_run_record 聚合 11 张工作队列卡片状态。</p>
      </div>
    `);
  }
  const totals = state.totals || {};
  const cards = state.work_queue_cards || [];
  const byCanonical = state.by_canonical_type || [];
  const byLegacy = state.by_legacy_system || [];
  const runs = state.recent_adapter_runs || [];
  const rollbacks = state.recent_rollbacks || [];
  // W6 视觉优化：用正确的 CSS class (status-ok / -warn / -danger / -neutral)
  const cardStatusPill = (s) => {
    const cls = { ready: 'status-ok', partial: 'status-warn', pending: 'status-neutral', failed: 'status-danger' }[s] || 'status-neutral';
    const label = { ready: '已通过', partial: '待裁决', pending: '待处理', failed: '失败' }[s] || s;
    return `<span class="status-pill ${cls}">${escapeHtml(label)}</span>`;
  };
  // M0 是实施工具页面 — 不让客户去处理冲突，全部由实施工程师 CLI 处理。
  // 各卡片显示对应的 CLI 命令而非 WebUI 跳转。
  const cardCli = (id) => {
    const cli = {
      mapping_verify: '.venv/bin/python scripts/import_legacy_dumps.py verify --strict',
      catalog_migration_review: '.venv/bin/python scripts/import_legacy_dumps.py verify --canonical-type=catalog_entry',
      schema_mapping: '.venv/bin/python scripts/import_legacy_dumps.py verify --canonical-type=resource_asset',
      application_history: '.venv/bin/python scripts/import_legacy_dumps.py verify --canonical-type=application_record',
      rollback: '.venv/bin/python -m zw_brain.entry.legacy_migration.rollback --tenant=sd-default --legacy-system=<schema> --commit',
      export: 'bash scripts/customer_export.sh --db-host=... --output-dir=... --batch-id=B-...',
      import: 'bash scripts/customer_acceptance_up.sh',
      gap_reimport: 'bash scripts/customer_acceptance_up.sh  # 幂等重跑追加',
    }[id];
    return cli ? `<div class="row-meta mt-2 text-body-sm" style="font-family:monospace;background:#f6f8fa;padding:6px 8px;border-radius:4px;">$ ${escapeHtml(cli)}</div>` : '';
  };
  const tCellNum = (n, danger) => `<td class="num"${danger && n ? ' style="color:#b71c1c;font-weight:600"' : ''}>${Number(n || 0).toLocaleString()}</td>`;
  const conflictRate = totals.mappings ? (totals.conflicted / totals.mappings * 100) : 0;
  const partialCount = cards.filter(c => c.status === 'partial').length;
  const pendingCount = cards.filter(c => c.status === 'pending').length;
  const failedCount = cards.filter(c => c.status === 'failed').length;
  const allReady = partialCount === 0 && pendingCount === 0 && failedCount === 0 && totals.conflicted === 0;
  // canonical 分布：按 total 降序 + 默认折叠 0 行
  const sortedCanonical = [...byCanonical].sort((a, b) => (b.total || 0) - (a.total || 0)).filter(r => r.total > 0);
  const sortedLegacy = [...byLegacy].sort((a, b) => (b.total || 0) - (a.total || 0)).filter(r => r.total > 0);
  // 占比条
  const maxCanonical = Math.max(...sortedCanonical.map(r => r.total || 0), 1);
  const maxLegacy = Math.max(...sortedLegacy.map(r => r.total || 0), 1);
  const bar = (n, max) => {
    const pct = Math.min(100, Math.round((n || 0) / max * 100));
    return `<div style="width:60px;height:6px;background:#eef2f7;border-radius:3px;display:inline-block;vertical-align:middle;overflow:hidden;"><div style="width:${pct}%;height:100%;background:var(--b-primary);"></div></div>`;
  };

  // ───────────── 实施监控焦点卡（不让客户进，无业务 CTA）─────────────
  const focusCard = allReady
    ? `
      <div class="state-card" style="background:linear-gradient(135deg,#e8f5e9 0%,#f1f8f4 100%);border-left:4px solid #1b5e20;">
        <div class="flex items-center gap-3">
          <div style="font-size:32px;line-height:1">✓</div>
          <div style="flex:1">
            <div class="row-title text-zw-ink">M0 迁移已就绪，可向客户移交</div>
            <div class="row-meta mt-1">11 张工作队列卡片状态正常；映射 ${Number(totals.mappings || 0).toLocaleString()} 条全部 mapped 且零冲突。运行 <code>bash scripts/customer_acceptance_up.sh</code> 重新出验收报告即可。</div>
          </div>
        </div>
      </div>`
    : `
      <div class="state-card" style="background:linear-gradient(135deg,#eef2f7 0%,#f7f9fc 100%);border-left:4px solid #5e6c84;">
        <div class="flex items-start gap-3">
          <div style="font-size:24px;line-height:1;color:#5e6c84">⚙</div>
          <div style="flex:1">
            <div class="row-title text-zw-ink">实施期残余技术债 — 由实施团队 CLI 处理</div>
            <div class="row-meta mt-1">
              ${totals.conflicted ? `映射剩 <strong>${Number(totals.conflicted).toLocaleString()} 条 conflicted</strong>（占 ${conflictRate.toFixed(2)}%）多集中在 <code>dsp-catalog3</code> 的 approval_step / approval_decision；建议按时间戳保留最新版本。` : ''}
              ${!totals.conflicted && (partialCount + pendingCount) ? `${partialCount} 张 partial + ${pendingCount} 张 pending 待处理。` : ''}
            </div>
            <div class="row-meta mt-2 text-body-sm">
              <strong>客户角色 (R1-R8) 看不到此页</strong>；R7/R8 在 zw-brain 中只看到已迁干净的目录、资源、申请。剩余 conflicted 不暴露给业务人员裁决。
            </div>
          </div>
        </div>
      </div>`;

  const lastRunTime = runs.length ? (runs[0].finished_at || runs[0].started_at) : null;

  const main = `
    ${crumbs([{ label: 'M0 迁移监控（内部）' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">M0 迁移监控（仅平台实施）</div>
          <div class="page-hero-title">实施期诊断面板 — 不暴露给客户业务岗位</div>
          <div class="page-hero-subtitle">租户 <code>${escapeHtml(state.tenant_id || 'sd-default')}</code>${lastRunTime ? ` · 上次同步 <code>${escapeHtml(lastRunTime)}</code>` : ''} · 客户 R1-R8 看到的是已迁干净的系统，不会看到本页</div>
        </div>
        <div class="page-meta">实施工程师 · admin</div>
      </div>
    </div>

    ${focusCard}

    <div class="grid grid-cols-4 gap-4 mt-5">
      <div class="gov-stat-card"><div class="gov-stat-label">总映射条目</div><div class="gov-stat-value">${Number(totals.mappings || 0).toLocaleString()}</div><div class="mt-2 text-caption text-zw-mute">legacy_object_mapping 全量</div></div>
      <div class="gov-stat-card"><div class="gov-stat-label" style="color:#1b5e20;">✓ 已映射 mapped</div><div class="gov-stat-value" style="color:#1b5e20;">${Number(totals.mapped || 0).toLocaleString()}</div><div class="mt-2 text-caption text-zw-mute">占 ${totals.mappings ? (totals.mapped / totals.mappings * 100).toFixed(1) : '0'}%</div></div>
      <div class="gov-stat-card" ${totals.conflicted ? 'style="background:#fff5f5;border-color:#fcc;"' : ''}><div class="gov-stat-label" ${totals.conflicted ? 'style="color:#b71c1c;"' : ''}>${totals.conflicted ? '! ' : ''}冲突 conflicted</div><div class="gov-stat-value" ${totals.conflicted ? 'style="color:#b71c1c;"' : ''}>${Number(totals.conflicted || 0).toLocaleString()}</div><div class="mt-2 text-caption text-zw-mute">${totals.conflicted ? '由实施期 CLI 处理' : '无冲突'}</div></div>
      <div class="gov-stat-card"><div class="gov-stat-label">已回滚 rolled_back</div><div class="gov-stat-value">${Number(totals.rolled_back || 0).toLocaleString()}</div><div class="mt-2 text-caption text-zw-mute">${totals.rolled_back ? '查看 audit_event' : '尚未触发'}</div></div>
    </div>

    ${panel('11 张 M0 工作队列卡片', `${cards.filter(c => c.status === 'ready').length} 已完成 · ${partialCount} 部分完成 · ${pendingCount} 待跑${failedCount ? ` · ${failedCount} 失败` : ''}  · 每张卡片对应的 CLI 命令在卡内显示`, `
      <div class="grid grid-cols-2 gap-4">
        ${cards.map(c => {
          const needAction = c.status === 'partial' || c.status === 'pending' || c.status === 'failed';
          return `
          <div class="gov-card" ${c.status === 'failed' ? 'style="border-left:3px solid var(--b-danger);"' : c.status === 'partial' ? 'style="border-left:3px solid #f57c00;"' : ''}>
            <div class="gov-card-head">
              <div class="row-title">${escapeHtml(c.title)}</div>
              ${cardStatusPill(c.status)}
            </div>
            <div class="row-meta mt-2">${escapeHtml(c.owner || '')}</div>
            <div class="text-body-sm mt-2 text-zw-mute">${escapeHtml(c.summary || '')}</div>
            ${needAction ? cardCli(c.id) : ''}
          </div>`;
        }).join('')}
      </div>
    `)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('按 canonical_type 分布', `${sortedCanonical.length} 种实体；按映射数降序；零值已折叠`, `
        <table class="gov-table text-body-sm">
          <thead><tr><th>canonical_type</th><th>占比</th><th class="num">total</th><th class="num">mapped</th><th class="num">conflicted</th></tr></thead>
          <tbody>${sortedCanonical.slice(0, 15).map(r => `<tr><td>${escapeHtml(r.canonical_type)}</td><td>${bar(r.total, maxCanonical)}</td>${tCellNum(r.total)}${tCellNum(r.mapped)}${tCellNum(r.conflicted, true)}</tr>`).join('') || '<tr><td colspan="5" class="row-meta">尚无映射条目</td></tr>'}</tbody>
        </table>
        ${sortedCanonical.length > 15 ? `<div class="row-meta mt-2 text-body-sm">仅显示前 15 行；共 ${sortedCanonical.length} 行非零数据。</div>` : ''}
      `)}
      ${panel('按 legacy_system 分布', `${sortedLegacy.length} 个旧库；按映射数降序`, `
        <table class="gov-table text-body-sm">
          <thead><tr><th>legacy_system</th><th>占比</th><th class="num">total</th><th class="num">mapped</th><th class="num">conflicted</th></tr></thead>
          <tbody>${sortedLegacy.map(r => `<tr><td>${escapeHtml(r.legacy_system)}</td><td>${bar(r.total, maxLegacy)}</td>${tCellNum(r.total)}${tCellNum(r.mapped)}${tCellNum(r.conflicted, true)}</tr>`).join('') || '<tr><td colspan="5" class="row-meta">尚无映射条目</td></tr>'}</tbody>
        </table>
      `)}
    </div>

    ${panel('最近 adapter_run（最多 20 条）', '按 finished_at 倒序；失败的红色高亮', `
      <table class="gov-table text-body-sm">
        <thead><tr><th>adapter_slug</th><th>operation</th><th>status</th><th class="num">target</th><th class="num">success</th><th class="num">failure</th><th>finished_at</th></tr></thead>
        <tbody>${runs.map(r => `<tr><td>${escapeHtml(r.adapter_slug)}</td><td>${escapeHtml(r.operation || '')}</td><td>${cardStatusPill(r.status === 'succeeded' ? 'ready' : (r.status === 'failed' ? 'failed' : 'pending'))}</td>${tCellNum(r.target_count)}${tCellNum(r.success_count)}${tCellNum(r.failure_count, true)}<td class="row-meta">${escapeHtml(r.finished_at || '')}</td></tr>`).join('') || '<tr><td colspan="7" class="row-meta">尚无 adapter run</td></tr>'}</tbody>
      </table>
    `)}

    ${panel('最近 rollback（最多 5 条）', 'audit_event(skill_id=legacy.migration.rollback) 摘要', `
      ${rollbacks.length ? `
      <table class="gov-table text-body-sm">
        <thead><tr><th>audit_id</th><th>actor</th><th>occurred_at</th><th>scope</th><th class="num">rolled_back</th></tr></thead>
        <tbody>${rollbacks.map(r => `<tr><td><code>${escapeHtml((r.audit_id || '').slice(0, 8))}</code></td><td>${escapeHtml(r.actor || '')}</td><td>${escapeHtml(r.occurred_at || '')}</td><td><code class="text-body-sm">${escapeHtml(JSON.stringify(r.scope || {}))}</code></td>${tCellNum(r.rolled_back)}</tr>`).join('')}</tbody>
      </table>
      ` : '<div class="row-meta text-body-sm">尚未触发 rollback — 这是好事，意味着本批迁移没出现需要冻结的批次。</div>'}
    `)}
  `;
  return shell('p0', main);
};

// W6.6: SVG 矢量图标（替代单字色块）
const WORKBENCH_ICONS = {
  search: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
  apply: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>',
  progress: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>',
  delivery: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>',
  audit: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
  topic: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"/></svg>',
  catalog: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>',
  api: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m10 13-2 2 2 2M14 17l2-2-2-2M5 3a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2Z"/></svg>',
  shield: '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/></svg>',
};

// W6.1: 按角色定制 hero 文案 + 主入口排序
const ROLE_HERO = {
  r1: {
    kicker: '数据共享工作台',
    title: '从一个业务需求开始，先找可复用数据。',
    subtitle: '找得到就复用；要使用就发起受控申请；交付、回流和审计在同一条链上追踪。',
    primary: ['search', 'apply', 'progress', 'delivery', 'topic'],
  },
  r2: {
    kicker: '审批承接台',
    title: '把住重复要数阀门 — 看待审申请、复用判断、授权边界。',
    subtitle: '不是把申请原样转发，而是看证据链做准入判定：分级授权 / 撤回处置 / API 边界审。',
    primary: ['progress', 'audit', 'delivery', 'search'],
  },
  r3: {
    kicker: '镇街补差任务',
    title: '只补差异，不重填整表。',
    subtitle: '看任务卡 → 补现场变化 → 提交。异常一键回传，不靠线下沟通。',
    primary: ['apply', 'progress'],
  },
  r4: {
    kicker: '村社区核实任务',
    title: '现场核实，只看任务卡。',
    subtitle: '任务卡告诉你补哪些字段、不补哪些。看不懂的字段一键回传上级。',
    primary: ['apply', 'progress'],
  },
  r5: {
    kicker: '审核汇总台',
    title: '盯异常、确认自动汇总。',
    subtitle: '不再线下拼表 — 系统已汇总好的结果在这里集中处理异常、口径冲突、质量证据。',
    primary: ['progress', 'audit', 'delivery'],
  },
  r6: {
    kicker: '数据供给台账',
    title: '把目录、资源、API 准备好 — 让 R1 一搜就用。',
    subtitle: '反向编目 / API 服务化 / 自动检测规则 — 4 张工作流卡都在"维护数据供给"。',
    primary: ['catalog', 'api', 'audit', 'topic'],
  },
  r7: {
    kicker: '目录运营台',
    title: '让发布真正可发现、可申请、可授权。',
    subtitle: '字段口径裁决 / 挂接审核 / 供需对接 — 3 张收件箱在"维护数据供给"。',
    primary: ['inbox', 'catalog', 'topic', 'audit'],
  },
  r8: {
    kicker: '合规与减负治理',
    title: '守底线 — 重复要数、绕行采集、断链都进证据链。',
    subtitle: '减负指标 / 撤回审计 / 异议绕行 / 直达督查 — 不直接改业务事实，只形成整改建议。',
    primary: ['shield', 'audit', 'delivery'],
  },
  admin: {
    kicker: 'M0 实施监控',
    title: '客户验收日打开本页一次。',
    subtitle: '本页不开放给业务岗位；M0 状态由 customer_acceptance_up.sh CLI 跑出。',
    primary: [],
  },
};

PAGES.workbench = function () {
  const current = window.RUNTIME_WORKBENCH[window.STATE.role] || window.RUNTIME_WORKBENCH.r1;
  const metrics = window.RUNTIME_DASHBOARD.burdenMetrics || [];
  const requests = window.RUNTIME_REQUESTS || [];
  const deliveryTasks = window.RUNTIME_DELIVERY_TASKS || [];
  const primaryRequest = activeRequest();
  const primaryDelivery = activeDelivery();
  const role = window.STATE.role;
  const canAccess = roles => roles.includes(role);
  const heroCfg = ROLE_HERO[role] || ROLE_HERO.r1;
  // W6.1+W6.6: serviceEntries 加 iconKey 用 SVG，按角色 primary 重排序
  const allServiceEntries = [
    { key: 'search',   label: '找可复用数据', desc: '先查已有资源和专题包，避免重新要数。', href: '#/p2-discovery', iconKey: 'search', roles: ['r1', 'r2', 'r6', 'r7', 'r8'] },
    { key: 'apply',    label: '发起共享申请', desc: '把资源、用途、差异字段带入受控准入。', href: '#/p3-request-flow', iconKey: 'apply', roles: ['r1', 'r2', 'r3', 'r4', 'r5'] },
    { key: 'progress', label: '看申请进度', desc: '查看补件、审批、补录和汇总状态。', href: primaryRequest ? summaryRouteForRole(role, primaryRequest.id) : '#/p3-request-flow', iconKey: 'progress', roles: ['r1', 'r2', 'r3', 'r4', 'r5'] },
    { key: 'delivery', label: '看交付回执', desc: '跟踪交付、对账和回流候选。', href: primaryDelivery ? `#/p4-delivery-exchange/task/${primaryDelivery.id}` : '#/p4-delivery-exchange', iconKey: 'delivery', roles: ['r2', 'r5', 'r6', 'r7', 'r8'] },
    { key: 'audit',    label: '查审计证据', desc: '回放争议、告警、工单和责任链。', href: '#/p6-compliance-ops', iconKey: 'audit', roles: ['r2', 'r5', 'r6', 'r7', 'r8'] },
    { key: 'topic',    label: '进专题包', desc: '从一表通、营商环境等场景直接进入。', href: '#/p7-zones-pack', iconKey: 'topic', roles: ['r1', 'r2', 'r6', 'r7', 'r8'] },
    { key: 'inbox',    label: '收件箱：字段裁决/挂接审核', desc: 'R7 的字段口径裁决 + 资源挂接审核 + 供需对接收件箱。', href: '#/p5-provider', iconKey: 'inbox', roles: ['r7'] },
    { key: 'catalog',  label: '维护数据供给', desc: '反向编目 / 资源挂接 / 服务上架。', href: '#/p5-provider', iconKey: 'catalog', roles: ['r6', 'r7'] },
    { key: 'api',      label: 'API 服务化交付', desc: '把资源对外开放为受控 API。', href: '#/p5-provider/wizard/api-service', iconKey: 'api', roles: ['r6'] },
    { key: 'shield',   label: '减负指标 / 合规督查', desc: '减负结果、撤回审计、异议绕行、直达 / API 绕行抽查。', href: '#/p6-compliance-ops', iconKey: 'shield', roles: ['r8'] },
  ];
  // 按角色 primary 顺序排序；只显示当前角色 allowed 的
  const orderedEntries = heroCfg.primary
    .map(k => allServiceEntries.find(e => e.key === k))
    .filter(e => e && canAccess(e.roles));
  const serviceCards = orderedEntries.map(item => `
      <a href="${safeHashHref(item.href)}" class="service-entry">
        <span class="service-icon" aria-hidden="true">${WORKBENCH_ICONS[item.iconKey] || ''}</span>
        <strong>${escapeHtml(item.label)}</strong>
        <em>${escapeHtml(item.desc)}</em>
      </a>`).join('');
  const baseRows = [
    { section: '常用办理', title: '搜索业务或数据需求', desc: '输入“停车场信息”“泊位开放状态”等业务说法，先找可复用资源。', href: '#/p2-discovery', tag: '搜索优先', roles: ['r2', 'r6', 'r7', 'r8'] },
    { section: '常用办理', title: '查看共享申请进度', desc: primaryRequest ? `${primaryRequest.id} · ${requestStatusLabel(primaryRequest, role)}` : '暂无进行中的共享申请，可先从资源详情发起。', href: '#/p3-request-flow', tag: '受控准入', roles: ['r1', 'r2', 'r3', 'r4', 'r5'] },
    { section: '待我确认', title: current.todos?.[0]?.title || '查看今日待办', desc: current.todos?.[0]?.status || '按当前身份只显示需要你处理的事项。', href: current.todos?.[0]?.href || '#/p1-workbench', tag: '人工确认', roles: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'] },
    { section: '专题共享', title: '进入专题包', desc: '从高频主题进入资产、订阅和复用申请。', href: '#/p7-zones-pack', tag: '场景入口', roles: ['r1', 'r2', 'r6', 'r7', 'r8'] },
    { section: '交付与审计', title: '查看交付回执与审计证据', desc: primaryDelivery ? `${primaryDelivery.id} · ${deliveryStatusLabel(primaryDelivery, primaryRequest)}` : '交付、对账、回流和争议证据集中查看。', href: primaryDelivery ? `#/p4-delivery-exchange/task/${primaryDelivery.id}` : '#/p6-compliance-ops', tag: '证据可查', roles: ['r2', 'r5', 'r6', 'r7', 'r8'] },
  ];
  const serviceRows = baseRows.map(item => {
    const allowed = canAccess(item.roles);
    return `
      <a href="${allowed ? safeHashHref(item.href) : '#'}"
         class="service-row ${allowed ? '' : 'is-disabled'}"
         ${allowed ? '' : 'aria-disabled="true" onclick="event.preventDefault();window.UI.toast(\'当前岗位暂无该事项权限，请选择其他可办理事项\',\'info\')"'}>
        <span><strong>${escapeHtml(item.title)}</strong><em>${escapeHtml(item.section)} · ${escapeHtml(item.desc)}</em></span>
        <span class="service-row-tag">${escapeHtml(item.tag)}</span>
      </a>`;
  }).join('');
  // W6.1: 搜索框仅 R1 / R2 显示（其他角色主入口不是搜索）
  const showSearch = role === 'r1' || role === 'r2';
  const main = `
    <div class="service-home-hero page-hero">
      <div class="service-home-copy">
        <div class="page-kicker">${escapeHtml(heroCfg.kicker)}</div>
        <div class="page-hero-title">${escapeHtml(heroCfg.title)}</div>
        <div class="page-hero-subtitle">${escapeHtml(heroCfg.subtitle)}</div>
      </div>
      ${showSearch ? `
      <form class="service-search" role="search" onsubmit="window.ACTIONS.searchFromHome(event)">
        <label class="sr-only" for="home-service-q">搜索业务或数据需求</label>
        <input id="home-service-q" name="q" type="search" class="field-input" placeholder="搜索业务或数据需求，例如：停车场信息、泊位开放状态" autocomplete="off" />
        <button class="gov-btn gov-btn-primary" type="submit">搜索</button>
      </form>` : ''}
      <div class="service-home-assurance">
        <span>${roleLabel(role)}</span>
        <span>${humanConfirmPillText(role)}</span>
        <span>关键动作均保留人工确认和审计回执</span>
      </div>
    </div>

    <section class="panel">
      <div class="panel-body">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div class="panel-title">今天能办的共享服务</div>
            <div class="panel-subtitle">只展示当前岗位可办理的事项。</div>
          </div>
          <a href="#/p2-discovery" class="gov-btn gov-btn-secondary">查看全部资源</a>
        </div>
        <div class="service-entry-grid mt-4">${serviceCards}</div>
      </div>
    </section>

    ${r1ApiCredentialsAndDemandRegistration()}

    <section class="panel">
      <div class="panel-body">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div class="panel-title">继续办理中的事项</div>
            <div class="panel-subtitle">按阶段查看本岗位的下一步动作。</div>
          </div>
        </div>
        <div class="service-row-list mt-4">${serviceRows}</div>
      </div>
    </section>

    <div class="executive-chain panel">
      <div class="panel-body">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div class="panel-title">一条可追踪的办理链路</div>
            <div class="panel-subtitle">从发现资源到申请审批、基层补录、审核汇总、交付回流，状态和证据连续呈现。</div>
          </div>
          <span class="guardrail-pill">关键写动作由经办人确认</span>
        </div>
        <div class="chain-rail mt-5">
          <a href="#/p2-discovery"><span>1</span><strong>发现资源</strong><em>先找可复用数据</em></a>
          <a href="#/p3-request-flow"><span>2</span><strong>申请审批</strong><em>准入判断重复要数</em></a>
          <a href="${primaryRequest ? `#/p3-request-flow/request/${primaryRequest.id}` : '#/p3-request-flow'}"><span>3</span><strong>补差异</strong><em>基层只补现场变化</em></a>
          <a href="${primaryDelivery ? `#/p4-delivery-exchange/task/${primaryDelivery.id}` : '#/p4-delivery-exchange'}"><span>4</span><strong>看交付</strong><em>回执和回流候选</em></a>
          <a href="#/p6-compliance-ops"><span>5</span><strong>查证据</strong><em>审计回放和减负治理</em></a>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('今日待办', '只列出当前身份真正需要处理的事项。', infoList(current.todos))}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('办理建议', '根据证据提示排序和处置建议，最终动作仍由经办人确认。', `
          <div class="text-body leading-7 text-zw-ink">${escapeHtml(current.aiSummary.summary)}</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">${(current.aiSummary.basis || []).map(item => `• ${escapeHtml(item)}`).join('<br/>')}</div>
        `)}
        ${(role === 'r3' || role === 'r4')
          ? ''
          : panel('服务证据概览', '指标只作辅助，主路径仍从搜索和办理入口进入。', `
          ${statCards([
            { label: '目录资源', value: window.RUNTIME_DISCOVERY.resources.length, note: '可先复用的数据资源', href: '#/p2-discovery' },
            { label: '共享申请', value: requests.length, note: primaryRequest ? requestStatusLabel(primaryRequest, role) : '暂无申请', href: '#/p3-request-flow' },
            { label: '交付任务', value: deliveryTasks.length, note: primaryDelivery ? deliveryStatusLabel(primaryDelivery, primaryRequest) : '暂无任务', href: '#/p4-delivery-exchange' },
            { label: '治理告警', value: window.RUNTIME_ALERTS.length, note: metrics[0] ? `${metrics[0].label} ${metrics[0].value}` : '暂无异常', href: '#/p6-compliance-ops' },
          ])}
        `)}
      </aside>
    </div>
  `;
  return shell('p1', main);
};

function r1ApiCredentialsAndDemandRegistration() {
  // W4.5: R1 视角下显示"我的 API 凭据"和"需求登记前置"两个入口
  if (!window.STATE || window.STATE.role !== 'r1') return '';
  const apiDeliveries = (window.RUNTIME_DELIVERY_TASKS || []).filter(t => t.channel === 'api' || (t.channel || '').includes('api'));
  return `
    <div class="grid grid-cols-2 gap-5 mt-5">
      ${panel(`我的 API 凭据 (${apiDeliveries.length} 条)`, '已审批的 API 交付通道；凭据引用 + 调用计数 + 错误样本 projection', `
        ${apiDeliveries.length ? `
          <table class="gov-table text-body-sm">
            <thead><tr><th>delivery_code</th><th>application</th><th>state</th><th>更新时间</th></tr></thead>
            <tbody>${apiDeliveries.slice(0, 10).map(t => `<tr><td><code>${escapeHtml(t.id || '')}</code></td><td>${escapeHtml(t.requestId || '—')}</td><td>${statusPill(t.status || 'pending')}</td><td class="row-meta">${escapeHtml(t.updatedAt || '')}</td></tr>`).join('')}</tbody>
          </table>
          <div class="row-meta text-body-sm mt-2">凭据 / IP 白名单 / 限流额度详情请进 #/p4-delivery-exchange/task/&lt;delivery_code&gt; 查看。调用计数与错误样本走 ops.service.invocation.query。</div>
        ` : '<div class="row-meta">尚无 API 交付通道；通过申请审批后会在此显示。</div>'}
      `)}
      ${panel('需求登记前置', '不确定该用哪份目录？先以「需求登记」前置：写明用途/字段/时间窗，R7 反查复用', `
        <div class="row-meta text-body-sm mb-3">复用判断成功 → 直接申请；不可复用 → R7 派 R5 切片任务。</div>
        <div class="flex flex-col gap-2">
          <input id="r1-demand-purpose" class="gov-input" placeholder="用途 (e.g. 民生保障专题统计)"/>
          <input id="r1-demand-fields" class="gov-input" placeholder="字段口径 (e.g. 停车场名称, 区域, 状态, 更新时间)"/>
          <input id="r1-demand-window" class="gov-input" placeholder="时间窗 (e.g. 2026-01 ~ 2026-06)"/>
          <button onclick="window.ACTIONS.submitDemandRegistration()" class="gov-btn gov-btn-primary">提交需求登记</button>
        </div>
        <div class="row-meta text-body-sm mt-2">提交后调用 require.intent.submit；可在 #/p3-request-flow 跟踪复用判断结果。</div>
      `)}
    </div>
  `;
}

PAGES.login = function () {
  const cfg = window.ZW_WEBUI && window.ZW_WEBUI.iafIam;
  const iafConfigured = !!(cfg && cfg.configured);
  const configuredBody = `
        <div class="login-gate-field">
          <label for="login-gate-iam-readonly">认证渠道</label>
          <div id="login-gate-iam-readonly" class="login-gate-iam-box" tabindex="0" role="group" aria-label="认证渠道说明">
            请使用主管部门统一身份账号登录，账号口令与验证码均在统一身份页面完成。
          </div>
        </div>
        <div class="login-gate-actions">
          <button type="button" class="gov-btn gov-btn-primary"
            onclick="window.ACTIONS.startIafLogin(event)">打开统一身份登录页</button>
          <a href="#/p1-workbench" class="gov-btn gov-btn-secondary">返回数据共享工作台</a>
        </div>
        <p class="login-gate-footnote">登录成功后将自动返回本系统。</p>`;
  const unconfiguredBody = `
        <div class="login-gate-field">
          <label>认证渠道</label>
          <div class="login-gate-iam-box" role="alert">
            当前统一身份服务暂不可用，请联系系统管理员确认登录服务配置后再试。
          </div>
        </div>
        <div class="login-gate-actions">
          <a href="#/p1-workbench" class="gov-btn gov-btn-primary">返回数据共享工作台</a>
        </div>
        <p class="login-gate-footnote">本系统不存储账号口令，请通过统一身份页面完成认证。</p>`;
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '统一身份登录' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">账号与安全</div>
          <div class="page-hero-title">登录本应用前先完成统一身份核验。</div>
          <div class="page-hero-subtitle">本系统不托管账号口令，请在统一身份页面完成认证。</div>
        </div>
      </div>
    </div>
    <div class="login-gate-wrap">
      <section class="login-gate-card" aria-labelledby="login-gate-heading">
        <header class="login-gate-card-header">
          <h2 id="login-gate-heading" class="login-gate-card-title">统一身份登录</h2>
          <p class="login-gate-card-sub">${iafConfigured
            ? '点击下方按钮跳转至统一身份登录页。'
            : '当前统一身份服务暂不可用，请联系系统管理员。'}
          </p>
        </header>
        <div class="login-gate-card-body">
          ${iafConfigured ? configuredBody : unconfiguredBody}
        </div>
      </section>
    </div>`;
  return shell('p1', main);
};

PAGES.discovery = function () {
  const runtime = window.RUNTIME_DISCOVERY || {};
  const ai = {
    summary: '数据加载中...',
    missingQuestions: [],
    nextActions: [],
    evidence: [],
    ...(runtime.aiCopilot || {}),
  };
  if (!runtime.resources) {
    return shell('p2', `
      ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '数据资源发现' }])}
      <div class="state-card">
        <div class="page-kicker">数据资源发现</div>
        <div class="page-hero-title">正在加载资源清单…</div>
        <p class="row-meta mt-2">从已沉淀的目录、资源和专题包中检索复用候选。</p>
      </div>`);
  }
  const query = escapeHtml(window.STATE.discoveryQuery || '');
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '数据资源发现' }])}
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
        <div class="panel-title">搜索可复用数据</div>
        <div class="panel-subtitle">输入业务说法，先看已有资源能不能直接复用，再决定是否发起共享申请。</div>
        <form onsubmit="window.ACTIONS.setDiscoveryQuery(event)" class="flex gap-3 mt-4">
          <input id="discovery-q" type="search" value="${query}" class="flex-1 px-4 py-3 rounded-lg border-default text-body bg-white field-input" placeholder="例如：停车场信息、泊位开放状态" />
          <button class="gov-btn gov-btn-primary">搜索</button>
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
                      <p class="text-body mt-3 leading-7">${item.desc || ''}</p>
                      ${Array.isArray(item.explain) && item.explain.length
                        ? `<div class="mt-4 text-body-sm text-zw-mute leading-7" data-ai-surface="resource-reason">推荐理由：${item.explain.join('；')}</div>`
                        : ''}
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-body-sm text-zw-mute">相关度</div>
                      <div class="text-display text-zw-primary mt-1">${item.score != null ? item.score : '—'}</div>
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-body-sm text-zw-mute">下一步</div>
                      <div class="text-body text-zw-ink leading-7 mt-1">${(Array.isArray(item.nextHints) && item.nextHints[0]) || '查看详情'}</div>
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

  const empty = data.total === 0 ? `<div class="text-body text-zw-mute py-6 text-center">当前筛选下暂未找到可办理目录。可以切换状态或类型，也可以回到资源发现页重新搜索业务需求。</div>` : '';

  const main = `
    <div class="page-hero">
      <div class="page-kicker">数据资源发现 · 目录检索</div>
      <h1 class="page-hero-title">查看可复用目录</h1>
      <div class="page-hero-subtitle">按状态和类型查看已纳入共享服务的目录，命中后可进入资源详情并发起受控申请。当前 ${data.total || 0} 条命中（第 ${data.page || 1} / ${totalPages} 页）。</div>
    </div>

    <div class="panel mt-4">
      <div class="panel-body">
        <div class="panel-title">选择目录范围</div>
        <div class="panel-subtitle">默认看已经可用的目录；如需供给侧维护，再切换到草稿、审核中或待发布目录。</div>
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
        <div class="panel-title">可办理目录</div>
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
  const fields = item.catalogFields && item.catalogFields.length ? item.catalogFields.map(field => field.title) : (item.fields || []);
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

    ${renderInlineSummary(`${item.name} 已在共享目录中命中。先核对字段口径、共享条件和 schema 证据，再只申请本次确需字段；未绑定字段作为缺口说明。`, item.nextHints)}

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
    <div class="mt-5">
      ${renderFieldBindingEvidence(item)}
    </div>
    ${renderResourceEvidencePanels(item)}
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
  // W7.1: P3 hero 按角色定制 — R3/R4 只看自己的任务，不再读 R1/R2 的全链路口径
  const heroCfg = (
    role === 'r3' ? { kicker: '镇街补差任务', title: '我的差异补录任务', subtitle: '只处理标红的差异字段；预填值由上游目录与资源带出，异常字段一键回传。' } :
    role === 'r4' ? { kicker: '村社区核实任务', title: '我的现场核实任务', subtitle: '看任务卡 → 补现场变化 → 提交。看不懂的字段一键回传上级。' } :
    role === 'r2' ? { kicker: '审批承接 · 待审申请', title: '把住重复要数阀门 — 审批待办', subtitle: '看证据链做准入判定；分级授权策略 / API 边界审 / 撤回处置都在 reviewDetail 内联。' } :
    role === 'r5' ? { kicker: '审核汇总 · 异常确认', title: '盯异常、确认自动汇总', subtitle: '不再线下拼表 — 系统已汇总好的结果在这里集中处理异常项、口径冲突、质量证据。' } :
                    { kicker: '共享申请与审批', title: '共享申请、准入审批、基层补录在一条链上办理。', subtitle: '发起人、审批承接、镇街社区和汇总人员看到同一份状态，只在自己负责的环节执行人工确认。' }
  );
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: heroCfg.kicker }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${escapeHtml(heroCfg.kicker)}</div>
          <div class="page-hero-title">${escapeHtml(heroCfg.title)}</div>
          <div class="page-hero-subtitle">${escapeHtml(heroCfg.subtitle)}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
      ${isGrassroots ? '' : `<div class="mt-4">${stepBar(['发现模板', '复用判断', '受控准入', '预填补录', '审核汇总', '回流共享'], requestStepIndex(request, role))}</div>`}
    </div>

    ${renderInlineSummary(draft.summary, ['查看已预填字段', '查看差异补录', '查看自动汇总预估'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${isGrassroots ? panel('我的差异补录字段', '只补现场变化字段，不重填整表', `
          <div class="text-body leading-7 text-zw-ink">${request.diffFields.map(item => {
            const label = escapeHtml(item.label);
            const reason = escapeHtml(item.reason);
            const owner = escapeHtml(ownerForViewer(item.owner, role));
            return owner ? `• <strong>${label}</strong> — ${reason}（${owner}）` : `• <strong>${label}</strong> — ${reason}`;
          }).join('<br/>')}</div>
          <div class="mt-3 row-meta text-body-sm">基础字段已由共享资源带出，你只需核对差异。完成后会进入下一棒做汇总确认。</div>
          <div class="mt-4 flex gap-3 flex-wrap">
            ${requestActionBar(request, role)}
          </div>
        `) : panel('标准复用申请', '按模板覆盖率、差异字段和责任说明生成申请材料', `
          <div class="grid grid-cols-2 gap-4 text-body" data-ai-surface="request-inline-ai">
            ${renderFieldState('复用模板', request.resourceName, '已识别', '作为涉企默认基础对象')}
            ${renderFieldState('模板覆盖率', request.templateCoverage, '已识别', '多数基础字段可自动带出')}
            <div class="col-span-2">${renderFieldState('业务目标', request.purpose, '已识别', '先复用模板，再补现场差异')}</div>
            <div class="col-span-2">${renderFieldState('差异字段责任说明', '经营状态 / 走访时间 / 现场备注', request.status === 'need-fix' ? '待补正' : '待确认', '需明确由镇街 / 社区补录，审核汇总人员只处理异常项')}</div>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-4">
            ${panel('已预填字段', '这些字段已由共享资源自动带出', `<div class="text-body leading-7 text-zw-mute">${request.prefilledFields.map(item => `• ${item.label}：${item.value}（${item.source}）`).join('<br/>')}</div>`)}
            ${panel('差异补录字段', '现场变化字段进入基层补录', `<div class="text-body leading-7 text-zw-mute">${request.diffFields.map(item => {
              const owner = escapeHtml(ownerForViewer(item.owner, role));
              return owner ? `• ${escapeHtml(item.label)}：${escapeHtml(item.reason)}（${owner}）` : `• ${escapeHtml(item.label)}：${escapeHtml(item.reason)}`;
            }).join('<br/>')}</div>`)}
          </div>
          <div class="mt-4 text-body leading-7 text-zw-ink" data-ai-surface="request-summary-inline">可审摘要：${draft.summary}</div>
          <div class="mt-5 flex gap-3 flex-wrap">
            ${requestActionBar(request, role)}
          </div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel(
          isGrassroots ? '我的补录提示' : '准入 / 汇总侧栏',
          (
            role === 'r3' ? '镇街只核对已带出字段并补齐自己负责的现场差异。' :
            role === 'r4' ? '村社区只核实现场变化字段，看不懂或无法核实就异常回传。' :
            '审批承接人员处理准入，审核汇总人员处理异常项与汇总结果。'
          ), `
          <div class="text-body leading-7 text-zw-ink">${
            role === 'r3' ? '本任务已自动带出企业基础字段，你只需核对经营状态、最近走访时间和现场备注。' :
            role === 'r4' ? '本任务只让你核实当前现场状态，不要求接触整张表。' :
            isReviewer ? '当前重点是确认差异字段、异常项和自动汇总结果。' :
            draft.risk
          }</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">${isReviewer ? request.summaryResult.note : '建议优先复用模板，并确认差异字段和回流要求。'}</div>
        `)}
        ${panel('当前链路队列', isGrassroots ? '只看分给我的差异补录任务' : '查看各申请当前进度和可处理入口', `
          ${isGrassroots ? `
            <div class="row-meta text-body-sm mb-2">
              当前身份：${escapeHtml(roleLabel(role))} · 只显示状态为"补录中 / 退回补正"的任务卡片
              <a href="#" onclick="event.preventDefault();window.ACTIONS.openGrassrootsExceptionForm()" class="ml-2 text-zw-link">异常回传</a>
            </div>
          ` : ''}
          <div class="gov-list text-body">
            ${(isGrassroots
                ? window.RUNTIME_REQUESTS.filter(req => req.status === 'supplementing' || req.status === 'need-fix')
                : window.RUNTIME_REQUESTS
              ).map(item => `
              <a href="${summaryRouteForRole(window.STATE.role, item.id)}" class="gov-list-row card-hover">
                <div><div class="row-title">${escapeHtml(item.resourceName || '未命名共享申请')}</div><div class="row-meta mt-2 text-body-sm text-zw-mute">${escapeHtml(formatIdShort(item.id, '申请'))}</div></div>
                ${statusPill(requestStatusLabel(item, role))}
              </a>`).join('') || (isGrassroots ? '<div class="text-body-sm text-zw-mute py-3">当前无需要你补录或补正的任务。</div>' : '')}
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
  const diffNote = field => {
    const owner = ownerForViewer(field.owner, role);
    const tail = item.status === 'summary-pending' || item.status === 'completed' ? ` · ${field.state || '已补录'}` : '';
    return owner ? `${field.reason} · ${owner}${tail}` : `${field.reason}${tail}`;
  };
  const grassrootsCrumb = role === 'r3' ? '镇街补差任务' : '村社区核实任务';
  const grassrootsTitle = role === 'r3' ? '我的差异补录任务' : '我的现场核实任务';
  const grassrootsSubtitle = role === 'r3'
    ? '只看分给镇街的差异字段，基础信息已经预填。'
    : '只核实现场变化字段，看不懂或无法核实就异常回传。';
  const main = isGrassroots ? `
    ${crumbs([{ label: '我的任务', href: '#/p3-request-flow' }, { label: grassrootsCrumb }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${grassrootsCrumb}</div>
          <div class="page-hero-title">${grassrootsTitle} · ${item.id}</div>
          <div class="page-hero-subtitle">${grassrootsSubtitle}</div>
        </div>
        ${statusPill(requestStatusLabel(item, role))}
      </div>
    </div>

    ${renderInlineSummary('系统已带出企业基础信息，只需要补齐经营状态、最近走访时间和现场备注。', ['核对预填值', '补差异字段', '异常回传'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('我的待补字段', '只补真正缺失、动态、现场性强的字段', `
          <div class="grid grid-cols-1 gap-3">${item.diffFields
            // B3 — R3 only sees fields they own; R4 only sees fields they own.
            // Fields tagged for the *other* grassroots role get hidden so we
            // don't leak the cross-role breakdown onto the field card.
            .filter(field => {
              const o = String(field.owner || '').toUpperCase();
              if (role === 'r3' && /R4(?!\/)/i.test(o) && !/R3/.test(o)) return false;
              if (role === 'r4' && /R3(?!\/)/i.test(o) && !/R4/.test(o)) return false;
              return true;
            })
            .map(field => renderFieldState(field.label, field.value, diffState, diffNote(field))).join('')}</div>
          <div class="mt-4 flex gap-3 flex-wrap">
            ${requestActionBar(item, role)}
            <button onclick="window.ACTIONS.openGrassrootsExceptionForm('${item.id}')" class="gov-btn gov-btn-secondary">异常回传</button>
          </div>
        `)}
        ${panel('已自动带出，不用重填', '来源透明，现场人员只核对不重复录入', `
          <div class="grid grid-cols-2 gap-3">${item.prefilledFields.map(field => renderFieldState(field.label, field.value, field.state, field.source)).join('')}</div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel('办理提醒', '先补差异，再提交；异常不要线下沟通', `
          <div class="text-body leading-7 text-zw-ink">${role === 'r3' ? '镇街只处理分派给自己的补差任务。无法确认的字段回传上级汇总，不把问题压给社区。' : '村社区只核实现场事实。字段口径不理解、现场无法核实或任务范围不对时，直接回传异常。'}</div>
          <div class="mt-4 text-body-sm text-zw-mute leading-7">下一步：${escapeHtml(item.aiStatus.nextAction || '提交后进入 R5 汇总确认。')}</div>
        `)}
        ${panel('回执与审计', '提交和异常回传都会留下回执', `
          <div class="flex flex-wrap gap-2 text-body">
            ${evidenceChip('审计编号', item.auditId)}
            ${evidenceChip('可信存证', item.chainAnchor)}
          </div>
          <div class="text-body-sm text-zw-mute mt-2">点击芯片复制完整证据 ID。</div>
        `)}
        ${panel('回流说明', '查看补录结果如何进入后续复用', `
          <div class="text-body leading-7 text-zw-ink">${item.returnFlow.map(line => `• ${line}`).join('<br/>')}</div>
        `)}
      </aside>
    </div>
  ` : `
    ${crumbs([{ label: '共享申请与审批', href: '#/p3-request-flow' }, { label: escapeHtml(formatIdShort(item.id, '申请')) }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${escapeHtml(formatIdShort(item.id, '申请'))}</div>
          <div class="page-hero-title">${escapeHtml(item.resourceName || '共享申请详情')}</div>
          <div class="page-hero-subtitle">${escapeHtml(item.applicantDept || '')}</div>
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
          <div class="flex flex-wrap gap-2 text-body">
            ${evidenceChip('审计编号', item.auditId)}
            ${evidenceChip('可信存证', item.chainAnchor)}
          </div>
          <div class="text-body-sm text-zw-mute mt-2">点击芯片复制完整证据 ID。</div>
          ${(item.aiStatus && Array.isArray(item.aiStatus.evidence) && item.aiStatus.evidence.length)
            ? `<div class="text-zw-mute text-body-sm mt-3 leading-7">依据：${item.aiStatus.evidence.map(e => escapeHtml(e)).join('；')}</div>`
            : ''}
        `)}
        ${panel('回流说明', '查看补录结果如何进入后续复用', `
          <div class="text-body leading-7 text-zw-ink">${item.returnFlow.map(line => `• ${line}`).join('<br/>')}</div>
        `)}
        ${panel('当前链路动作', '申请方当前查看状态、证据和可处理动作。', `
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
  const reasonItems = asList(approval.reason);
  const riskItems = asList(approval.risk);
  const exceptionItems = asList(approval.exceptionItems);
  const confidence = Number.isFinite(Number(approval.confidence)) ? Number(approval.confidence) : 0;
  const statusLabel = requestStatusLabel(request, window.STATE.role);
  const materials = approval.applicationMaterials || request.applicationMaterials || {};
  const requestedItems = asList(materials.requestedItems || request.requestedItems);
  const fieldEvidence = approval.fieldEvidence || {};
  const fieldSummary = fieldEvidence.fieldBindingSummary || request.fieldBindingSummary || {};
  const fieldBindings = asList(fieldEvidence.fieldBindings || request.fieldBindings);
  const sensitivePolicy = fieldEvidence.sensitivePolicy || request.sensitivePolicy || {};
  const resourceAssets = asList(fieldEvidence.resourceAssets || request.resourceAssets);
  const history = approval.historicalContext || request.historicalContext || {};
  const grantEvidence = approval.grantEvidence || {};
  const grant = grantEvidence.accessGrant || {};
  const recommendation = approval.recommendedDecision || {};
  const quality = approval.qualityEvidence || request.qualityEvidence || {};
  const legacyMappings = asList(approval.legacyMappings || request.legacyMappings).slice(0, 8);
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
    ${crumbs([{ label: '共享申请与审批', href: '#/p3-request-flow' }, { label: window.STATE.role === 'r5' ? '汇总确认详情' : '审批准入详情' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${window.STATE.role === 'r5' ? '审核汇总 · 异常确认' : (window.STATE.role === 'r2' ? '审批承接 · 准入判定' : '审核 / 汇总详情')}</div>
          <div class="page-hero-title">${window.STATE.role === 'r5' ? '汇总确认' : '审批准入'} · ${request.id}</div>
          <div class="page-hero-subtitle">${window.STATE.role === 'r5' ? '盯异常、确认自动汇总；本页只处理汇总阶段的异常项。' : window.STATE.role === 'r2' ? '看证据链做准入判定；分级授权策略 / API 边界审 / 撤回授权悬空处置都在本页。' : '审批承接人员处理准入，审核汇总人员处理异常项与自动汇总。'}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(`${approval.suggestion}。${approval.autoSummary}`, ['查看异常项', '查看自动汇总结果', '查看回流要求'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('申请材料与复用范围', '审批承接人员先核对用途、目录、字段、频次和最小必要范围', `
          <table class="gov-table">
            <tbody>
              <tr><td>复用对象</td><td>${businessValue(request.resourceName)}</td></tr>
              <tr><td>目录编号</td><td>${businessValue(materials.catalogCode)}</td></tr>
              <tr><td>申请用途</td><td>${businessValue(materials.purpose || request.purpose)}</td></tr>
              <tr><td>使用范围</td><td>${businessValue(materials.scope || request.range)}</td></tr>
              <tr><td>申请频次</td><td>${businessValue(materials.frequency ? `${materials.frequency.times || '—'} 次 / ${materials.frequency.mostTimes || '—'} 次 · ${materials.frequency.timeWindow || '—'}` : request.timeWindow)}</td></tr>
              <tr><td>申请字段</td><td>${requestedItems.map(item => `${businessValue(item.title)}${item.sensitive_level ? `（敏感级别 ${businessValue(item.sensitive_level)}）` : ''}`).join(' / ') || '—'}</td></tr>
              <tr><td>最小必要</td><td>${materials.minimal ? '已按本次确需字段收敛' : '需补充收敛说明'}</td></tr>
            </tbody>
          </table>
        `)}
        ${panel('准入证据链', '把目录、资源状态、字段绑定、敏感策略和质量投影放在同一处判断', `
          <div data-ai-surface="r2-approval-evidence-chain" class="space-y-4 text-body leading-7">
            <div><strong>字段绑定</strong><div class="mt-2 text-zw-mute">诊断：${businessValue(fieldSummary.diagnosis)}；已绑定 ${businessValue(fieldSummary.active ?? fieldSummary.total ?? 0)} 项。${fieldBindings.map(item => `${businessValue(item.catalog_item_title || item.catalog_item_code)} → ${businessValue(item.explain && item.explain.source_column)}`).join('；') || '暂无字段绑定证据'}</div></div>
            <div><strong>敏感策略</strong><div class="mt-2 text-zw-mute">${businessValue(sensitivePolicy.display || '查询与导出侧按字段敏感级别脱敏。')} 字段敏感级别：${businessList(sensitivePolicy.fieldSensitiveLevels, '未标注')}</div></div>
            <div><strong>资源状态</strong><div class="mt-2 text-zw-mute">${resourceAssets.map(asset => `${businessValue(asset.title || asset.resource_code)}：${businessValue(asset.lifecycle_status)}`).join('；') || businessValue(request.reuseCandidate && request.reuseCandidate.resourceStatus)}</div></div>
            <div><strong>历史与重复线索</strong><div class="mt-2 text-zw-mute">${businessValue(history.duplicateConclusion || history.message)}；历史申请 ${businessValue(history.relatedApplicationCount ?? 0)} 条，在途重复 ${businessValue(history.inFlightDuplicateCount ?? 0)} 条。</div></div>
            <div><strong>质量投影</strong><div class="mt-2 text-zw-mute">${businessValue(quality.summary)}；状态 ${businessValue(quality.status)}。</div></div>
          </div>
        `)}
        ${panel(isSummaryStage ? '自动汇总结果与异常项' : '建议决策与授权边界', isSummaryStage ? '审核汇总人员确认异常项和自动汇总结果。' : '审批承接人员基于证据选择通过复用、退回缩小范围、驳回重复或转口径确认。', `
          <div data-ai-surface="review-summary" class="space-y-4 text-body leading-7">
            <div><strong>${isSummaryStage ? '自动汇总结果' : '建议决策'}</strong><div class="mt-2 text-zw-mute">${businessValue(recommendation.primary || request.summaryResult.note)}；可选动作：${businessList(recommendation.alternatives)}</div></div>
            <div><strong>授权边界</strong><div class="mt-2 text-zw-mute">状态：${businessValue(grantEvidence.state)}；资源类型：${businessValue(grant.res_type || (recommendation.grantBoundary || {}).res_type)}；授权期：${businessValue(grant.limit_day || (recommendation.grantBoundary || {}).limit_day)} 天；续期：${businessValue(recommendation.renewalBoundary)}</div></div>
            <div><strong>异常项</strong><div class="mt-2 text-zw-mute">${exceptionItems.map(item => `• ${escapeHtml(item)}`).join('<br/>') || '—'}</div></div>
          </div>
        `)}
        ${panel('旧平台回指与审计来源', '用于客户现场核验：申请、审批过程和授权都能回指真实旧平台对象', `
          <div class="gov-list">
            ${legacyMappings.map(item => `<div class="gov-list-row"><div><div class="row-title">${businessValue(item.legacy_object_type)} → ${businessValue(item.canonical_type)}</div><div class="row-meta mt-2">${businessValue(item.legacy_object_ref)} · ${businessValue(item.mapping_status)}</div></div>${statusPill(item.mapping_status || 'mapped')}</div>`).join('') || '<div class="text-body text-zw-mute py-4">暂无旧平台回指。</div>'}
          </div>
        `)}
        ${renderDraftCard('审批 / 汇总意见草稿', [approval.draftNote], '草稿只帮助你更快进入结构化决策，不会替你写入最终结果。')}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('依据与风险', '动作前先看建议依据、风险和影响预估', `
          <div data-ai-surface="approval-inline-ai" class="space-y-4 text-body leading-7">
            <div><strong>建议依据</strong><div class="mt-2 text-zw-mute">${reasonItems.map(item => `• ${escapeHtml(item)}`).join('<br/>') || '—'}</div></div>
            <div><strong>风险提示</strong><div class="mt-2 text-zw-mute">${riskItems.map(item => `• ${escapeHtml(item)}`).join('<br/>') || '—'}</div></div>
            <div><strong>影响预估</strong><div class="mt-2 text-zw-mute">${businessValue(approval.impact)}</div></div>
            <div><strong>反事实提示</strong><div class="mt-2 text-zw-mute">${businessValue(approval.counterfactual)}</div></div>
            <div><span class="confidence-chip">置信度 ${Math.round(confidence * 100)}%</span></div>
          </div>
        `)}
      </aside>
    </div>
    ${r2GradeAuthorizationStrategyForm(request)}
    ${r5SummaryWithdrawAction(request)}
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

function r2GradeAuthorizationStrategyForm(request) {
  // W4.1: 仅当 R2 在 pending 阶段时显示分级授权策略表单
  if (!window.STATE || window.STATE.role !== 'r2') return '';
  if (!request || request.status !== 'pending') return '';
  const grant = (request.recommendedDecision && request.recommendedDecision.grantBoundary) || {};
  return panel('分级授权策略 (R2)', '决定授权档位、字段脱敏粒度、频次上限、有效期、是否级联。R7 只实施可见组织，不替 R2 决定档位。', `
    <div class="grid grid-cols-3 gap-3 text-body-sm">
      <div>
        <label class="row-meta">档位</label>
        <select id="r2-grade" class="gov-input mt-1">
          <option value="standard">标准（按目录默认）</option>
          <option value="strict">收紧（仅特定组织）</option>
          <option value="relaxed">放宽（含级联）</option>
        </select>
      </div>
      <div>
        <label class="row-meta">字段脱敏档位</label>
        <select id="r2-mask" class="gov-input mt-1">
          <option value="full">完全脱敏</option>
          <option value="partial" selected>部分脱敏（保留首尾）</option>
          <option value="none">不脱敏（仅向 sd-default 信任组织）</option>
        </select>
      </div>
      <div>
        <label class="row-meta">频次上限（次/天）</label>
        <input id="r2-freq" class="gov-input mt-1" type="number" placeholder="如 200" />
      </div>
      <div>
        <label class="row-meta">有效期（天）</label>
        <input id="r2-limitday" class="gov-input mt-1" type="number" placeholder="${escapeHtml(String(grant.limit_day || 90))}" />
      </div>
      <div class="flex items-end">
        <label class="row-meta flex items-center gap-2">
          <input id="r2-cascade" type="checkbox"/> 允许级联授权
        </label>
      </div>
    </div>
    <div class="text-body-sm text-zw-mute mt-3">通过"通过并下发补录"时，此策略会随 decision payload 一并审计；R7 在收件箱按这一档实施可见组织。</div>
  `);
}

function r5SummaryWithdrawAction(request) {
  // W4.4: 仅当 R5 看到已 completed 的请求 — 允许触发汇总撤回
  if (!window.STATE || window.STATE.role !== 'r5') return '';
  if (!request || request.status !== 'completed') return '';
  return panel('汇总撤回 (R5)', '汇总后发现口径错配时，撤回本次汇总并保留影响范围。', `
    <div class="text-body-sm text-zw-mute mb-3">撤回会写一次 summary.confirm 反向决策事件 + 影响范围摘要；不删除原始补录数据。</div>
    <div class="flex gap-3 items-center">
      <input id="r5-withdraw-reason" class="gov-input flex-1" placeholder="撤回原因 (e.g. 字段口径与目录模板冲突)" />
      <button onclick="window.ACTIONS.withdrawSummary('${request.id}')" class="gov-btn gov-btn-warn">撤回汇总</button>
    </div>
  `);
}

PAGES.deliveryExchange = function () {
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '交付交换与回流' }])}
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
                  <div class="flex items-center gap-2"><div class="panel-title">${escapeHtml(task.name || '交付任务')}</div>${statusPill(statusLabel)}</div>
                  <div class="row-meta mt-2">${escapeHtml(formatIdShort(task.id, '任务'))} · ${escapeHtml(task.channel || '—')} · ${escapeHtml(task.owner || '—')}</div>
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
  const ai = task.aiSummary;
  const statusLabel = deliveryStatusLabel(task, request);
  const backflowKey = backflowStatusKey(task.backflow.status);
  const requestCompleted = request ? request.status === 'completed' : task.status === 'completed' || task.summaryConfirmed === true;
  const canConfirmBackflow = requestCompleted && task.receiptStatus === 'reconciled' && backflowKey !== 'confirmed';
  const materials = task.applicationMaterials || (request && request.applicationMaterials) || {};
  const frequency = materials.frequency || {};
  const grant = task.accessGrantSnapshot || {};
  const grantBoundary = task.grantBoundary || {};
  const supplementBoundary = task.supplementBoundary || {};
  const nonGrantBoundary = task.nonGrantBoundary || {};
  const activeBoundary = Object.keys(grantBoundary).length ? grantBoundary : supplementBoundary;
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
        ${request ? panel('关联申请快照', '供给与回流角色只看必要申请信息，不要求拥有审批详情权限', `
          <table class="gov-table">
            <tbody>
              <tr><td>关联申请</td><td>${escapeHtml(formatIdShort(request.id, '申请'))}</td></tr>
              <tr><td>复用对象</td><td>${escapeHtml(request.resourceName || '—')}</td></tr>
              <tr><td>申请单位</td><td>${escapeHtml(request.applicantDept || '—')}</td></tr>
              <tr><td>申请状态</td><td>${requestStatusLabel(request, window.STATE.role)}</td></tr>
              <tr><td>审计编号</td><td>${evidenceChip('审计', request.auditId)}</td></tr>
            </tbody>
          </table>
        `) : panel('关联申请快照', '交付任务可独立展示，不因申请投影缺失击穿详情页', `
          <div class="text-body text-zw-mute leading-7">关联申请 ${task.requestId} 暂未同步到当前视图，当前仍按交付任务展示时间线、回执和回流候选。</div>
        `)}
        ${panel('授权 / 续期边界回放', '回放审批通过后的字段范围、敏感级别、访问频次、完成时限和续期真实来源', `
          <div data-ai-surface="delivery-authorization-boundary" class="grid grid-cols-2 gap-4 text-body leading-7">
            <div><strong>字段范围</strong><div class="mt-2 text-zw-mute">${businessList(activeBoundary.field_scope || materials.requestedItems?.map(item => item.title), '—')}</div></div>
            <div><strong>敏感级别</strong><div class="mt-2 text-zw-mute">${businessList(activeBoundary.sensitive_levels || task.r2Review?.evidence?.sensitive_levels, '未标注')}</div></div>
            <div><strong>访问频次</strong><div class="mt-2 text-zw-mute">${businessValue((activeBoundary.frequency || frequency).times)} 次 / ${businessValue((activeBoundary.frequency || frequency).mostTimes)} 次 · ${businessValue((activeBoundary.frequency || frequency).timeWindow)}</div></div>
            <div><strong>完成时限</strong><div class="mt-2 text-zw-mute">授权 ${businessValue(activeBoundary.limit_day || grant.limit_day)} 天；资源类型 ${businessValue(grant.res_type || activeBoundary.access_grant_snapshot?.res_type)}</div></div>
            <div class="col-span-2"><strong>access_grant_snapshot</strong><div class="mt-2 text-zw-mute">状态 ${businessValue(grant.status)}；apply_status ${businessValue(grant.apply_status)}；来源 ${businessValue(activeBoundary.source || task.r2Review?.evidence?.access_grant_source)}</div></div>
            <div class="col-span-2"><strong>续期边界</strong><div class="mt-2 text-zw-mute">${businessValue(task.renewalBoundary || task.authorizationBoundary?.renewalPolicy)}；真实续期行 ${businessValue(task.authorizationBoundary?.renewalSourceRows ?? 0)} 条。</div></div>
            <div class="col-span-2"><strong>非通过处理</strong><div class="mt-2 text-zw-mute">${nonGrantBoundary.no_new_grant ? `不生成新授权：${businessValue(nonGrantBoundary.mode)}` : '通过类决策按既有授权或补录边界继续。'}</div></div>
          </div>
        `)}
        ${panel('交付回执', '查看交付结果、回执编号和对账状态', `
          <div class="gov-list text-body">
            ${(task.receipts || []).map(receipt => `<div class="gov-list-row"><div><div class="row-title">${receipt.receiptNo || '交付回执'}</div><div class="row-meta mt-2">${receipt.receiptType || 'receipt'} · ${receipt.receiptStatus || '待对账'}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">${receipt.payload ? Object.entries(receipt.payload).map(([key, value]) => `${key}：${value}`).join('；') : '暂无回执明细'}</div></div></div>`).join('') || `<div class="gov-list-row"><div><div class="row-title">${task.receiptNo || '待生成回执'}</div><div class="row-meta mt-2">${task.receiptStatus || '待对账'}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">对账完成后才能进入回流确认。</div></div></div>`}
          </div>
        `)}
        ${panel('回流共享说明', '查看本次补录沉淀出的回流候选', `
          <div class="grid grid-cols-2 gap-4 text-body leading-7">
            <div><strong>回流候选对象</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateObject}</div></div>
            <div><strong>回流状态</strong><div class="mt-2 text-zw-mute">${task.backflow.status}</div></div>
            <div class="col-span-2"><strong>候选字段</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateFields.length ? task.backflow.candidateFields.join(' / ') : '—'}</div></div>
            <div class="col-span-2"><strong>确认条件</strong><div class="mt-2 text-zw-mute">需先完成汇总确认和交付回执对账，由台账管理员 / 目录管理员显式确认，系统再写入审计。</div></div>
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
            <div>申请状态：${request ? requestStatusLabel(request, window.STATE.role) : '关联申请仅作可选补充，当前按交付任务投影展示'}</div>
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


function r7ProviderWorkflowCards() {
  if (window.STATE && window.STATE.role !== 'r7') return '';
  const fd = (window.RUNTIME_R7_FIELD_DRAFTS || []).length;
  const hk = (window.RUNTIME_R7_HOOKUP_PENDING || []).length;
  const dm = (window.RUNTIME_R7_DEMAND_PENDING || []).length;
  const total = fd + hk + dm;
  // P5 — Inbox Zero. When all 3 R7 inboxes are empty, replace 4 zero-cards
  // with a single celebratory state; surface the buttons as a thin secondary
  // strip so direct deep-links still work.
  if (total === 0) {
    return `
      ${panel('收件箱已清空 · Inbox Zero', '本周 R7 三类裁决队列均已处理完，可专注分类关联 / 国家目录认领 / 在线目录定义等长周期治理', `
        <div class="text-body leading-7 text-zw-ink">字段口径裁决 ・ 资源挂接审核 ・ 供需对接 — 当前都为 0 条。</div>
        <div class="mt-4 flex flex-wrap gap-2">
          <a href="#/p5-provider/inbox/field-decision" class="gov-btn gov-btn-secondary">字段口径收件箱</a>
          <a href="#/p5-provider/inbox/hookup-review" class="gov-btn gov-btn-secondary">挂接审核收件箱</a>
          <a href="#/p5-provider/inbox/demand-match" class="gov-btn gov-btn-secondary">供需对接收件箱</a>
        </div>
      `)}
    `;
  }
  return `
    ${fd > 0 ? panel(`字段口径裁决（${fd} 条待我裁决）`, 'R6 反向编目草稿 → R7 校字段中文名 + 敏感等级 → 通过/驳回', `
      <div class="text-body-sm text-zw-mute mb-3">看 R6 已提交的草稿，置信度色块帮助你定位重点。</div>
      <a href="#/p5-provider/inbox/field-decision" class="gov-btn gov-btn-primary">打开字段口径收件箱</a>
    `) : ''}
    ${hk > 0 ? panel(`资源挂接审核（${hk} 条待我裁决）`, 'R6 提交目录项↔资源字段绑定 → R7 审字段证据', `
      <div class="text-body-sm text-zw-mute mb-3">字段绑定不清的资源会驳回回 R6 补 schema。</div>
      <a href="#/p5-provider/inbox/hookup-review" class="gov-btn gov-btn-primary">打开挂接审核收件箱</a>
    `) : ''}
    ${dm > 0 ? panel(`供需对接（${dm} 条需求待对接）`, 'R1 业务需求 → R7 判定复用 or 派 R5 任务', `
      <div class="text-body-sm text-zw-mute mb-3">可复用即落 demand-resource 对接；不可复用按区域/字段派 R5 切片任务。</div>
      <a href="#/p5-provider/inbox/demand-match" class="gov-btn gov-btn-primary">打开供需对接收件箱</a>
    `) : ''}
  `;
}

function r6ProviderWorkflowCards() {
  if (window.STATE && window.STATE.role !== 'r6') return '';
  return `
    ${panel('反向编目（R6 → R7）', '选已采集库表 → 系统预填 90% 草稿 → 一键提交 R7 字段口径裁决', `
      <div class="text-body-sm text-zw-mute mb-3">用现成的 schema 一气呵成新建目录草稿，跳过空白表单。</div>
      <a href="#/p5-provider/wizard/reverse-catalog" class="gov-btn gov-btn-primary">进入反向编目工作流</a>
    `)}
    ${panel('API 服务化交付（R6 → R7/R2）', '把已发布资源对外开放为 API，配 IP 白名单 + 限流 + 字段脱敏档位', `
      <div class="text-body-sm text-zw-mute mb-3">资源 → API 草稿 → 提审 R7 边界审 + R2 授权策略复核。</div>
      <a href="#/p5-provider/wizard/api-service" class="gov-btn gov-btn-primary">进入 API 服务化工作流</a>
    `)}
    ${panel('自动检测规则维护（R6）', '维护必填率 / 格式 / 值域 / 字段一致性等检测规则，触发任务、查看回执、失败重跑', `
      <div class="text-body-sm text-zw-mute mb-3">规则版本化；失败任务保留摘要可重跑。</div>
      <a href="#/p5-provider/wizard/quality-rule" class="gov-btn gov-btn-primary">进入检测规则工作流</a>
    `)}
    ${panel('资源挂接 / 发布 / 维护（已有）', '已有目录-资源绑定 + 资源上下架；驳回回路看下方"第一步/第二步"', `
      <div class="text-body-sm text-zw-mute mb-3">沿用下方现有列表入口；将在 W3 收敛为统一审核队列。</div>
    `)}
  `;
}

PAGES.provider = function () {
  // W6.2: P5 按角色严格隔离 — R6 看维护卡 + 三步面板；R7 看收件箱 + 目录运营
  const role = window.STATE.role;
  const ai = window.RUNTIME_PROVIDER.aiGovernance;
  const isR6 = role === 'r6';
  const isR7 = role === 'r7';
  const r6Cards = isR6 ? r6ProviderWorkflowCards() : '';
  const r7Cards = isR7 ? r7ProviderWorkflowCards() : '';
  const heroKicker = isR7 ? '目录运营收件箱' : '维护数据供给';
  const heroTitle = isR7
    ? '让发布真正可发现、可申请、可授权。'
    : '把目录、资源、API 准备好 — 让 R1 一搜就用。';
  const heroSubtitle = isR7
    ? '字段口径裁决 / 资源挂接审核 / 供需对接 — 3 张收件箱集中处理。'
    : '反向编目 / API 服务化 / 自动检测规则 / 资源挂接 — 4 张工作流入口。';
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: heroKicker }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${escapeHtml(heroKicker)}</div>
          <div class="page-hero-title">${escapeHtml(heroTitle)}</div>
          <div class="page-hero-subtitle">${escapeHtml(heroSubtitle)}</div>
        </div>
        <div class="page-meta">${isR7 ? '目录管理员（R7）' : '台账管理员（R6）'}</div>
      </div>
    </div>

    ${isR6 && r6Cards ? `<div class="grid grid-cols-2 gap-5">${r6Cards}</div>` : ''}
    ${isR7 && r7Cards ? `<div class="grid grid-cols-2 gap-5">${r7Cards}</div>` : ''}

    ${isR6 ? statCards(window.RUNTIME_PROVIDER.overview) : ''}

    ${isR6 ? `
    <div class="grid grid-cols-3 gap-5">
      ${panel('第一步：确认目录说明', '把来源、用途、责任人与申请边界说清楚', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.catalogs.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.owner} · ${item.issue}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}<button onclick="window.ACTIONS.manageCatalogEntry('${item.id}', '${item.status === '已发布' ? 'revise' : 'publish'}')" class="gov-btn gov-btn-secondary">${item.status === '已发布' ? '修正文案' : '发布共享'}</button></div></div>`).join('')}</div>
      `)}
      ${panel('第二步：确认资源可用性', '可复用就发布，不适合继续共享就暂停', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.resources.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.type} · 更新于 ${item.updatedAt}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}<button onclick="window.ACTIONS.manageResourceAsset('${item.id}', '${item.status === '可共享' ? 'suspend' : 'publish'}')" class="gov-btn gov-btn-secondary">${item.status === '可共享' ? '暂停共享' : '发布共享'}</button></div></div>`).join('')}</div>
      `)}
      ${panel('第三步：值守预填与回流服务', '保障前台可用，出现异常先暂停服务', `
        <div class="gov-list text-body">${window.RUNTIME_PROVIDER.services.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">本周服务活跃度 ${item.qps} 次调用 · ${item.note}</div></div><div class="flex items-center gap-2">${statusPill(item.status)}${item.status === '在线' ? `<button onclick="window.ACTIONS.suspendProviderService('${item.id}')" class="gov-btn gov-btn-secondary">暂停</button>` : `<button onclick="window.ACTIONS.publishProviderService('${item.id}')" class="gov-btn gov-btn-secondary">发布</button>`}</div></div>`).join('')}</div>
      `)}
    </div>` : ''}

    ${panel('今日优先处理', '先处理最影响前台办理体验的事项', `
      <div data-ai-surface="provider-governance" class="text-body leading-7 text-zw-ink">${ai.summary}</div>
      <div class="mt-4 text-body-sm text-zw-mute leading-7">${ai.priorities.map(item => `• ${item}`).join('<br/>')}</div>
    `)}
  `;
  return shell('p5', main);
};

// ----- W3 R7 P5 工作收件箱 -------------------------------------------------

PAGES.providerInboxFieldDecision = function () {
  const items = window.RUNTIME_R7_FIELD_DRAFTS || [];
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '字段口径裁决' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">字段口径裁决收件箱（R7）</div>
          <div class="page-hero-title">${items.length} 条 R6 反向编目草稿待我裁决。</div>
          <div class="page-hero-subtitle">每条草稿带 R6 提交的字段建议；点开看完整字段表，按置信度色块定位重点。</div>
        </div>
        <div class="page-meta">目录管理员（R7）</div>
      </div>
    </div>
    <div class="state-card mt-4">
      ${items.length ? `
        <div class="gov-list text-body-sm">
          ${items.map(item => `
            <div class="gov-list-row">
              <div>
                <div class="row-title">${escapeHtml(item.title || item.catalog_code)}</div>
                <div class="row-meta mt-1">${escapeHtml(item.catalog_code)} · 提交方 ${escapeHtml(item.owner_org_id || '—')}</div>
              </div>
              <div class="flex items-center gap-2">
                <span class="status-pill is-pending">draft</span>
                <a href="#/p5-provider/inbox/field-decision/${encodeURIComponent(item.catalog_code)}" class="gov-btn gov-btn-secondary">打开裁决</a>
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="row-meta">当前无待我裁决的反向编目草稿。</div>'}
      <div class="mt-4">
        <a href="#/p5-provider" class="gov-btn gov-btn-secondary">返回 P5</a>
      </div>
    </div>
  `;
  return shell('p5', main);
};

PAGES.providerInboxFieldDecisionDetail = function (catalogCode) {
  const decoded = decodeURIComponent(catalogCode || '');
  const suggestions = window.RUNTIME_R7_FIELD_DRAFT_DETAIL || null;
  if (!suggestions) {
    return shell('p5', `
      ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '字段口径裁决', href: '#/p5-provider/inbox/field-decision' }, { label: decoded }])}
      <div class="state-card mt-4">
        <div class="page-kicker">正在加载草稿</div>
        <div class="row-meta mt-2">${escapeHtml(decoded)}</div>
      </div>
    `);
  }
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '字段口径裁决', href: '#/p5-provider/inbox/field-decision' }, { label: decoded }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">字段口径裁决：${escapeHtml(decoded)}</div>
          <div class="page-hero-title">校字段中文名 + 敏感等级，然后通过 / 驳回。</div>
          <div class="page-hero-subtitle">绿/黄/橙 分别代表 comment / PII 模式 / 待补名 — 通过后草稿进 pending_review；驳回回 R6 修 schema。</div>
        </div>
        <div class="page-meta">目录管理员（R7）</div>
      </div>
    </div>

    <div class="state-card mt-4">
      <div class="row-title mb-2">字段建议表（共 ${suggestions.coverage.total} 字段 · ${suggestions.coverage.green} 绿 / ${suggestions.coverage.yellow} 黄 / ${suggestions.coverage.orange} 橙）</div>
      <table class="gov-table text-body-sm">
        <thead><tr><th>字段英文名</th><th>R6 建议中文名（可改）</th><th>R6 建议来源</th><th>敏感等级（可改）</th><th>类型</th></tr></thead>
        <tbody>
          ${suggestions.fields.map((f, i) => `
            <tr>
              <td><code>${escapeHtml(f.field_en)}</code></td>
              <td><input class="gov-input fd-field-cn" data-i="${i}" value="${escapeHtml(f.field_cn)}"/></td>
              <td>${confidenceBadge(f.confidence)}</td>
              <td>
                <select class="gov-input fd-field-sens" data-i="${i}">
                  ${['1','2','3','4'].map(lv => `<option value="${lv}" ${f.sensitive_level === lv ? 'selected' : ''}>${lv} 级</option>`).join('')}
                </select>
              </td>
              <td class="row-meta">${escapeHtml(f.data_type || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <div class="mt-4">
        <label class="row-meta">裁决意见 / 驳回理由</label>
        <input id="fd-comment" class="gov-input mt-1" placeholder="可写明字段一致性 / 共享条件 / 敏感等级判断依据"/>
      </div>

      <div class="mt-5 flex gap-3">
        <button onclick="window.ACTIONS.confirmFieldDecision('${escapeHtml(decoded)}')" class="gov-btn gov-btn-primary">通过 → 进入 pending_review</button>
        <button onclick="window.ACTIONS.rejectFieldDecision('${escapeHtml(decoded)}')" class="gov-btn gov-btn-secondary">驳回 → 退回 R6</button>
        <a href="#/p5-provider/inbox/field-decision" class="gov-btn gov-btn-secondary">返回收件箱</a>
      </div>
    </div>
  `;
  return shell('p5', main);
};

PAGES.providerInboxHookupReview = function () {
  const items = window.RUNTIME_R7_HOOKUP_PENDING || [];
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '挂接审核' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">资源挂接审核收件箱（R7）</div>
          <div class="page-hero-title">${items.length} 条挂接 / 资源发布草稿待我裁决。</div>
          <div class="page-hero-subtitle">校 R6 提交的目录项↔资源字段绑定证据；字段绑定不清的退回 R6。</div>
        </div>
        <div class="page-meta">目录管理员（R7）</div>
      </div>
    </div>
    <div class="state-card mt-4">
      ${items.length ? `
        <div class="gov-list text-body-sm">
          ${items.map(item => {
            const code = item.resource_code || item.catalog_code || item.id || '';
            // If title is the same as the code (legacy data with no name), fall
            // back to a short formatted id so the row isn't dominated by a hash.
            const title = (item.title && item.title !== code) ? item.title : formatIdShort(code, '目录');
            return `
            <div class="gov-list-row">
              <div>
                <div class="row-title">${escapeHtml(title)}</div>
                <div class="row-meta mt-1">${escapeHtml(item.kind || '目录条目')} · 状态 ${escapeHtml(item.lifecycle_status || item.status || '—')} · ${escapeHtml(formatIdShort(code, '编码'))}</div>
              </div>
              <div class="flex items-center gap-2">
                <span class="status-pill is-pending">${escapeHtml(item.lifecycle_status || item.status || 'pending_review')}</span>
                <button onclick="window.ACTIONS.approveResourceReview('${escapeHtml(code)}')" class="gov-btn gov-btn-primary">通过</button>
                <button onclick="window.ACTIONS.rejectResourceReview('${escapeHtml(code)}')" class="gov-btn gov-btn-secondary">驳回</button>
              </div>
            </div>
          `;}).join('')}
        </div>
      ` : '<div class="row-meta">当前无待我审核的挂接 / 资源发布草稿。</div>'}
      <div class="mt-4">
        <a href="#/p5-provider" class="gov-btn gov-btn-secondary">返回 P5</a>
      </div>
    </div>
  `;
  return shell('p5', main);
};

PAGES.providerInboxDemandMatch = function () {
  const items = window.RUNTIME_R7_DEMAND_PENDING || [];
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '供需对接' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">供需对接收件箱（R7）</div>
          <div class="page-hero-title">${items.length} 条 R1 业务需求待对接。</div>
          <div class="page-hero-subtitle">先判定能不能用现成目录复用；不可复用就按区域/字段切片成 R5 任务。</div>
        </div>
        <div class="page-meta">目录管理员（R7）</div>
      </div>
    </div>
    <div class="state-card mt-4">
      ${items.length ? `
        <div class="gov-list text-body-sm">
          ${items.map(item => `
            <div class="gov-list-row">
              <div>
                <div class="row-title">${escapeHtml(item.applicant_name || item.application_code)}</div>
                <div class="row-meta mt-1">${escapeHtml(item.applicant_org || '—')} · 提交于 ${escapeHtml(item.submitted_at || '—')}</div>
              </div>
              <div class="flex items-center gap-2">
                <span class="status-pill is-pending">${escapeHtml(item.status || 'submitted')}</span>
                <a href="#/p5-provider/inbox/demand-match/${encodeURIComponent(item.application_code)}" class="gov-btn gov-btn-secondary">打开对接</a>
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="row-meta">当前无待对接的业务需求。</div>'}
      <div class="mt-4">
        <a href="#/p5-provider" class="gov-btn gov-btn-secondary">返回 P5</a>
      </div>
    </div>
  `;
  return shell('p5', main);
};

PAGES.providerInboxDemandMatchDetail = function (applicationCode) {
  const decoded = decodeURIComponent(applicationCode || '');
  const ctx = window.RUNTIME_R7_DEMAND_DETAIL || null;
  if (!ctx) {
    return shell('p5', `
      ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '供需对接', href: '#/p5-provider/inbox/demand-match' }, { label: decoded }])}
      <div class="state-card mt-4">
        <div class="page-kicker">正在加载需求</div>
        <div class="row-meta mt-2">${escapeHtml(decoded)}</div>
      </div>
    `);
  }
  const demand = ctx.demand || {};
  const matches = ctx.matches || [];
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '供需对接', href: '#/p5-provider/inbox/demand-match' }, { label: decoded }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">供需对接：${escapeHtml(decoded)}</div>
          <div class="page-hero-title">先看现成候选，再决定复用 or 派 R5。</div>
          <div class="page-hero-subtitle">需求来自 ${escapeHtml(demand.applicant_name || '—')} · ${escapeHtml(demand.applicant_org || '—')}</div>
        </div>
        <div class="page-meta">目录管理员（R7）</div>
      </div>
    </div>

    ${panel('需求摘要', '', `
      <pre class="text-body-sm text-zw-mute" style="white-space: pre-wrap;">${escapeHtml(JSON.stringify(demand.payload_json || {}, null, 2))}</pre>
    `)}

    ${panel(`候选可复用资源（${matches.length} 条）`, '匹配自 catalog_entry + resource_asset 的现有 active 资产', `
      ${matches.length ? `
        <div class="gov-list text-body-sm">
          ${matches.map(m => `
            <div class="gov-list-row">
              <div>
                <div class="row-title">${escapeHtml(m.title || m.id)}</div>
                <div class="row-meta mt-1">${escapeHtml(m.resource_kind || '—')} · ${escapeHtml(m.region_code || '—')}</div>
              </div>
              <div class="flex items-center gap-2">
                <span class="status-pill is-ok">可复用</span>
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="row-meta">未找到现成可复用资源 — 建议派 R5 切片任务。</div>'}
    `)}

    ${panel('R7 决定', '', `
      <div class="mt-3">
        <label class="row-meta">切片方式（仅在派 R5 时填）</label>
        <input id="dm-slice" class="gov-input mt-1" placeholder='{"slice_by":"region","slices":["370102","370112"]}'/>
      </div>
      <div class="mt-5 flex gap-3">
        <button onclick="window.ACTIONS.dispatchDemand('${escapeHtml(decoded)}')" class="gov-btn gov-btn-primary">派 R5 切片任务</button>
        <a href="#/p5-provider/inbox/demand-match" class="gov-btn gov-btn-secondary">返回收件箱</a>
      </div>
      <div class="row-meta mt-3">如可复用，请直接在 R1 申请审批中通过；本端只处理"不可复用 → 派任务"动作。</div>
    `)}
  `;
  return shell('p5', main);
};

// ----- W2 R6 P5 工作流向导 -------------------------------------------------

function confidenceBadge(confidence) {
  const cls = { green: 'is-ok', yellow: 'is-warn', orange: 'is-pending' }[confidence] || 'is-pending';
  const label = { green: '高 (comment)', yellow: '中 (PII 模式)', orange: '低 (待 R6 补名)' }[confidence] || confidence;
  return `<span class="status-pill ${cls}">${escapeHtml(label)}</span>`;
}

PAGES.providerWizardReverseCatalog = function () {
  const wizState = window.STATE.providerReverseCatalog || {};
  const candidates = window.RUNTIME_PROVIDER_REVERSE_CANDIDATES || [];
  const suggestions = wizState.suggestions || null;
  const draftTitle = wizState.draftTitle || (suggestions && suggestions.title_suggestion && suggestions.title_suggestion.title) || '';

  const stepChoose = `
    <div class="state-card mt-4">
      <div class="page-kicker">第 1 步：选已采集 schema 作为反向编目源</div>
      <div class="row-meta mt-2">系统会优先列出尚未生成草稿的候选；已有草稿的会标记。</div>
      <div class="mt-4 flex gap-3">
        <button onclick="window.ACTIONS.loadReverseCatalogCandidates()" class="gov-btn gov-btn-primary">${candidates.length ? '重新拉取候选' : '加载候选 schema 清单'}</button>
        <a href="#/p5-provider" class="gov-btn gov-btn-secondary">返回 P5</a>
      </div>
      ${candidates.length ? `
        <div class="gov-list mt-4 text-body-sm">
          ${candidates.map(c => `
            <div class="gov-list-row">
              <div>
                <div class="row-title">${escapeHtml(c.schema_ref || '')}</div>
                <div class="row-meta mt-1">${escapeHtml(c.resource_code || '')} · binding ${escapeHtml(c.binding_code || '—')} · 采集于 ${escapeHtml(c.captured_at || '')}</div>
              </div>
              <div class="flex items-center gap-2">
                ${c.has_reverse_draft ? '<span class="status-pill is-pending">已有草稿</span>' : ''}
                <button onclick="window.ACTIONS.pickReverseCatalogSource('${escapeHtml(c.schema_ref || '')}')" class="gov-btn gov-btn-secondary">用这条预填</button>
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="row-meta mt-4">尚未加载候选；点击上方按钮拉取。</div>'}
    </div>
  `;

  const stepReview = suggestions ? `
    <div class="state-card mt-4">
      <div class="page-kicker">第 2 步：预填草稿（90% 已填，你只校对差异）</div>
      <div class="row-meta mt-2">绿/黄/橙 分别代表 comment / PII 模式 / 待补名 — 重点校对橙色字段。</div>

      <div class="mt-4 grid grid-cols-2 gap-4">
        <div>
          <label class="row-meta">目录英文编码（不可改）</label>
          <input id="rc-catalog-code" class="gov-input mt-1" value="${escapeHtml(suggestions.schema_ref.replace(/[^a-z0-9_-]/gi,'_'))}"/>
        </div>
        <div>
          <label class="row-meta">目录中文名</label>
          <input id="rc-title" class="gov-input mt-1" value="${escapeHtml(draftTitle)}" />
        </div>
      </div>

      <div class="mt-5">
        <div class="row-title mb-2">字段预填 (${suggestions.coverage.green} 绿 / ${suggestions.coverage.yellow} 黄 / ${suggestions.coverage.orange} 橙)</div>
        <table class="gov-table text-body-sm">
          <thead><tr><th>字段英文名</th><th>中文名（可改）</th><th>建议来源</th><th>敏感等级</th><th>类型</th></tr></thead>
          <tbody>
            ${suggestions.fields.map((f, i) => `
              <tr>
                <td><code>${escapeHtml(f.field_en)}</code></td>
                <td><input class="gov-input rc-field-cn" data-i="${i}" value="${escapeHtml(f.field_cn)}"/></td>
                <td>${confidenceBadge(f.confidence)}</td>
                <td>
                  <select class="gov-input rc-field-sens" data-i="${i}">
                    ${['1','2','3','4'].map(lv => `<option value="${lv}" ${f.sensitive_level === lv ? 'selected' : ''}>${lv} 级</option>`).join('')}
                  </select>
                </td>
                <td class="row-meta">${escapeHtml(f.data_type || '')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <div class="mt-5 flex gap-3">
        <button onclick="window.ACTIONS.submitReverseCatalogDraft()" class="gov-btn gov-btn-primary">提交草稿（进入 R7 字段口径裁决）</button>
        <button onclick="window.ACTIONS.resetReverseCatalogWizard()" class="gov-btn gov-btn-secondary">重选 schema</button>
      </div>
    </div>
  ` : '';

  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '反向编目工作流' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">反向编目工作流</div>
          <div class="page-hero-title">选源 → 预填 → 提交，一气呵成。</div>
          <div class="page-hero-subtitle">系统读 column.comment + meta_standard_cn + PII 模式给 90% 字段中文名建议；你只补差异。R7 在工作收件箱里裁决字段口径。</div>
        </div>
        <div class="page-meta">台账管理员（R6）</div>
      </div>
    </div>

    ${stepChoose}
    ${stepReview}
  `;
  return shell('p5', main);
};

PAGES.providerWizardApiService = function () {
  const wizState = window.STATE.providerApiServiceWizard || {};
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: 'API 服务化交付' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">API 服务化交付</div>
          <div class="page-hero-title">把已发布资源对外开放为 API。</div>
          <div class="page-hero-subtitle">注册 API → 配 IP 白名单 / 限流 / 字段脱敏档位 → 提审 R7 边界审 + R2 授权策略复核。</div>
        </div>
        <div class="page-meta">台账管理员（R6）</div>
      </div>
    </div>
    <div class="state-card mt-4">
      <div class="row-title mb-3">填 API 草稿</div>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="row-meta">资源 ID</label>
          <input id="api-resource-id" class="gov-input mt-1" placeholder="例如 resource-停车场"/>
        </div>
        <div>
          <label class="row-meta">API 路径</label>
          <input id="api-path" class="gov-input mt-1" placeholder="例如 /v1/parking-lots"/>
        </div>
        <div>
          <label class="row-meta">IP 白名单（CIDR / 逗号分隔）</label>
          <input id="api-iplist" class="gov-input mt-1" placeholder="例如 10.0.0.0/24, 10.1.2.3"/>
        </div>
        <div>
          <label class="row-meta">限流（每分钟）</label>
          <input id="api-ratelimit" class="gov-input mt-1" type="number" value="60"/>
        </div>
        <div>
          <label class="row-meta">字段脱敏档位</label>
          <select id="api-mask-level" class="gov-input mt-1">
            <option value="full">完全脱敏（仅返回打码）</option>
            <option value="partial" selected>部分脱敏（保留首尾）</option>
            <option value="none">不脱敏（仅向 sd-default 信任组织）</option>
          </select>
        </div>
        <div>
          <label class="row-meta">订阅应用</label>
          <input id="api-app" class="gov-input mt-1" placeholder="例如 app-民生协同"/>
        </div>
      </div>
      <div class="mt-5 flex gap-3">
        <button onclick="window.ACTIONS.submitApiServicePublish()" class="gov-btn gov-btn-primary">提交 API 草稿 → R7 审核</button>
        <a href="#/p5-provider" class="gov-btn gov-btn-secondary">返回 P5</a>
      </div>
      <div class="row-meta mt-3">提交后会依次调用 resource.api.register → resource.api.policy.update → resource.api.submit_review。审核结果在 R7 收件箱。</div>
    </div>
  `;
  return shell('p5', main);
};

PAGES.providerWizardQualityRule = function () {
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '维护数据供给', href: '#/p5-provider' }, { label: '自动检测规则工作流' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">自动检测规则维护</div>
          <div class="page-hero-title">维护检测规则、触发任务、失败重跑。</div>
          <div class="page-hero-subtitle">规则按 rule_code 幂等保存；任务由外部执行器跑，失败可重跑。</div>
        </div>
        <div class="page-meta">台账管理员（R6）</div>
      </div>
    </div>
    <div class="grid grid-cols-2 gap-5 mt-4">
      ${panel('新增 / 更新检测规则', 'rule_code 全局唯一；变更产生新版本', `
        <div class="grid grid-cols-1 gap-3">
          <div>
            <label class="row-meta">规则编码</label>
            <input id="qr-code" class="gov-input mt-1" placeholder="例如 QR-MUST-FILL-01"/>
          </div>
          <div>
            <label class="row-meta">规则名称</label>
            <input id="qr-name" class="gov-input mt-1" placeholder="例如 必填率检查"/>
          </div>
          <div>
            <label class="row-meta">规则类型</label>
            <select id="qr-kind" class="gov-input mt-1">
              <option value="completeness">必填率</option>
              <option value="format">字段格式</option>
              <option value="value-range">值域</option>
              <option value="consistency">字段一致性</option>
              <option value="mapping">挂接一致性</option>
            </select>
          </div>
          <div>
            <label class="row-meta">阈值（json，可选）</label>
            <input id="qr-payload" class="gov-input mt-1" placeholder='{"threshold": 0.98}'/>
          </div>
        </div>
        <div class="mt-4">
          <button onclick="window.ACTIONS.submitQualityRule()" class="gov-btn gov-btn-primary">保存 / 更新规则</button>
        </div>
      `)}
      ${panel('触发任务 / 失败重跑', '只发起任务；执行在外部，回执由 ops.catalog.quality.query 查看', `
        <div class="grid grid-cols-1 gap-3">
          <div>
            <label class="row-meta">已存规则编码</label>
            <input id="qr-run-code" class="gov-input mt-1" placeholder="例如 QR-MUST-FILL-01"/>
          </div>
          <div>
            <label class="row-meta">目标目录（可选）</label>
            <input id="qr-run-target" class="gov-input mt-1" placeholder="例如 catalog-停车场信息"/>
          </div>
          <div>
            <label class="row-meta">重跑：上一次失败 task_ref</label>
            <input id="qr-replay-prev" class="gov-input mt-1" placeholder="quality-task:...:..."/>
          </div>
        </div>
        <div class="mt-4 flex gap-3">
          <button onclick="window.ACTIONS.runQualityTask()" class="gov-btn gov-btn-primary">触发任务</button>
          <button onclick="window.ACTIONS.replayQualityTask()" class="gov-btn gov-btn-secondary">失败重跑</button>
        </div>
      `)}
    </div>
    <div class="mt-4 row-meta">
      要查看任务结果与失败摘要，请用 <code>ops.catalog.quality.query</code>（P6 合规运营页可见）或 W3 上线后的统一收件箱。
    </div>
  `;
  return shell('p5', main);
};


PAGES.complianceOps = function () {
  const metrics = window.RUNTIME_DASHBOARD.burdenMetrics;
  const role = (window.STATE && window.STATE.role) || 'r8';
  // B4 — R2 vs R5 vs R6 vs R7 vs R8 must not look like the same page.
  const heroCfg = (
    role === 'r2' ? { kicker: '审批承接 · 合规视角', title: '看你审过的申请有没有形成绕行或重复要数。', subtitle: '回放你刚刚审批的准入边界，确认它们没有反弹成线下采集或越权访问。', meta: '审批承接' } :
    role === 'r5' ? { kicker: '审核汇总 · 异常优先', title: '盯异常、确认自动汇总，不去线下重算。', subtitle: '先看争议与异常工单，再看减负指标与审计回放是否还有口径未对齐。', meta: '审核汇总' } :
    role === 'r6' ? { kicker: '资源治理 · 提供方视角', title: '哪些资源字段被频繁要求、被审计点名？', subtitle: '从合规事件回推到你管理的资源、字段、采集任务，决定是否升级模板或下架。', meta: '资源治理' } :
    role === 'r7' ? { kicker: '目录运营 · 共享侧视角', title: '看可见性与授权策略是否被绕行。', subtitle: '从争议、撤回、IAM 异常反向核对你发布的目录与共享专区是否需要调整。', meta: '目录运营' } :
                    { kicker: '合规督查 · 减负主责', title: '打住重复要数，统计采集和基层负担反映。', subtitle: '减负指标 / 绕行抽查 / 异议四子流程时间线，全部进入证据链。', meta: '合规督查' }
  );
  // R5 cares first about exceptions, R2 about audit replay, others get the
  // default metrics-first layout.
  const exceptionsFirst = role === 'r5';
  const main = `
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: heroCfg.kicker }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">${escapeHtml(heroCfg.kicker)}</div>
          <div class="page-hero-title">${escapeHtml(heroCfg.title)}</div>
          <div class="page-hero-subtitle">${escapeHtml(heroCfg.subtitle)}</div>
        </div>
        <div class="page-meta">${escapeHtml(heroCfg.meta)}</div>
      </div>
    </div>

    ${exceptionsFirst
      ? renderInlineSummary(window.RUNTIME_AUDIT_AI.summary, ['查看重复要数争议', '查看差异补录热区', '查看审计回放'])
      : panel('减负指标', '先看减负结果，再钻取证据和工单链路', `
      <div class="grid grid-cols-4 gap-4">
        ${metrics.map(item => `<a href="#/p6-compliance-ops" class="gov-stat-card gov-stat-link"><div class="gov-stat-label">${item.label}</div><div class="gov-stat-value">${item.value}</div><div class="mt-2 text-caption text-zw-mute">${item.trend}</div><div class="mt-3 text-caption font-bold text-zw-link">查看证据</div></a>`).join('')}
      </div>
    `)}

    ${exceptionsFirst
      ? panel('减负指标', '完成异常处理后，回看减负结果是否随之恢复', `
      <div class="grid grid-cols-4 gap-4">
        ${metrics.map(item => `<a href="#/p6-compliance-ops" class="gov-stat-card gov-stat-link"><div class="gov-stat-label">${item.label}</div><div class="gov-stat-value">${item.value}</div><div class="mt-2 text-caption text-zw-mute">${item.trend}</div><div class="mt-3 text-caption font-bold text-zw-link">查看证据</div></a>`).join('')}
      </div>
    `)
      : renderInlineSummary(window.RUNTIME_AUDIT_AI.summary, ['查看重复要数争议', '查看差异补录热区', '查看审计回放'])}

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
        ${r8BypassSurveillancePanel()}
      </section>
    </div>
  `;
  return shell('p6', main);
};

function r8BypassSurveillancePanel() {
  // W4.2: R8 视角下显示绕行督查；其他角色不显示
  if (!window.STATE || window.STATE.role !== 'r8') return '';
  const direct = window.RUNTIME_R8_DIRECT_ACCESS || { items: [], total: 0 };
  const objection = (window.RUNTIME_DISPUTES || []).filter(d => /绕行|线下|未审批/.test(d.title + (d.aiSummary || '')));
  return panel('R8 绕行督查 / 检测失败 / 撤回审计', '直达 + API 绕行抽查 / 检测任务失败 / 撤回是否走审批 / 异议四子流程时间倒置', `
    <div class="grid grid-cols-2 gap-4">
      <div class="state-card">
        <div class="row-title mb-2">数据直达交付清单（已审批）</div>
        <div class="row-meta text-body-sm mb-2">共 ${direct.total || 0} 条；任一条没有 application_record 回执都视为绕行风险。</div>
        ${direct.items && direct.items.length ? `
          <table class="gov-table text-body-sm">
            <thead><tr><th>delivery_code</th><th>application_code</th><th>state</th></tr></thead>
            <tbody>${direct.items.slice(0, 8).map(t => `<tr><td><code>${escapeHtml(t.delivery_code)}</code></td><td>${escapeHtml(t.application_code || '—')}</td><td>${escapeHtml(t.state || '')}</td></tr>`).join('')}</tbody>
          </table>
        ` : '<div class="row-meta">尚无已审批数据直达条目。</div>'}
      </div>
      <div class="state-card">
        <div class="row-title mb-2">异议绕行可疑事项 (${objection.length})</div>
        <div class="row-meta text-body-sm">命中"线下/绕行/未审批"关键字的争议；点击进 disputeDetail 看四子流程时间线。</div>
        ${objection.length ? `
          <div class="gov-list text-body-sm mt-3">
            ${objection.slice(0, 5).map(d => `<div class="gov-list-row"><div><div class="row-title">${escapeHtml(d.title)}</div><div class="row-meta mt-1">${escapeHtml(d.id)} · ${escapeHtml(d.owner || '')}</div></div><a href="#/p6-compliance-ops/dispute/${escapeHtml(d.id)}" class="gov-btn gov-btn-secondary">打开</a></div>`).join('')}
          </div>
        ` : '<div class="row-meta mt-2">未命中绕行可疑模式。</div>'}
      </div>
    </div>
    <div class="row-meta mt-3 text-body-sm">数据来自 direct_access.delivery.list + 异议争议过滤；不会反向改业务事实，仅作整改建议依据。</div>
  `);
}

function r5ObjectionFourSubstagesPanel(item) {
  // W4.4: R5 视角下展开"评估/处置/授权/用数"四子流程动作面板
  if (!window.STATE || window.STATE.role !== 'r5') return '';
  const id = item && item.id;
  if (!id) return '';
  return panel('异议四子流程裁决 (R5)', '评估 → 处置 → 授权影响 → 用数反馈；每段都进 data_objection projection，避免线下绕行。', `
    <div class="grid grid-cols-2 gap-4">
      <div class="state-card">
        <div class="row-title mb-2">① 评估</div>
        <div class="row-meta text-body-sm mb-2">判定异议是否成立（口径 / 质量 / 血缘 / 审批 / 范围 / 交付 / 直达）</div>
        <input id="obj-eval-${escapeHtml(id)}" class="gov-input mb-2" placeholder="评估结论 / 归因类别"/>
        <button onclick="window.ACTIONS.evaluateObjection('${escapeHtml(id)}')" class="gov-btn gov-btn-primary">提交评估</button>
      </div>
      <div class="state-card">
        <div class="row-title mb-2">② 处置</div>
        <div class="row-meta text-body-sm mb-2">退回 R3/R4 / 转 R6/R7 / 转 R2 / 解释关闭</div>
        <select id="obj-proc-action-${escapeHtml(id)}" class="gov-input mb-2">
          <option value="return-to-grassroots">退回基层</option>
          <option value="forward-to-provider">转 R6 修字段证据</option>
          <option value="forward-to-catalog">转 R7 修目录口径</option>
          <option value="forward-to-r2">转 R2 复审授权</option>
          <option value="close-with-explain">解释关闭</option>
        </select>
        <button onclick="window.ACTIONS.processObjection('${escapeHtml(id)}')" class="gov-btn gov-btn-primary">提交处置</button>
      </div>
      <div class="state-card">
        <div class="row-title mb-2">③ 授权影响</div>
        <div class="row-meta text-body-sm mb-2">确认是否影响在途授权或订阅</div>
        <input id="obj-authz-${escapeHtml(id)}" class="gov-input mb-2" placeholder="授权影响摘要"/>
        <button onclick="window.ACTIONS.reviewObjectionAuthorization('${escapeHtml(id)}')" class="gov-btn gov-btn-primary">登记授权影响</button>
      </div>
      <div class="state-card">
        <div class="row-title mb-2">④ 用数反馈</div>
        <div class="row-meta text-body-sm mb-2">用数方是否接受处置结果</div>
        <select id="obj-use-${escapeHtml(id)}" class="gov-input mb-2">
          <option value="accepted">接受</option>
          <option value="rejected">不接受 / 升级</option>
        </select>
        <button onclick="window.ACTIONS.replyObjection('${escapeHtml(id)}')" class="gov-btn gov-btn-primary">回复用数方</button>
      </div>
    </div>
    <div class="row-meta mt-3 text-body-sm">每段动作都会写一次 audit_event + objection.case.* skill；R8 督查时间倒置时会标记。</div>
  `);
}

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
    ${r5ObjectionFourSubstagesPanel(item)}
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
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '共享专区 / 专题包' }])}
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
      <div class="grid ${(window.RUNTIME_ZONES || []).length <= 3 ? 'grid-cols-2' : 'grid-cols-3'} gap-5">
        ${window.RUNTIME_ZONES.map(zone => `<a href="#/p7-zones-pack/zone/${zone.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-2"><div class="panel-title text-body">${zone.name}</div>${statusPill(zone.status)}</div><p class="text-body mt-3 leading-7">${zone.desc}</p><div class="mt-4 row-meta">资产 ${zone.assets.length} 项 · 订阅部门 ${zone.subscribers}</div><div class="mt-4 text-body-sm text-zw-mute leading-7">适用问题：${zone.aiGuide}</div></div></a>`).join('')}
      </div>
    `)}
  `;
  return shell('p7', main);
};

PAGES.zoneDetail = function (id) {
  const zone = zoneById(id);
  if (!zone) return entityNotFoundShell('p7', '专题包', id, '#/p7-zones-pack', '返回共享专区 / 专题包');
  const publishAction = window.STATE.role === 'r7'
    ? `<button onclick="window.ACTIONS.publishZoneTopicProjection('${zone.id}')" class="gov-btn gov-btn-primary">发布正式投影</button>`
    : actionNotice('当前身份可查看资产、发起复用申请或订阅更新，正式投影发布由目录管理员处理');
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
        <div class="mt-5">${publishAction}</div>
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
    ${crumbs([{ label: '数据共享工作台', href: '#/p1-workbench' }, { label: '受控接入治理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">受控接入治理</div>
          <div class="page-hero-title">只让能帮助办理、且不会越权的外部能力上线。</div>
          <div class="page-hero-subtitle">目录管理员确认来源、租户范围、权限策略和审计要求；涉及提交、审批、交付确认的能力必须保留人工确认。</div>
        </div>
        <div class="page-meta">管理员确认后生效</div>
      </div>
    </div>

    ${statCards([
      { label: '待审核能力', value: pendingCount, note: '待补租户范围和审计级别' },
      { label: '辅助能力', value: readOnlyCount, note: '可进入待上线清单' },
      { label: '已驳回越权', value: rejectedCount, note: '已阻断越权动作' },
      { label: '人工确认', value: '强制', note: '管理员待确认' },
    ])}

    ${renderInlineSummary('当前优先处理停车场信息共享目录只读查询能力：待补齐租户可见范围后再进入上线审核。', ['查看待审能力包', '查看暴露范围', '查看退回草案'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7">
        ${panel('待确认的外部能力', '逐项确认它能帮经办人提效，也不会替人越权办理', `
          <div class="space-y-3 text-body">
            ${packages.map(item => `<a href="#/p8-integration-admin/package/${item.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-3"><div class="panel-title text-body">${formatPackageName(item.slug)}</div>${statusPill(packageStatusLabel(item))}</div><div class="row-meta mt-2">${item.source}</div><div class="mt-3">${item.desc}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">审核状态：${packageStatusLabel(item)} · 暴露面 ${formatExposure(item.exposure)}</div><div class="mt-3 text-body-sm text-zw-mute leading-7" data-ai-surface="package-inline-ai">建议摘要：${item.aiReview.summary}</div></div></a>`).join('')}
          </div>
        `)}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('身份、权限与裁决证据', '查看账号绑定、岗位范围、租户策略和拒绝原因', `
          <div class="text-body leading-7 text-zw-ink">从统一能力契约读取治理总览，直接查看身份、授权与策略证据。</div>
          <a href="#/p8-integration-admin/iam-governance" class="gov-btn gov-btn-secondary mt-4 inline-block">打开治理总览</a>
        `)}
        ${panel('上线前确认', '上线前确认来源、范围、责任动作和回退方案', `
          <ul class="space-y-2 text-body leading-7 list-disc pl-5">
            <li>能力名称 / 版本 / 来源</li>
            <li>租户范围 / 权限策略 / 审计级别</li>
            <li>是否需要人工确认</li>
            <li>兼容范围 / 对外暴露范围</li>
            <li>影响说明 / 回退目标</li>
          </ul>
        `)}
        ${panel('辅助判断', '建议只帮管理员读材料，不替管理员批准上线。', `
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
    ${crumbs([{ label: '受控接入治理', href: '#/p8-integration-admin' }, { label: '身份与权限治理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-kicker">账号与权限治理</div>
          <div class="page-hero-title">查看账号绑定、岗位授权与能力开放范围。</div>
          <div class="page-hero-subtitle">这里集中展示可核对的授权事实、策略范围和裁决依据，方便管理员定位“为什么可用 / 为什么受限”。</div>
        </div>
        <div class="page-meta">${escapeHtml(data.tenant_id || 'sd-default')}</div>
      </div>
    </div>

    ${statCards([
      { label: '账号记录', value: summary.actor_count || 0, note: `绑定状态 ${JSON.stringify(summary.binding_status_counts || {})}` },
      { label: '组织 / 区划', value: `${summary.org_count || 0} / ${summary.region_count || 0}`, note: '当前授权数据范围' },
      { label: '岗位 / 策略', value: `${summary.role_count || 0} / ${summary.policy_count || 0}`, note: '岗位授权与能力范围' },
      { label: '待处理问题', value: summary.issue_count || 0, note: '未确认授权默认受限' },
    ])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('账号绑定与岗位授权', '查看账号状态、组织归属与岗位分配', `
          <div class="space-y-3 text-body">
            ${actors.map(item => `<div class="panel"><div class="panel-body"><div class="flex items-center justify-between gap-3"><div class="panel-title text-body">${escapeHtml(item.display_name || item.external_actor_id)}</div>${statusPill(item.status)}</div><div class="row-meta mt-2">${escapeHtml(item.external_actor_id)} · 组织 ${escapeHtml(item.org_code || '—')}</div><div class="mt-2 text-body-sm text-zw-mute leading-7">岗位：${(item.role_codes_json || []).map(escapeHtml).join('、') || '无'} · 绑定状态：${escapeHtml((item.profile_json && item.profile_json.binding_status) || item.status)}</div></div></div>`).join('') || '<div class="text-body text-zw-mute">暂无账号授权记录</div>'}
          </div>
        `)}
        ${panel('租户能力范围', '查看当前租户可用能力及开放面', `
          <table class="gov-table"><tbody>
            ${policies.map(item => `<tr><td>${escapeHtml(item.package_slug)}</td><td>${statusPill(item.policy_status)}</td><td>${escapeHtml((item.policy_json && (item.policy_json.exposedSurfaces || []).join('、')) || '—')}</td></tr>`).join('') || '<tr><td colspan="3">暂无租户能力范围配置</td></tr>'}
          </tbody></table>
        `)}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('策略裁决探针', '用样本账号验证当前租户策略是否允许', probe ? `
          <div class="text-body leading-7">裁决：${probe.allowed ? '允许' : '拒绝'} · ${escapeHtml(probe.decision_reason || '—')}</div>
          <div class="text-body-sm text-zw-mute leading-7 mt-2">能力：${escapeHtml(probe.capability_id || '—')} · 暴露面：${escapeHtml(probe.surface || '—')} · 审计级别：${escapeHtml(probe.audit_class || '—')}</div>
        ` : '<div class="text-body text-zw-mute">暂无可探测策略</div>')}
        ${panel('导入问题', '未绑定、未映射、组织关系缺失都会先受限，再等待修复', `
          <div class="space-y-2 text-body-sm leading-7">
            ${issues.map(item => `<div>${statusPill('warning')} ${escapeHtml(item.type)} · ${escapeHtml(item.table || '—')} · ${escapeHtml(item.legacy_ref || '—')}</div>`).join('') || '<div class="text-zw-mute">暂无导入问题</div>'}
          </div>
        `)}
        ${panel('审计证据', '策略裁决与导入操作会留下审计记录', `
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
  if (!item) return entityNotFoundShell('p8', '能力包', id, '#/p8-integration-admin', '返回受控接入治理');
  const ai = item.aiReview;
  const statusLabel = packageStatusLabel(item);
  const canApprove = item.status !== 'approved' && item.status !== 'rejected';
  const canReturn = item.status !== 'approved' && item.status !== 'rejected';
  const canReject = item.status !== 'approved' && item.status !== 'rejected';
  const canConfigureExposure = item.versionStatus === 'registered';
  const canApplyTenantPolicy = item.versionStatus === 'registered' && !(item.tenantPolicy && item.tenantPolicy.policyStatus === 'enabled');
  const main = `
    ${crumbs([{ label: '受控接入治理', href: '#/p8-integration-admin' }, { label: item.slug }])}
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
      ${renderDraftCard('审核意见草稿', [ai.draft], '审核助手只给草案；批准、退回和驳回仍由管理员点击确认。')}
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
    'ledger.entity.base.read': '停车场信息共享目录只读查询能力',
    'ledger.diff.recommend': '差异字段回流建议能力',
    'ledger.bulk.submit': '批量提交能力（已驳回）',
  }[slug] || slug;
}

function formatExposure(values) {
  const map = { api: '接口', cli: '命令行', mcp: '工具接入', a2a: '智能体协同' };
  return (values || []).map(item => map[item] || item).join(' / ');
}
