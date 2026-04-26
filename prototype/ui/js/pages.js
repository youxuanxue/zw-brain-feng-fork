window.PAGES = {};

function roleLabel(role) {
  return {
    r1: 'R1 上级业务需求发起人',
    r2: 'R2 审批承接人员',
    r3: 'R3 镇街填报人员',
    r4: 'R4 村社区填报人员',
    r5: 'R5 审核汇总人员',
    r6: 'R6 台账管理员',
    r7: 'R7 目录管理员',
    r8: 'R8 合规与减负治理',
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
    'open': 'status-warn',
    'escalated': 'status-danger',
    'resolved': 'status-ok',
    'warning': 'status-warn',
    'failed': 'status-danger',
    'reconciling': 'status-warn',
    'supplementing': 'status-warn',
    'summary-pending': 'status-warn',
    'completed': 'status-ok',
    'approved': 'status-ok',
    'pending': 'status-warn',
    'pending-fix': 'status-warn',
    'rejected': 'status-danger',
    '已派单': 'status-neutral',
    '筹建中': 'status-neutral',
    '不适用': 'status-neutral',
  };
  return `<span class="status-pill ${map[status] || 'status-neutral'}">${status}</span>`;
}

function crumbs(items) {
  return `
    <nav class="text-xs text-zw-mute mb-4 flex items-center gap-1.5 flex-wrap">
      ${items.map((it, i) => i === items.length - 1
        ? `<span class="text-zw-ink">${it.label}</span>`
        : `<a href="${it.href}" class="hover:text-zw-link">${it.label}</a><span class="opacity-40">/</span>`
      ).join('')}
    </nav>`;
}

function stepBar(steps, activeIdx) {
  return `
    <div class="flex items-center gap-2 mb-5 text-xs text-zw-mute flex-wrap">
      ${steps.map((s, i) => `
        <span class="step-dot ${i < activeIdx ? 'done' : i === activeIdx ? 'now' : 'todo'}">${i < activeIdx ? '✓' : i + 1}</span>
        <span class="${i === activeIdx ? 'text-zw-ink font-medium' : ''}">${s}</span>
        ${i < steps.length - 1 ? '<span class="opacity-30">───</span>' : ''}
      `).join('')}
    </div>`;
}

function statCards(items) {
  return `
    <div class="grid grid-cols-4 gap-4">
      ${items.map(item => `
        <div class="gov-stat-card">
          <div class="gov-stat-label">${item.label}</div>
          <div class="gov-stat-value">${item.value}</div>
        </div>`).join('')}
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
          <div class="text-sm leading-7 text-zw-ink flex-1">${summary}</div>
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
      ${note ? `<div class="mt-3 text-[13px] text-zw-mute leading-7">${note}</div>` : ''}
    </div>`;
}

function renderFieldState(label, value, state, note) {
  const chip = state === '已预填' || state === '已识别' ? 'chip-ok' : 'chip-ask';
  return `
    <div class="panel p-3 bg-zw-bg-soft border border-zw-line rounded-xl">
      <div class="row-meta mb-1">${label}</div>
      <div class="row-title">${value}</div>
      <div class="mt-2 flex items-center gap-2 flex-wrap">
        <span class="chip ${chip}">${state}</span>
        ${note ? `<span class="text-[13px] text-zw-mute">${note}</span>` : ''}
      </div>
    </div>`;
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

function deliveryStatusLabel(task) {
  if (!task) return '—';
  if (task.status === 'supplementing') return '待补录';
  if (task.status === 'reconciling') return '待汇总确认';
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
      <button onclick="window.ACTIONS.noop('当前已回到申请方补正阶段，需先补齐差异字段责任边界说明')" class="gov-btn gov-btn-secondary">查看补正说明</button>`;
  }
  if (!isGrassroots && item.status === 'pending') {
    return `
      <a href="#/p3-request-flow/review/${item.id}" class="gov-btn gov-btn-primary">进入审批详情</a>
      <button onclick="window.ACTIONS.noop('申请已进入受控准入，当前等待审批承接人员处理')" class="gov-btn gov-btn-secondary">查看准入说明</button>`;
  }
  if (isGrassroots && item.status === 'supplementing') {
    return `
      <button onclick="window.ACTIONS.submitSupplement('${item.id}')" class="gov-btn gov-btn-primary">提交差异补录</button>
      <button onclick="window.ACTIONS.noop('这里只补动态差异字段，不需要重新整表录入')" class="gov-btn gov-btn-secondary">查看补录说明</button>`;
  }
  if (item.status === 'summary-pending') {
    return `
      <a href="#/p3-request-flow/review/${item.id}" class="gov-btn gov-btn-primary">查看汇总确认</a>
      <button onclick="window.ACTIONS.noop('当前链路已进入自动汇总确认，等待 R5 处理异常项')" class="gov-btn gov-btn-secondary">查看异常项</button>`;
  }
  if (item.status === 'completed') {
    return `
      <a href="#/p4-delivery-exchange/task/DLV-2026-04-25-0011" class="gov-btn gov-btn-primary">查看回流确认</a>
      <button onclick="window.ACTIONS.noop('自动汇总已经确认完成，下一步是供给侧确认回流候选')" class="gov-btn gov-btn-secondary">查看回流说明</button>`;
  }
  if (item.status === 'rejected') {
    return `
      <button onclick="window.ACTIONS.noop('该申请已驳回，如需继续请回到模板复用起点重新收敛需求')" class="gov-btn gov-btn-secondary">查看驳回原因</button>`;
  }
  return `
    <button onclick="window.ACTIONS.noop('当前阶段没有新的责任写动作')" class="gov-btn gov-btn-secondary">查看当前说明</button>`;
}

function shell(activeKey, mainHtml) {
  const role = window.STATE.role;
  const nav = [
    { key: 'p1', label: 'P1 工作台', href: '#/p1-workbench', roles: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'] },
    { key: 'p2', label: 'P2 资源发现', href: '#/p2-discovery', roles: ['r1', 'r2', 'r6', 'r7', 'r8'] },
    { key: 'p3', label: 'P3 申请 / 审批 / 跟踪', href: '#/p3-request-flow', roles: ['r1', 'r2', 'r3', 'r4', 'r5'] },
    { key: 'p4', label: 'P4 交付 / 交换 / 回流', href: '#/p4-delivery-exchange', roles: ['r2', 'r5', 'r6', 'r7', 'r8'] },
    { key: 'p5', label: 'P5 提供方管理', href: '#/p5-provider', roles: ['r6', 'r7'] },
    { key: 'p6', label: 'P6 合规与运营', href: '#/p6-compliance-ops', roles: ['r2', 'r5', 'r6', 'r7', 'r8'] },
    { key: 'p7', label: 'P7 共享专区 / 专题包', href: '#/p7-zones-pack', roles: ['r1', 'r2', 'r6', 'r7', 'r8'] },
    { key: 'p8', label: 'P8 平台接入与扩展中心', href: '#/p8-integration-admin', roles: ['r7'] },
  ];
  const active = nav.find(item => item.key === activeKey);

  return `
    <div class="prototype-shell-grid">
      <aside class="prototype-shell-aside">
        <div class="prototype-shell-stack">
          <div class="panel prototype-nav-panel">
            <div class="panel-body">
              <div class="panel-title">v4 Prototype 导航</div>
              <div class="panel-subtitle">R1–R8 真实角色链路 · 法人模板首条黄金旅程</div>
              <div class="prototype-role-chip">当前角色：${roleLabel(role)}</div>
              <div class="mt-4 space-y-1.5">
                ${nav.map(item => {
                  const allowed = item.roles.includes(role);
                  const isActive = item.key === activeKey;
                  return `
                    <a href="${allowed ? item.href : '#'}"
                       ${allowed ? '' : 'onclick="event.preventDefault();window.UI.toast(\'当前角色无访问权限，验证角色边界\',\'info\')"'}
                       class="prototype-nav-link ${isActive ? 'is-active' : ''} ${allowed ? '' : 'is-disabled'}">
                      <span>${item.label}</span>
                      <span class="prototype-nav-state">${allowed ? (isActive ? '当前页' : '可进入') : '受角色约束'}</span>
                    </a>`;
                }).join('')}
              </div>
            </div>
          </div>

          <div class="panel prototype-focus-panel">
            <div class="panel-body">
              <div class="panel-title">当前验收焦点</div>
              <div class="panel-subtitle">不是看页面多少，而是看状态、责任和证据有没有连起来。</div>
              <div class="prototype-focus-list mt-4">
                <div class="prototype-focus-item">
                  <div class="prototype-focus-label">当前页</div>
                  <div class="prototype-focus-value">${active ? active.label : '当前场景'}</div>
                </div>
                <div class="prototype-focus-item">
                  <div class="prototype-focus-label">主链要求</div>
                  <div class="prototype-focus-value">先复用模板，再差异补录，再沉淀回流</div>
                </div>
                <div class="prototype-focus-item">
                  <div class="prototype-focus-label">责任边界</div>
                  <div class="prototype-focus-value">AI 只减摩，不代提交、不代审批、不代模板生效</div>
                </div>
                <div class="prototype-focus-item">
                  <div class="prototype-focus-label">失败表达</div>
                  <div class="prototype-focus-value">退回、驳回、熔断、快照模式必须诚实可见</div>
                </div>
              </div>
            </div>
          </div>

          <div class="panel prototype-guardrail-panel">
            <div class="panel-body">
              <div class="panel-title">快速对照</div>
              <div class="prototype-guardrail-list mt-4">
                <a href="#/p4-delivery-exchange/task/DLV-2026-04-25-0011" class="prototype-guardrail-link">看回流确认是否真实改变模板与专区</a>
                <a href="#/p8-integration-admin/package/PKG-2026-04-25-001" class="prototype-guardrail-link">看外部能力包是否仍被平台约束</a>
                <a href="#/dashboard/alert/AL-2026-04-25-002" class="prototype-guardrail-link">看 K12 是否只读消费治理结果与责任链</a>
              </div>
            </div>
          </div>
        </div>
      </aside>
      <section class="prototype-shell-main">${mainHtml}</section>
    </div>`;
}

function resourceById(id) {
  return window.MOCK_DISCOVERY.resources.find(item => item.id === id) || window.MOCK_DISCOVERY.resources[0];
}
function requestById(id) {
  return window.MOCK_REQUESTS.find(item => item.id === id) || window.MOCK_REQUESTS[0];
}
function approvalById(id) {
  return window.MOCK_APPROVALS.find(item => item.id === id) || window.MOCK_APPROVALS[0];
}
function deliveryById(id) {
  return window.MOCK_DELIVERY_TASKS.find(item => item.id === id) || window.MOCK_DELIVERY_TASKS[0];
}
function disputeById(id) {
  return window.MOCK_DISPUTES.find(item => item.id === id) || window.MOCK_DISPUTES[0];
}
function zoneById(id) {
  return window.MOCK_ZONES.find(item => item.id === id) || window.MOCK_ZONES[0];
}
function packageById(id) {
  return window.MOCK_CAPABILITY_PACKAGES.find(item => item.id === id) || window.MOCK_CAPABILITY_PACKAGES[0];
}

PAGES.workbench = function () {
  const current = window.MOCK_WORKBENCH[window.STATE.role] || window.MOCK_WORKBENCH.r1;
  const main = `
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${current.greeting}</div>
          <div class="page-hero-subtitle">${current.subtitle}</div>
        </div>
        <div class="page-meta">P1 工作台 · 真实角色待办 / 推荐 / 异常</div>
      </div>
    </div>

    ${statCards([
      { label: '真实角色', value: 'R1–R8' },
      { label: '首条黄金旅程', value: '法人模板复用' },
      { label: '结构化主页面', value: '8 + 1' },
      { label: '当前目标', value: '先复用后补录' },
    ])}

    ${renderInlineSummary(current.aiSummary.summary, current.aiSummary.actions)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('今日待办', '待办按真实角色和主旅程组织，不再按旧平台系统烟囱切开', infoList(current.todos))}
      ${panel('关键信号', '一屏看清复用、补录、汇总与减负效果', `<ul class="space-y-2 list-disc pl-5 text-sm">${current.highlights.map(item => `<li>${item}</li>`).join('')}</ul>`)}
    </div>

    ${panel('主旅程入口', '保持 8+1 IA，不新增并列大平台', `
      <div class="grid grid-cols-2 gap-3 text-sm">
        <a href="#/p2-discovery" class="panel card-hover"><div class="panel-body"><div class="panel-title">P2 资源发现</div><div class="panel-subtitle">R1/R2 先发现“法人单位基础信息台账模板”</div></div></a>
        <a href="#/p3-request-flow" class="panel card-hover"><div class="panel-body"><div class="panel-title">P3 申请 / 审批 / 跟踪</div><div class="panel-subtitle">R1/R2/R3/R4/R5 共用一条结构化链路</div></div></a>
        <a href="#/p4-delivery-exchange" class="panel card-hover"><div class="panel-body"><div class="panel-title">P4 交付 / 交换 / 回流</div><div class="panel-subtitle">补录、自动汇总、回流共享不再割裂</div></div></a>
        <a href="#/p5-provider" class="panel card-hover"><div class="panel-body"><div class="panel-title">P5 提供方管理</div><div class="panel-subtitle">R6/R7 管模板、目录和服务</div></div></a>
        <a href="#/p6-compliance-ops" class="panel card-hover"><div class="panel-body"><div class="panel-title">P6 合规与运营</div><div class="panel-subtitle">R8 看重复要数、绕行与减负结果</div></div></a>
        <a href="#/p7-zones-pack" class="panel card-hover"><div class="panel-body"><div class="panel-title">P7 共享专区 / 专题包</div><div class="panel-subtitle">把法人模板变成 zw-brain 前台可发现专题资产</div></div></a>
      </div>
    `)}
  `;
  return shell('p1', main);
};

PAGES.discovery = function () {
  const query = escapeHtml(window.STATE.discoveryQuery || '');
  const ai = window.MOCK_DISCOVERY.aiCopilot;
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P2 资源发现' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P2 资源发现</div>
          <div class="page-hero-subtitle">先发现 zw-brain 已沉淀的默认复用能力，再决定是否进入申请，而不是先造新表。</div>
        </div>
        <div class="page-meta">Journey 1–2 · 发现与复用判断</div>
      </div>
    </div>

    <div class="panel" data-ai-surface="search-context">
      <div class="panel-body">
        <div class="panel-title">搜索工作台</div>
        <div class="panel-subtitle">自然语言只负责把业务目标翻译成结构化检索上下文，不替代页面本身。</div>
        <form onsubmit="window.ACTIONS.setDiscoveryQuery(event)" class="flex gap-3 mt-4">
          <input id="discovery-q" type="text" value="${query}" class="flex-1 px-4 py-3 rounded-xl border border-zw-line text-[14px] bg-white" placeholder="例如：我要为本周营商环境专题复用法人单位基础信息台账模板" />
          <button class="gov-btn gov-btn-primary">重新解析</button>
        </form>
        <div class="mt-4 flex flex-wrap gap-2">
          <span class="chip chip-ok">已识别：涉企专题</span>
          <span class="chip chip-ok">已识别：先复用模板</span>
          <span class="chip chip-ok">已识别：差异补录</span>
          ${ai.missingQuestions.map(item => `<span class="chip chip-ask">${item}</span>`).join('')}
        </div>
        <div class="mt-4 text-[14px] leading-7 text-zw-ink">${ai.summary}</div>
      </div>
    </div>

    <div class="grid grid-cols-12 gap-5">
      <aside class="col-span-3 space-y-5">
        ${panel('目录树', '按对象和主题找，不按后台系统找', `
          <div class="space-y-2 text-[14px]">
            ${window.MOCK_DISCOVERY.catalogTree.map(item => `<div class="flex justify-between py-2 border-b border-zw-line/60"><span>${item.name}</span><span class="text-zw-mute">${item.count}</span></div>`).join('')}
          </div>
        `)}
        ${panel('当前缺口', '缺口不补齐也能看详情，但会影响申请与下游任务边界', `
          <div class="space-y-2 text-[14px] leading-7 text-zw-mute">
            ${ai.missingQuestions.map(item => `<div>• ${item}</div>`).join('')}
          </div>
        `)}
      </aside>
      <section class="col-span-9 space-y-4">
        ${panel('推荐结果', '把“为什么先用它”说清楚，让新增采集变成例外', `
          <div class="space-y-4">
            ${window.MOCK_DISCOVERY.resources.map(item => `
              <a href="#/p2-discovery/resource/${item.id}" class="panel card-hover block">
                <div class="panel-body">
                  <div class="grid grid-cols-12 gap-4 items-start">
                    <div class="col-span-8">
                      <div class="flex items-center gap-2"><div class="panel-title">${item.name}</div>${statusPill(item.status)}</div>
                      <div class="row-meta mt-2">${item.provider} · ${item.zone} · 更新于 ${item.updatedAt} · 覆盖/说明 ${item.coverage}</div>
                      <p class="text-[14px] mt-3 leading-7">${item.desc}</p>
                      <div class="mt-4 text-[13px] text-zw-mute leading-7" data-ai-surface="resource-reason">推荐理由：${item.explain.join('；')}</div>
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-[13px] text-zw-mute">相关度</div>
                      <div class="text-3xl font-bold text-zw-primary mt-1">${item.score}</div>
                    </div>
                    <div class="col-span-2 text-right">
                      <div class="text-[13px] text-zw-mute">下一步</div>
                      <div class="text-[14px] text-zw-ink leading-7 mt-1">${item.nextHints[0] || '查看详情'}</div>
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

PAGES.resourceDetail = function (id) {
  const item = resourceById(id);
  const zoneId = item.zone === '营商环境专区' ? 'business' : item.zone === '治理减负专区' ? 'governance' : 'livelihood';
  const main = `
    ${crumbs([{ label: 'P2 资源发现', href: '#/p2-discovery' }, { label: item.name }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${item.name}</div>
          <div class="page-hero-subtitle">${item.provider} · ${item.zone} · 更新于 ${item.updatedAt}</div>
        </div>
        ${statusPill(item.status)}
      </div>
    </div>

    ${renderInlineSummary('系统判断这里是当前涉企需求的默认起点：先复用法人模板，再把现场差异字段交给基层补录。', item.nextHints)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('核心字段与覆盖', '前台用户看到的是可复用能力，不是后台模型名', `<div class="gov-list">${item.fields.map(field => `<div class="gov-list-row"><div class="row-title">${field}</div><div class="row-meta">标准字段 / 可预填</div></div>`).join('')}</div>`)}
      ${panel('信任信息与动作', '把来源、覆盖和下一步说清楚，降低“我还要不要重新要数”的判断成本', `
        <div class="space-y-3 text-[14px]">
          <div>覆盖情况：<strong>${item.coverage}</strong></div>
          <div>历史审批通过率：<strong>${item.approvalRate}</strong></div>
          <div>订阅 / 使用部门：<strong>${item.subscribers}</strong></div>
          <div class="text-zw-mute">推荐动作：先查看差异字段，再进入 P3 发起标准复用申请。</div>
        </div>
        <div class="mt-5 flex gap-3">
          <a href="#/p3-request-flow" class="gov-btn gov-btn-primary">进入标准复用申请</a>
          <a href="#/p7-zones-pack/zone/${zoneId}" class="gov-btn gov-btn-secondary">查看所属专题包</a>
        </div>
      `)}
    </div>
  `;
  return shell('p2', main);
};

PAGES.requestFlow = function () {
  const request = requestById('REQ-2026-04-25-0011');
  const draft = request.aiDraft;
  const role = window.STATE.role;
  const isGrassroots = role === 'r3' || role === 'r4';
  const isReviewer = role === 'r2' || role === 'r5';
  const statusLabel = requestStatusLabel(request, role);
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P3 申请 / 审批 / 跟踪' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P3 申请 / 审批 / 跟踪</div>
          <div class="page-hero-subtitle">一条链同时承载 R1 发起、R2 准入、R3/R4 补录、R5 汇总确认。</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
      <div class="mt-5">${stepBar(['发现模板', '复用判断', '受控准入', '预填补录', '审核汇总', '回流共享'], requestStepIndex(request, role))}</div>
    </div>

    ${renderInlineSummary(draft.summary, ['查看已预填字段', '查看差异补录', '查看自动汇总预估'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('标准复用申请', '不再从零造表，而是围绕模板覆盖、差异字段和责任边界发起申请', `
          <div class="grid grid-cols-2 gap-4 text-[14px]" data-ai-surface="request-inline-ai">
            ${renderFieldState('复用模板', request.resourceName, '已识别', '作为涉企默认基础对象')}
            ${renderFieldState('模板覆盖率', request.templateCoverage, '已识别', '多数基础字段可自动带出')}
            <div class="col-span-2">${renderFieldState('业务目标', request.purpose, '已识别', '先复用模板，再补现场差异')}</div>
            <div class="col-span-2">${renderFieldState('差异字段责任边界', '经营状态 / 走访时间 / 现场备注', request.status === 'need-fix' ? '待补正' : '待确认', '需明确由 R3/R4 补录，R5 只处理异常项')}</div>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-4">
            ${panel('已预填字段示意', '这些字段来自共享资源池或模板版本，不需要基层重复录入', `<div class="text-[14px] leading-7 text-zw-mute">${request.prefilledFields.map(item => `• ${item.label}：${item.value}（${item.source}）`).join('<br/>')}</div>`)}
            ${panel('差异补录字段', '只保留现场性、动态性强的字段进入基层补录', `<div class="text-[14px] leading-7 text-zw-mute">${request.diffFields.map(item => `• ${item.label}：${item.reason}（${item.owner}）`).join('<br/>')}</div>`)}
          </div>
          <div class="mt-4 text-[14px] leading-7 text-zw-ink" data-ai-surface="request-summary-inline">可审摘要：${draft.summary}</div>
          <div class="mt-5 flex gap-3 flex-wrap">
            ${requestActionBar(request, role)}
          </div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel(isGrassroots ? '基层补录提示' : '准入 / 汇总侧栏', isGrassroots ? 'R3/R4 只看已带出字段和待补项，不需要理解治理后台。' : 'R2 看是否属于重复要数；R5 看异常项与自动汇总结果。', `
          <div class="text-[14px] leading-7 text-zw-ink">${isGrassroots ? '本任务已自动带出企业基础字段，你只需核对经营状态、最近走访时间和现场备注。' : isReviewer ? '当前重点不是重新人工拼表，而是确认差异字段边界、异常项和自动汇总是否可直接通过。' : draft.risk}</div>
          <div class="mt-4 text-[13px] text-zw-mute leading-7">${isReviewer ? request.summaryResult.note : '系统判断：新增整表必要性低，真正要确认的是差异字段和回流要求。'}</div>
        `)}
        ${panel('当前链路队列', '不同角色进入同一条链，不再分裂成多套页面', `
          <div class="gov-list text-[14px]">
            ${window.MOCK_REQUESTS.map(item => `
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
  const role = window.STATE.role;
  const isGrassroots = role === 'r3' || role === 'r4';
  const diffState = item.status === 'supplementing' ? '待补录' : item.status === 'summary-pending' || item.status === 'completed' ? '已补录' : item.status === 'need-fix' ? '待补正' : '待确认';
  const diffNote = field => item.status === 'summary-pending' || item.status === 'completed'
    ? `${field.reason} · ${field.owner} · ${field.state || '已补录'}`
    : `${field.reason} · ${field.owner}`;
  const main = `
    ${crumbs([{ label: 'P3 申请 / 审批 / 跟踪', href: '#/p3-request-flow' }, { label: item.id }])}
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
        ${panel('回执与审计', 'audit / chain 是默认能力，不是可选后台信息', `
          <div class="space-y-3 text-[14px]">
            <div><span class="audit-chip">audit_id</span> <strong>${item.auditId}</strong></div>
            <div><span class="audit-chip">chain_anchor</span> <strong>${item.chainAnchor}</strong></div>
            <div class="text-zw-mute">依据：${item.aiStatus.evidence.join('；')}</div>
          </div>
        `)}
        ${panel('回流说明', '让基层补录结果自然回到共享资产池，而不是停在一次性任务上', `
          <div class="text-[14px] leading-7 text-zw-ink">${item.returnFlow.map(line => `• ${line}`).join('<br/>')}</div>
        `)}
        ${panel(isGrassroots ? '当前补录动作' : '当前链路动作', isGrassroots ? '基层只在补录阶段执行责任写动作，其余时间只读跟踪。' : '申请方只在补正 / 重提阶段执行动作，其余阶段查看状态与证据。', `
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
  const isSummaryStage = request.status === 'summary-pending' || request.status === 'completed';
  const statusLabel = requestStatusLabel(request, window.STATE.role);
  const actionTitle = isSummaryStage ? '汇总确认动作' : '准入判定动作';
  const actionSubtitle = isSummaryStage
    ? '自动汇总确认、退回补正、明确驳回都必须由 R5 显式点击。'
    : '是否进入基层补录必须由 R2 显式点击，AI 只能草拟建议。';
  const primaryAction = request.status === 'pending'
    ? `<button onclick="window.ACTIONS.approveRequest('${request.id}')" class="gov-btn gov-btn-primary">通过并下发补录</button>`
    : request.status === 'summary-pending'
      ? `<button onclick="window.ACTIONS.confirmSummary('${request.id}')" class="gov-btn gov-btn-primary">确认自动汇总</button>`
      : `<button onclick="window.ACTIONS.noop('当前阶段没有新的主状态写动作')" class="gov-btn gov-btn-secondary">查看当前说明</button>`;
  const secondaryAction = ['pending', 'summary-pending'].includes(request.status)
    ? `<button onclick="window.ACTIONS.returnForFix('${request.id}')" class="gov-btn gov-btn-warn">退回补正</button>`
    : '';
  const rejectAction = ['pending', 'summary-pending'].includes(request.status)
    ? `<button onclick="window.ACTIONS.rejectRequest('${request.id}')" class="gov-btn gov-btn-danger">驳回</button>`
    : '';
  const main = `
    ${crumbs([{ label: 'P3 申请 / 审批 / 跟踪', href: '#/p3-request-flow' }, { label: '审核 / 汇总详情' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">审核 / 汇总详情 · ${request.id}</div>
          <div class="page-hero-subtitle">R2 看准入与重复要数，R5 看异常项与自动汇总；AI 只给建议，不代决。</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(`${approval.suggestion}。${approval.autoSummary}`, ['查看异常项', '查看自动汇总结果', '查看回流要求'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7 space-y-5">
        ${panel('申请与模板信息', '审批人先判断这是不是“先复用模板再补差异字段”的正确形状', `
          <table class="gov-table">
            <tbody>
              <tr><td>复用对象</td><td>${request.resourceName}</td></tr>
              <tr><td>模板覆盖率</td><td>${request.templateCoverage}</td></tr>
              <tr><td>差异字段</td><td>${request.diffFields.map(item => item.label).join(' / ')}</td></tr>
              <tr><td>申请目标</td><td>${request.purpose}</td></tr>
            </tbody>
          </table>
        `)}
        ${panel(isSummaryStage ? '自动汇总结果与异常项' : '准入判断与差异字段边界', isSummaryStage ? 'R5 只处理异常项与系统自动汇总确认，不再人工拼表。' : 'R2 判断是否进入基层补录，而不是机械转发申请。', `
          <div data-ai-surface="review-summary" class="space-y-4 text-[14px] leading-7">
            <div><strong>${isSummaryStage ? '自动汇总结果' : '准入判断'}</strong><div class="mt-2 text-zw-mute">${request.summaryResult.note}</div></div>
            <div><strong>异常项</strong><div class="mt-2 text-zw-mute">${approval.exceptionItems.map(item => `• ${item}`).join('<br/>')}</div></div>
            <div><strong>回流候选</strong><div class="mt-2 text-zw-mute">${request.returnFlow.map(item => `• ${item}`).join('<br/>')}</div></div>
          </div>
        `)}
        ${renderDraftCard('AI 建议的审批 / 汇总意见草稿', [approval.draftNote], '草稿只帮助你更快进入结构化决策，不会替你写入最终结果。')}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('依据与风险', '把建议、风险和影响贴近动作区，不做大面积炫技说明', `
          <div data-ai-surface="approval-inline-ai" class="space-y-4 text-[14px] leading-7">
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
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P4 交付 / 交换 / 回流' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P4 交付 / 交换 / 回流</div>
          <div class="page-hero-subtitle">不只看交付是否完成，还看补录结果如何自动汇总并回流共享资产池。</div>
        </div>
        <div class="page-meta">Journey 4–6 · 补录 / 汇总 / 回流</div>
      </div>
    </div>

    ${panel('任务队列', '任务状态同时表达：是正常预填闭环、准入拦截，还是审计熔断保护', `
      <div data-ai-surface="delivery-queue" class="space-y-4">
        ${window.MOCK_DELIVERY_TASKS.map(task => {
          const request = requestById(task.requestId);
          const requestReady = request && request.status === 'completed';
          const backflowReady = requestReady && task.backflow.status !== '已确认';
          const statusLabel = deliveryStatusLabel(task);
          const actionHint = task.status === 'supplementing'
            ? '当前等待基层完成差异补录。'
            : task.status === 'reconciling' && backflowReady
              ? '汇总已完成，当前等待供给侧确认是否纳入模板。'
              : task.backflow.status === '已确认'
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
                  <p class="text-sm mt-3">${task.note}</p>
                  <div class="mt-2 text-[13px] text-zw-mute leading-7">回流状态：${task.backflow.status} · ${actionHint}</div>
                  <div class="mt-4 text-[13px] text-zw-mute leading-7" data-ai-surface="delivery-inline-ai">当前判断：${task.aiSummary.summary}</div>
                </div>
                <div class="text-right text-xs text-zw-mute">最近更新<br/><strong class="text-zw-ink">${task.updatedAt}</strong></div>
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
  const request = requestById(task.requestId);
  const ai = task.aiSummary;
  const statusLabel = deliveryStatusLabel(task);
  const canConfirmBackflow = request && request.status === 'completed' && task.backflow.status !== '已确认';
  const main = `
    ${crumbs([{ label: 'P4 交付 / 交换 / 回流', href: '#/p4-delivery-exchange' }, { label: task.id }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${task.name}</div>
          <div class="page-hero-subtitle">${task.channel} · ${task.owner} · request_id ${task.requestId}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(ai.summary, [ai.nextAction])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        ${panel('任务时间线', '关键状态必须可追踪，不能只在后台任务系统里存在', `
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
        ${panel('回流共享说明', '让用户看清这次补录沉淀成了什么，下次如何被直接复用', `
          <div class="grid grid-cols-2 gap-4 text-[14px] leading-7">
            <div><strong>回流候选对象</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateObject}</div></div>
            <div><strong>回流状态</strong><div class="mt-2 text-zw-mute">${task.backflow.status}</div></div>
            <div class="col-span-2"><strong>候选字段</strong><div class="mt-2 text-zw-mute">${task.backflow.candidateFields.length ? task.backflow.candidateFields.join(' / ') : '—'}</div></div>
            <div class="col-span-2 text-zw-mute">${task.backflow.note}</div>
          </div>
        `)}
      </section>
      <aside class="col-span-4 space-y-5">
        ${panel('当前处置建议', 'AI 负责解释和衔接，不代替人工做回流生效决定', `
          <div data-ai-surface="delivery-detail-inline" class="text-[14px] leading-7 text-zw-ink">${ai.nextAction}</div>
          <div class="mt-4 text-[13px] text-zw-mute">原因：${ai.cause}</div>
          <div class="mt-2 text-[13px] text-zw-mute">影响：${ai.impact}</div>
        `)}
        ${panel('当前链路动作', '只有在自动汇总已被确认后，R6 / R7 才能显式确认回流生效。', `
          <div class="space-y-3 text-[13px] text-zw-mute leading-7">
            <div>申请状态：${requestStatusLabel(request, window.STATE.role)}</div>
            <div>回流候选：${task.backflow.status}</div>
          </div>
          <div class="mt-5 flex gap-3 flex-wrap">
            ${canConfirmBackflow
              ? `<button onclick="window.ACTIONS.confirmBackflow('${task.id}')" class="gov-btn gov-btn-primary">确认回流共享</button>`
              : `<button onclick="window.ACTIONS.noop('当前还未满足回流确认条件：需先完成汇总确认，且不能重复确认已生效回流。')" class="gov-btn gov-btn-secondary">查看回流门槛</button>`}
            <a href="#/p5-provider" class="gov-btn gov-btn-secondary">查看模板治理</a>
          </div>
        `)}
      </aside>
    </div>
  `;
  return shell('p4', main);
};


PAGES.provider = function () {
  const ai = window.MOCK_PROVIDER.aiGovernance;
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P5 提供方管理' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P5 提供方管理</div>
          <div class="page-hero-subtitle">R6/R7 管的不是抽象后台项，而是会被前台反复复用的默认能力底座。</div>
        </div>
        <div class="page-meta">Journey 6 · 模板治理与发布</div>
      </div>
    </div>

    ${statCards(window.MOCK_PROVIDER.overview)}

    <div class="grid grid-cols-3 gap-5">
      ${panel('目录治理', '先把默认复用入口和版本说明治理清楚', `
        <div class="gov-list text-sm">${window.MOCK_PROVIDER.catalogs.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.owner} · ${item.issue}</div></div>${statusPill(item.status)}</div>`).join('')}</div>
      `)}
      ${panel('资源 / 模板治理', '模板与治理视图放在同一供给侧面，不再切成两套后台', `
        <div class="gov-list text-sm">${window.MOCK_PROVIDER.resources.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">${item.type} · 更新于 ${item.updatedAt}</div></div>${statusPill(item.status)}</div>`).join('')}</div>
      `)}
      ${panel('服务治理', '预填与回流服务保持在线，是前台主旅程可复用的基础', `
        <div class="gov-list text-sm">${window.MOCK_PROVIDER.services.map(item => `<div class="gov-list-row"><div><div class="row-title">${item.name}</div><div class="row-meta mt-2">QPS ${item.qps} · ${item.note}</div></div>${statusPill(item.status)}</div>`).join('')}</div>
      `)}
    </div>

    ${panel('治理重点', 'AI 只帮排序和归纳，不替台账管理员做最终发布动作', `
      <div data-ai-surface="provider-governance" class="text-[14px] leading-7 text-zw-ink">${ai.summary}</div>
      <div class="mt-4 text-[13px] text-zw-mute leading-7">${ai.priorities.map(item => `• ${item}`).join('<br/>')}</div>
    `)}
  `;
  return shell('p5', main);
};

PAGES.complianceOps = function () {
  const metrics = window.MOCK_DASHBOARD.burdenMetrics;
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P6 合规与运营' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P6 合规与运营</div>
          <div class="page-hero-subtitle">R8 看的不是技术日志，而是重复要数有没有下降、哪些字段仍在反复补录。</div>
        </div>
        <div class="page-meta">Journey 7 · 减负治理与证据</div>
      </div>
    </div>

    ${panel('减负指标', '把治理结果直接呈现在前面，再允许继续钻取证据和工单链路', `
      <div class="grid grid-cols-4 gap-4">
        ${metrics.map(item => `<div class="gov-stat-card"><div class="gov-stat-label">${item.label}</div><div class="gov-stat-value">${item.value}</div><div class="mt-2 text-[12px] text-zw-mute">${item.trend}</div></div>`).join('')}
      </div>
    `)}

    ${renderInlineSummary(window.MOCK_AUDIT_AI.summary, ['查看重复要数争议', '查看差异补录热区', '查看审计回放'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-4 space-y-5">
        ${panel('争议与绕行', '先看哪些行为会增加基层负担，再进入证据核查', `
          <div class="space-y-3 text-[14px]">
            ${window.MOCK_DISPUTES.map(item => `<a href="#/p6-compliance-ops/dispute/${item.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between"><div class="panel-title text-[16px]">${item.title}</div>${statusPill(item.status)}</div><div class="row-meta mt-2">${item.id} · ${item.owner}</div><div class="mt-3 text-[13px] text-zw-mute leading-7" data-ai-surface="dispute-inline-ai">初步判断：${item.aiSummary}</div></div></a>`).join('')}
          </div>
        `)}
        ${panel('告警 → 工单 → 知识建议', '治理链必须可追踪，而不是只剩一个抽象告警数', `
          <div class="space-y-3 text-[14px]">
            ${window.MOCK_ALERTS.map(alert => {
              const ticket = window.MOCK_TICKETS.find(item => item.id === alert.linkedTicket);
              const kb = window.MOCK_KNOWLEDGE_ARTICLES.find(item => item.id === alert.knowledge);
              return `<div class="panel"><div class="panel-body"><div class="flex items-center justify-between"><div class="panel-title text-[16px]">${alert.title}</div>${statusPill('处理中')}</div><div class="row-meta mt-2">责任人：${alert.owner}</div><div class="mt-3 leading-7">${alert.summary}</div><div class="mt-3 text-[13px] text-zw-mute">工单：${ticket ? ticket.title : '—'}</div><div class="mt-1 text-[13px] text-zw-mute">知识建议：${kb ? kb.title : '—'}</div><div class="mt-3 text-[13px] text-zw-mute leading-7" data-ai-surface="alert-inline-ai">研判：${alert.aiAdvice}</div></div></div>`;
            }).join('')}
          </div>
        `)}
      </section>
      <section class="col-span-8 space-y-5">
        ${panel('审计回放', '原始证据必须始终保持主位，AI 摘要只辅助阅读', `
          <table class="gov-table">
            <thead><tr><th>时间</th><th>事件</th><th>目标</th><th>主体</th><th>结果</th></tr></thead>
            <tbody>
              ${window.MOCK_AUDIT_EVENTS.map(item => `<tr><td>${item.time}</td><td>${item.type}</td><td>${item.target}</td><td>${item.actor}</td><td>${statusPill(item.result)}</td></tr>`).join('')}
            </tbody>
          </table>
        `)}
        ${panel('当前治理判断', '把调查摘要贴近证据区，帮助 R8 判断是否需要制度或模板调整', `
          <div data-ai-surface="compliance-inline-ai" class="text-[14px] leading-7 text-zw-ink">${window.MOCK_AUDIT_AI.summary}</div>
          <div class="mt-4 text-[13px] text-zw-mute leading-7">${window.MOCK_AUDIT_AI.evidence.map(item => `• ${item}`).join('<br/>')}</div>
        `)}
      </section>
    </div>
  `;
  return shell('p6', main);
};

PAGES.disputeDetail = function (id) {
  const item = disputeById(id);
  const main = `
    ${crumbs([{ label: 'P6 合规与运营', href: '#/p6-compliance-ops' }, { label: item.id }])}
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
        <div class="text-[14px] leading-7 text-zw-ink">${item.aiSummary}</div>
      </div>
    </div>

    ${panel('争议处理时间线', '明确说明为什么属于重复要数、口径争议或异常补录，不把治理变成技术调试', `
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
        <button onclick="window.ACTIONS.noop('模拟受理 / 核查 / 审查 / 结论动作')" class="gov-btn gov-btn-primary">推进调查</button>
        <button onclick="window.ACTIONS.noop('模拟升级为模板治理或制度治理动作')" class="gov-btn gov-btn-secondary">升级治理</button>
      </div>
    `)}
  `;
  return shell('p6', main);
};

PAGES.zonesPack = function () {
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P7 共享专区 / 专题包' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P7 共享专区 / 专题包</div>
          <div class="page-hero-subtitle">把法人单位基础信息模板做成 zw-brain 前台可发现、可理解、可消费的专题资产。</div>
        </div>
        <div class="page-meta">J1 / J4 · 前台专题入口</div>
      </div>
    </div>

    ${panel('专题包列表', '前台看到的是高频场景入口，不是后台标准管理系统', `
      <div class="grid grid-cols-3 gap-5">
        ${window.MOCK_ZONES.map(zone => `<a href="#/p7-zones-pack/zone/${zone.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-2"><div class="panel-title text-[15px]">${zone.name}</div>${statusPill(zone.status)}</div><p class="text-sm mt-3 leading-7">${zone.desc}</p><div class="mt-4 text-xs text-zw-mute">资产 ${zone.assets.length} 项 · 订阅部门 ${zone.subscribers}</div><div class="mt-4 text-[13px] text-zw-mute leading-7">适用问题：${zone.aiGuide}</div></div></a>`).join('')}
      </div>
    `)}
  `;
  return shell('p7', main);
};

PAGES.zoneDetail = function (id) {
  const zone = zoneById(id);
  const main = `
    ${crumbs([{ label: 'P7 共享专区 / 专题包', href: '#/p7-zones-pack' }, { label: zone.name }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${zone.name}</div>
          <div class="page-hero-subtitle">${zone.desc}</div>
        </div>
        ${statusPill(zone.status)}
      </div>
    </div>

    ${renderInlineSummary('专题包的价值，是把高频对象、复用入口、订阅与信任信息收敛到同一个前台面。', zone.nextActions)}

    <div class="grid grid-cols-2 gap-5">
      ${panel('包含资产', '让用户一眼看到这个专题包里有什么可以直接用', `<ul class="space-y-2 text-sm list-disc pl-5">${zone.assets.map(item => `<li>${item}</li>`).join('')}</ul>`)}
      ${panel('信任信息与价值', '说明它为什么能作为默认入口，而不是后台配置对象', `
        <ul class="space-y-2 text-sm list-disc pl-5">
          ${zone.trust.map(item => `<li>${item}</li>`).join('')}
          <li>可用动作：查看详情、发起复用申请、订阅专区更新。</li>
        </ul>
        <div class="mt-5"><button onclick="window.ACTIONS.noop('模拟订阅专题包或作为模板复用入口')" class="gov-btn gov-btn-primary">订阅 / 作为默认入口</button></div>
      `)}
    </div>
  `;
  return shell('p7', main);
};

PAGES.integrationAdmin = function () {
  const main = `
    ${crumbs([{ label: 'P1 工作台', href: '#/p1-workbench' }, { label: 'P8 平台接入与扩展中心' }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">P8 平台接入与扩展中心</div>
          <div class="page-hero-subtitle">这里只给 R7 用：审核 manifest / schema / 暴露范围，不让外部辅助接管主状态写权。</div>
        </div>
        <div class="page-meta">S2 · 管理员控制面</div>
      </div>
    </div>

    ${renderInlineSummary('当前最值得先处理的是 ledger.entity.base.read；它符合“只读辅助”定位，但还要补齐 tenant_scope。', ['查看待审能力包', '查看暴露范围', '查看退回草案'])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-7">
        ${panel('能力包注册队列', '平台 baseline 不依赖外部包；这里审核的是增益能力如何回注册', `
          <div class="space-y-3 text-sm">
            ${window.MOCK_CAPABILITY_PACKAGES.map(item => `<a href="#/p8-integration-admin/package/${item.id}" class="panel card-hover block"><div class="panel-body"><div class="flex items-center justify-between gap-3"><div class="panel-title text-[15px]">${item.slug}</div>${statusPill(packageStatusLabel(item))}</div><div class="row-meta mt-2">${item.source}</div><div class="mt-3">${item.desc}</div><div class="mt-2 text-[13px] text-zw-mute leading-7">审核状态：${packageStatusLabel(item)} · 暴露面 ${item.exposure.join(' / ')}</div><div class="mt-3 text-[13px] text-zw-mute leading-7" data-ai-surface="package-inline-ai">系统审核意见：${item.aiReview.summary}</div></div></a>`).join('')}
          </div>
        `)}
      </section>
      <aside class="col-span-5 space-y-5">
        ${panel('最小控制面字段', '控制面必须存在，但要纤薄且只服务生效边界', `
          <ul class="space-y-2 text-sm list-disc pl-5">
            <li>slug / version / source</li>
            <li>tenant_scope / auth_policy / audit_class</li>
            <li>human_confirmation_required</li>
            <li>compatibility / exposure</li>
            <li>side effects / rollback_target</li>
          </ul>
        `)}
        ${panel('审核门槛提示', '允许外部包存在，但始终限制在统一 capability 契约和只增益边界内。', `
          <div data-ai-surface="integration-inline-ai" class="text-[14px] leading-7 text-zw-ink">外部包只能做 draft / explain / summarize / recommend / adapter 这类辅助动作；凡是企图声明 submit、review-and-decide、reconcile-receipt、register-version、apply-tenant-policy 等责任写动作，一律不能通过注册。</div>
        `)}
      </aside>
    </div>
  `;
  return shell('p8', main);
};

PAGES.packageDetail = function (id) {
  const item = packageById(id);
  const ai = item.aiReview;
  const statusLabel = packageStatusLabel(item);
  const canApprove = item.status !== 'approved' && item.status !== 'rejected';
  const canReturn = item.status !== 'approved' && item.status !== 'rejected';
  const canReject = item.status !== 'approved' && item.status !== 'rejected';
  const main = `
    ${crumbs([{ label: 'P8 平台接入与扩展中心', href: '#/p8-integration-admin' }, { label: item.slug }])}
    <div class="page-hero">
      <div class="page-toolbar">
        <div>
          <div class="page-hero-title">${item.slug}</div>
          <div class="page-hero-subtitle">${item.source} · 暴露面：${item.exposure.join(' / ')}</div>
        </div>
        ${statusPill(statusLabel)}
      </div>
    </div>

    ${renderInlineSummary(ai.summary, ['查看缺失项', '查看安全项', '查看退回意见'])}

    <div class="grid grid-cols-2 gap-5">
      ${panel('能力包信息', '审核重点是它是否保持“只增益，不越权”', `
        <table class="gov-table"><tbody>
          <tr><td>审核状态</td><td>${statusLabel}</td></tr>
          <tr><td>审计级别</td><td>${item.auditClass}</td></tr>
          <tr><td>人工确认</td><td>${item.requiresHuman ? '需要' : '不需要'}</td></tr>
          <tr><td>描述</td><td>${item.desc}</td></tr>
        </tbody></table>
        <div class="mt-4 text-[13px] text-zw-mute leading-7">缺失项：${ai.missing.length ? ai.missing.join('；') : '无'}</div>
        <div class="mt-2 text-[13px] text-zw-mute leading-7">安全项：${ai.safe.length ? ai.safe.join('；') : '—'}</div>
      `)}
      ${renderDraftCard('AI 草拟的审核意见', [ai.draft], '审核助手只给草案；批准、退回和驳回仍由管理员点击确认。')}
    </div>
    ${panel('审核动作', '保持人工确认边界', `
      <div class="flex gap-3 flex-wrap">
        ${canApprove
          ? `<button onclick="window.ACTIONS.approvePackage('${item.id}')" class="gov-btn gov-btn-primary">批准</button>`
          : `<button onclick="window.ACTIONS.noop('当前能力包已处于终态，不再重复批准。')" class="gov-btn gov-btn-secondary">查看当前状态</button>`}
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

PAGES.dashboard = function () {
  const d = window.MOCK_DASHBOARD;
  return `
    <div class="dash-stage">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 class="text-3xl font-semibold">政务数据大脑 · K12 指挥中心大屏</h1>
          <div class="text-sm opacity-80 mt-1">只读消费治理结果与主旅程事实；关注减负、绕行和模板升级，不进入业务办理。</div>
        </div>
        <div class="flex items-center gap-3 text-xs">
          <span>主大脑 ${window.STATE.brainOutage ? '△ 快照模式' : '✓ 正常'}</span>
          <button onclick="window.ACTIONS.toggleOutage()" class="gov-btn gov-btn-secondary !bg-white/10 !border-white/20 !text-white hover:!bg-white/16">模拟主大脑故障</button>
        </div>
      </div>
      ${window.STATE.brainOutage ? '<div class="dash-snapshot-banner">当前为快照模式：主大脑故障不影响大屏继续展示最近一次可用快照，但所有数字停止刷新。</div>' : ''}
      <div class="grid grid-cols-5 gap-4 mb-4">
        <div class="dash-kpi"><div class="dash-label">今日闭环任务</div><div class="dash-num text-4xl mt-2">${d.summary.flowToday}</div></div>
        <div class="dash-kpi"><div class="dash-label">Skill QPS</div><div class="dash-num text-4xl mt-2">${d.summary.qps}</div></div>
        <div class="dash-kpi"><div class="dash-label">在线 Agent</div><div class="dash-num text-4xl mt-2">${d.summary.agentsOnline}</div></div>
        <div class="dash-kpi"><div class="dash-label">异常告警</div><div class="dash-num text-4xl mt-2">${d.summary.alerts}</div></div>
        <div class="dash-kpi"><div class="dash-label">国家通道</div><div class="dash-num text-3xl mt-3">${d.summary.national}</div></div>
      </div>
      <div class="grid grid-cols-4 gap-4 mb-4">
        ${d.burdenMetrics.map(item => `<div class="dash-kpi"><div class="dash-label">${item.label}</div><div class="dash-num text-2xl mt-3">${item.value}</div><div class="text-xs opacity-75 mt-2">${item.trend}</div></div>`).join('')}
      </div>
      <div class="grid grid-cols-3 gap-4">
        <div class="dash-card col-span-2">
          <div class="text-sm mb-3">黄金链路闭环趋势</div>
          <div id="dash-chart" style="height: 320px"></div>
        </div>
        <div class="dash-card">
          <div class="text-sm mb-3">指挥辅助结论</div>
          <div class="text-xl font-semibold leading-8">${d.suggestions.title}</div>
          <p class="text-[14px] opacity-85 mt-3 leading-7">${d.suggestions.body}</p>
          <div class="mt-4 text-[13px] opacity-80">责任人：${d.suggestions.owner}</div>
          <div class="mt-2 text-[13px] opacity-80">建议动作：${d.suggestions.nextAction}</div>
          <div class="mt-4 space-y-2 text-[13px] opacity-75">${d.suggestions.evidence.map(item => `<div>• ${item}</div>`).join('')}</div>
          <a href="#/dashboard/alert/AL-2026-04-25-002" class="inline-block mt-5 text-sm underline">查看异常钻取</a>
        </div>
      </div>
    </div>`;
};

PAGES.dashboard_onMount = function () {
  if (!window.echarts || !document.getElementById('dash-chart')) return;
  const chart = window.echarts.init(document.getElementById('dash-chart'));
  chart.setOption({
    xAxis: { type: 'category', data: window.MOCK_DASHBOARD.trendHours, axisLabel: { color: '#c7d7ff' } },
    yAxis: { type: 'value', axisLabel: { color: '#c7d7ff' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } },
    grid: { left: 32, right: 16, top: 24, bottom: 24 },
    series: [{ type: 'line', data: window.MOCK_DASHBOARD.trendValues, smooth: true, lineStyle: { color: '#8dc1ff', width: 3 }, itemStyle: { color: '#8dc1ff' }, areaStyle: { color: 'rgba(141,193,255,0.18)' } }],
    tooltip: { trigger: 'axis' }
  });
};

PAGES.dashboardAlert = function (id) {
  const alert = window.MOCK_ALERTS.find(item => item.id === id) || window.MOCK_ALERTS[0];
  const ticket = window.MOCK_TICKETS.find(item => item.id === alert.linkedTicket);
  const kb = window.MOCK_KNOWLEDGE_ARTICLES.find(item => item.id === alert.knowledge);
  return `
    <div class="dash-stage">
      <div class="dash-card max-w-5xl mx-auto">
        <div class="flex items-center justify-between gap-4">
          <div>
            <div class="text-xs opacity-70">K12 异常钻取</div>
            <h1 class="text-3xl font-semibold mt-2">${alert.title}</h1>
          </div>
          <a href="#/dashboard" class="text-sm underline">返回大屏</a>
        </div>
        <div class="dash-drill mt-6">
          <div>
            <div class="text-xs opacity-70 mb-2">告警摘要</div>
            <div class="text-sm leading-7">${alert.summary}</div>
            <div class="text-xs opacity-70 mt-5 mb-2">自动诊断</div>
            <div class="text-sm leading-7">${alert.diagnosis}</div>
            <div class="text-xs opacity-70 mb-2">系统研判摘要</div>
            <div class="text-[14px] leading-7">${alert.aiAdvice}</div>
          </div>
          <div>
            <div class="text-xs opacity-70 mb-2">关联工单</div>
            <div class="text-sm leading-7">${ticket ? ticket.title : '—'} · ${ticket ? ticket.status : '—'}</div>
            <div class="text-xs opacity-70 mt-5 mb-2">知识建议</div>
            <div class="text-sm leading-7">${kb ? kb.summary : '—'}</div>
            <div class="text-xs opacity-70 mt-5 mb-2">责任链路</div>
            <div class="text-sm leading-7">责任人：${alert.owner}</div>
          </div>
        </div>
      </div>
    </div>`;
};
