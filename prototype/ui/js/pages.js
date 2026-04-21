/* ---------------------------------------------------------------------------
   政务大脑 GATE-1 原型 · 页面渲染函数（vanilla）
   每个页面返回 HTML 字符串；如需 mount 后初始化（ECharts / 事件绑定），
   多导出一个同名 + "_onMount" 函数，由 app.js dispatch 后自动调用。
   --------------------------------------------------------------------------- */

window.PAGES = {};

// 通用：面包屑
function crumbs(items) {
  return `
    <nav class="text-xs text-zw-mute mb-4 flex items-center gap-1.5">
      ${items.map((it, i) => i === items.length - 1
        ? `<span class="text-zw-ink">${it.label}</span>`
        : `<a href="${it.href}" class="hover:text-zw-primary">${it.label}</a><span class="opacity-40">/</span>`
      ).join('')}
    </nav>`;
}

// 通用：步骤指示
function stepBar(steps, activeIdx) {
  return `
    <div class="flex items-center gap-2 mb-6 text-xs text-zw-mute">
      ${steps.map((s, i) => `
        <span class="step-dot ${i < activeIdx ? 'done' : i === activeIdx ? 'now' : 'todo'}">${i < activeIdx ? '✓' : i + 1}</span>
        <span class="${i === activeIdx ? 'text-zw-ink font-medium' : ''}">${s}</span>
        ${i < steps.length - 1 ? '<span class="opacity-30">───</span>' : ''}
      `).join('')}
    </div>`;
}

// ============================================================
// 通用：主大脑域 sidebar shell
// 5 个一级条目（§7.1 不变） + 二级 page 链接，
// 把 §7.3 全部 10 页都挂到同一个左侧导航上。
// activeKey 控制当前高亮：'workbench' | 'search' | 'manage' | 'review'
//   | 'exchange' | 'dispute' | 'compliance' | 'skill-market' | 'ops'
//   | 'zones' | 'request' | 'settings'
// ============================================================
function brainShell(activeKey, mainHtml) {
  const role = window.STATE.role;
  const reviewBadge   = (role === 'admin' || role === 'platform') ? window.MOCK_TODO_REVIEWS.length : 0;
  const proposalBadge = (role === 'platform') ? window.MOCK_SKILL_PROPOSALS.filter(p => p.status === 'pending').length : 0;
  const disputeOpen   = window.MOCK_DISPUTES.filter(d => d.status === 'open' || d.status === 'escalated').length;

  // 5 个一级 group · 共 12 个二级条目（覆盖 §7.3 的 10 个核心页 + 工作台 + 设置）
  const groups = [
    {
      key: 'workbench', label: '工作台', icon: '◉', items: [
        { key: 'workbench', label: '我的工作台', href: '#/' },
      ]
    },
    {
      key: 'data', label: '数据', icon: '◇', items: [
        { key: 'search',  label: '数据检索',  href: '#/search', desc: 'K3' },
        { key: 'manage',  label: '资源 / 目录 / 服务', href: '#/manage', desc: 'K1+K2+K3', roles: ['op','admin','platform'] },
        { key: 'zones',   label: '共享专区',  href: '#/zones',  desc: 'K11' },
      ]
    },
    {
      key: 'tasks', label: '任务', icon: '◧', items: [
        { key: 'request',  label: '我的申请', href: '#/' },
        { key: 'review',   label: '申请审批', href: '#/', desc: 'K4', badge: reviewBadge,   roles: ['admin','platform'] },
        { key: 'exchange', label: '数据交换', href: '#/exchange', desc: 'K5', roles: ['op','admin','platform'] },
        { key: 'dispute',  label: '异议处理', href: '#/dispute',  desc: 'K8', badge: disputeOpen },
      ]
    },
    {
      key: 'gov', label: '治理', icon: '◔', items: [
        { key: 'compliance',   label: '合规 / 审计回溯', href: '#/compliance',  desc: 'K8/K9', roles: ['admin','platform','leader'] },
        { key: 'skill-market', label: 'Skill 市场',     href: '#/skill-market', badge: proposalBadge },
        { key: 'ops',          label: '平台运营面板',    href: '#/ops',          roles: ['platform','leader'] },
      ]
    },
    {
      key: 'settings', label: '设置', icon: '◌', items: [
        { key: 'settings', label: '账户与组织', href: '#/' },
      ]
    },
  ];

  // 当前 activeKey 落在哪个 group
  const activeGroup = groups.find(g => g.items.some(i => i.key === activeKey));
  const activeGroupKey = activeGroup ? activeGroup.key : 'workbench';

  return `
    <div class="grid grid-cols-12 gap-6">
      <aside class="col-span-2">
        <div class="bg-white rounded-lg border border-zw-line p-2.5 sticky top-20">
          ${groups.map(g => {
            const isActiveGroup = g.key === activeGroupKey;
            // 单一二级条目时直接展示为一级（避免冗余）
            if (g.items.length === 1) {
              const it = g.items[0];
              const isActive = it.key === activeKey;
              return `
                <a href="${it.href}" class="block px-3 py-2 rounded text-sm ${isActive ? 'bg-zw-primary text-white' : 'text-zw-ink hover:bg-zw-bg'}">
                  <span class="inline-block w-3 text-xs opacity-60 mr-1">${g.icon}</span>${g.label}
                </a>`;
            }
            return `
              <div class="${isActiveGroup ? '' : ''}">
                <div class="px-3 py-2 text-xs ${isActiveGroup ? 'text-zw-primary font-semibold' : 'text-zw-mute'}">
                  <span class="inline-block w-3 opacity-60 mr-1">${g.icon}</span>${g.label}
                </div>
                <div class="ml-1 mb-1.5">
                  ${g.items.map(it => {
                    const isActive   = it.key === activeKey;
                    const allowed    = !it.roles || it.roles.indexOf(role) !== -1;
                    const lockBadge  = !allowed ? `<span class="text-[9px] ml-1 text-zw-mute opacity-70">🔒</span>` : '';
                    const numBadge   = it.badge && it.badge > 0 ? `<span class="text-[9px] ml-1 px-1 rounded bg-red-500 text-white">${it.badge}</span>` : '';
                    const descBadge  = it.desc ? `<span class="text-[9px] ml-1 opacity-50">${it.desc}</span>` : '';
                    return `
                      <a href="${allowed ? it.href : '#'}"
                         ${allowed ? '' : 'onclick="event.preventDefault();window.UI.toast(\'当前角色「' + roleLabel(role) + '」无访问权限 — 验证 §3.1 K10 ACL\',\'info\')"'}
                         class="flex items-center justify-between px-3 py-1.5 rounded text-xs
                                ${isActive ? 'bg-zw-primary text-white' :
                                  allowed   ? 'text-zw-ink hover:bg-zw-bg' :
                                              'text-zw-mute cursor-not-allowed opacity-60'}">
                        <span>${it.label}${descBadge}${lockBadge}</span>
                        ${numBadge}
                      </a>`;
                  }).join('')}
                </div>
              </div>`;
          }).join('')}
          <p class="text-[10px] text-zw-mute mt-3 px-3 leading-relaxed border-t border-zw-line pt-3">
            5 个一级条目 · 12 个二级条目 · 验证 §7.1：拒绝复刻旧平台 20+ 子系统菜单
          </p>
        </div>
      </aside>

      <section class="col-span-10 space-y-5">
        ${mainHtml}
      </section>
    </div>`;
}

// ============================================================
// 场景 1：主大脑 WebUI
// ============================================================

// ---- Page 1: 工作台 ----
PAGES.workbench = function () {
  const role = window.STATE.role;
  const myReq = (window.STATE.appliedRequests || []).concat(window.MOCK_REQUESTS);
  const showReviews = role === 'admin' || role === 'platform';
  const main = `
    <div class="bg-white rounded-lg p-5 border border-zw-line">
      <h1 class="text-xl font-semibold mb-1">早上好，${role === 'leader' ? '王副市长' : role === 'platform' ? '王平台管理员' : role === 'agent-dev' ? '赵工（外部 Agent 开发者）' : '李娟'}</h1>
      <p class="text-sm text-zw-mute">今天是 ${new Date().toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })} · 当前身份：<strong class="text-zw-ink">${roleLabel(role)}</strong></p>
    </div>

    ${showReviews ? `
    <div class="bg-white rounded-lg p-5 border border-zw-line">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">我的待办（待审批申请）</h2>
        <a href="#/dispute" class="text-xs text-zw-primary hover:underline">查看异议处理 →</a>
      </div>
      <div class="space-y-2">
        ${window.MOCK_TODO_REVIEWS.map(r => `
          <a href="#/review/${r.id}" class="flex items-center justify-between p-3 bg-zw-bg rounded card-hover">
            <div>
              <div class="text-sm font-medium">${r.dataset} · ${r.id}</div>
              <div class="text-xs text-zw-mute mt-0.5">申请人：${r.applicant} · 提交于 ${r.submittedAt}</div>
            </div>
            ${r.urgent ? '<span class="text-xs px-2 py-0.5 rounded sev-mid">紧急</span>' : ''}
          </a>`).join('')}
      </div>
    </div>` : ''}

    <div class="bg-white rounded-lg p-5 border border-zw-line">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">我提交的申请</h2>
        <a href="#/search" class="text-xs text-zw-primary hover:underline">+ 新申请</a>
      </div>
      ${myReq.length === 0 ? '<p class="text-sm text-zw-mute">暂无</p>' : `
      <div class="space-y-2">
        ${myReq.map(r => `
          <a href="#/request/${r.id}" class="block p-3 bg-zw-bg rounded card-hover">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-medium">${r.datasetName} · ${r.id}</div>
                <div class="text-xs text-zw-mute mt-0.5">提交于 ${r.submittedAt} · 用途：${r.purpose}</div>
              </div>
              <span class="text-xs px-2 py-0.5 rounded ${r.status === 'approved' ? 'sev-low' : r.status === 'rejected' ? 'sev-high' : 'sev-mid'}">
                ${r.status === 'approved' ? '已通过' : r.status === 'pending' ? '审批中' : r.status === 'rejected' ? '已驳回' : r.status}
              </span>
            </div>
          </a>`).join('')}
      </div>`}
    </div>

    <div class="bg-white rounded-lg p-5 border border-zw-line">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">快捷入口（覆盖 §7.3 全部 10 个核心场景页）</h2>
      </div>
      <div class="grid grid-cols-3 gap-3 text-sm">
        <a href="#/search"        class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">数据检索</div><div class="text-xs text-zw-mute mt-1">§7.3 #2 · K3</div></a>
        <a href="#/manage"        class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">资源 / 目录 / 服务</div><div class="text-xs text-zw-mute mt-1">§7.3 #3 · K1+K2+K3</div></a>
        <a href="#/exchange"      class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">数据交换任务</div><div class="text-xs text-zw-mute mt-1">§7.3 #5 · K5</div></a>
        <a href="#/dispute"       class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">异议处理</div><div class="text-xs text-zw-mute mt-1">§7.3 #6 · K8</div></a>
        <a href="#/compliance"    class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">合规督导 / 审计回溯</div><div class="text-xs text-zw-mute mt-1">§7.3 #7 · K8/K9</div></a>
        <a href="#/skill-market"  class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">Skill 市场</div><div class="text-xs text-zw-mute mt-1">§7.3 #8 · §6 入口</div></a>
        <a href="#/ops"           class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">平台运营面板</div><div class="text-xs text-zw-mute mt-1">§7.3 #9 · 内部 KPI</div></a>
        <a href="#/zones"         class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">共享专区</div><div class="text-xs text-zw-mute mt-1">§7.3 #10 · K11</div></a>
        <a href="#/dashboard"     class="p-3 bg-zw-bg rounded card-hover"><div class="font-medium">指挥中心大屏</div><div class="text-xs text-zw-mute mt-1">§7.7 · K12</div></a>
      </div>
    </div>

    <div class="bg-white rounded-lg p-5 border border-zw-line">
      <h2 class="font-semibold mb-3">最近浏览的目录</h2>
      <div class="grid grid-cols-3 gap-3">
        ${window.MOCK_DATASETS.map(d => `
          <a href="#/dataset/${d.id}" class="p-3 bg-zw-bg rounded card-hover">
            <div class="text-sm font-medium">${d.name}</div>
            <div class="text-xs text-zw-mute mt-1">${d.provider} · 订阅 ${d.subscriberCount} 部门</div>
          </a>`).join('')}
      </div>
    </div>`;
  return brainShell('workbench', main);
};

// ---- Page 2: 数据检索 ----
PAGES.search = function () {
  const parsed = window.STATE.parsedConditions;
  const q = window.STATE.nlQuery || '';
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '数据检索' }])}

    <div class="bg-white rounded-lg border border-zw-line p-6 mb-5">
      <div class="text-sm text-zw-mute mb-2">试试自然语言：「我要 XX 数据，下周一前」（验证 §7.2 NL 加速器）</div>
      <form id="search-form" class="flex gap-2">
        <input id="search-q" type="text" value="${q}" placeholder="例如：我要市卫健委 2024 年的预防接种数据，下周一前完成"
               class="flex-1 px-4 py-3 rounded border border-zw-line focus:outline-none focus:border-zw-primary text-sm" />
        <button class="px-5 py-3 bg-zw-primary text-white rounded text-sm hover:bg-blue-900">检索</button>
      </form>
    </div>

    ${parsed ? `
    <div class="grid grid-cols-12 gap-5">
      <!-- 左：NL 解析后的结构化条件（核心：用户可校验、可改） -->
      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20">
          <div class="text-xs text-zw-primary font-medium mb-2">NL 加速器解析（你可逐项校验）</div>
          ${parsed.lowConfidence ? `
          <div class="bg-amber-50 border border-amber-200 text-amber-900 text-xs p-2.5 rounded mb-3 leading-relaxed">
            ⚠️ 没识别到关键字段（年份 / 提供方）。建议补充结构化条件，或改写自然语言（如「市卫健委 2024 接种数据」）。
          </div>` : ''}
          <div class="space-y-2 text-sm">
            <div><span class="text-zw-mute text-xs">数据范围：</span><span class="chip ${parsed.lowConfidence ? '' : 'chip-ok'}">${parsed.range}</span></div>
            <div><span class="text-zw-mute text-xs">提供方：</span><span class="chip ${parsed.lowConfidence ? '' : 'chip-ok'}">${parsed.provider}</span></div>
            <div><span class="text-zw-mute text-xs">期望完成：</span><span class="chip chip-ok">${parsed.expectBy}</span></div>
            ${parsed.topic ? `<div><span class="text-zw-mute text-xs">主题：</span><span class="chip chip-ok">${parsed.topic}</span></div>` : ''}
          </div>
          <div class="mt-4 text-[11px] text-zw-mute">
            ✓ 字段可点击修改 ✓ 用户检视后才进入下一步 ✓ 不允许 NL 直接执行写操作（§7.5）
          </div>
        </div>
      </aside>

      <!-- 右：检索结果（按相关度排序） -->
      <section class="col-span-8 space-y-3">
        <div class="text-sm text-zw-mute">匹配 ${window.MOCK_DATASETS.length} 个数据集，按相关度排序</div>
        ${window.MOCK_DATASETS.map((d, i) => `
          <a href="#/dataset/${d.id}" class="block bg-white rounded-lg border border-zw-line p-4 card-hover">
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="font-medium">${d.name}</div>
                <div class="text-xs text-zw-mute mt-1">${d.provider} · ${d.zone} · 上次更新 ${d.updatedAt}</div>
                <p class="text-sm text-zw-ink mt-2 leading-relaxed">${d.desc}</p>
              </div>
              <div class="text-right text-xs text-zw-mute ml-4">
                <div class="text-lg font-semibold text-zw-accent">${(95 - i * 7).toFixed(0)}%</div>
                <div>相关度</div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-3 text-xs text-zw-mute">
              <span>历史通过率 <span class="text-green-600 font-medium">${(d.approvalRate * 100).toFixed(0)}%</span></span>
              <span>·</span>
              <span>已订阅 <span class="text-zw-primary font-medium">${d.subscriberCount}</span> 个部门</span>
            </div>
          </a>`).join('')}
      </section>
    </div>` : `
    <div class="bg-white rounded-lg border border-zw-line p-10 text-center">
      <div class="text-zw-mute text-sm mb-2">输入自然语言，体验 NL 加速器解析效果</div>
      <div class="text-xs text-zw-mute">点上方示例 → 检索按钮，会跳转到带 NL 解析结果的检索页</div>
    </div>`}
  `;
  return brainShell('search', main);
};

PAGES.search_onMount = function () {
  const form = document.getElementById('search-form');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = document.getElementById('search-q').value.trim();
    if (!q) return;
    window.STATE.nlQuery = q;
    // 极简 NL 解析（mock）：识别年份、部门、时间词
    const yearM = q.match(/(20\d\d)/);
    const year  = yearM ? yearM[1] : '2024';
    // 注意：用 (?:A|B) 分组替代旧版 [A|B] 字符类（旧写法只匹配单字，会把「市卫健委」截成「市卫」）
    const provM = q.match(/市?(?:卫健委|发改委|民政局|公安局|疾控中心|统计局|教育局|人社局|财政局)/);
    const parsed = {
      range:    `${year}-01-01 至 ${year}-12-31`,
      provider: provM ? provM[0] : '市卫健委',
      expectBy: q.includes('下周') ? '2026-04-21（下周一）' : q.includes('明天') ? '2026-04-19' : '不限',
      topic:    q.includes('接种') ? '预防接种'
              : q.includes('医疗') ? '医疗机构'
              : q.includes('流感') ? '流感监测'
              : q.includes('低保') || q.includes('救助') ? '低保救助'
              : null,
      lowConfidence: !provM && !yearM,    // 关键字段都没识别 → 标红提示用户检视
    };
    window.STATE.parsedConditions = parsed;
    PAGES._rerender();
  });
};

// ---- Page 3: 数据集详情 ----
PAGES.datasetDetail = function (id) {
  const d = window.MOCK_DATASETS.find(x => x.id === id);
  if (!d) return brainShell('search', `<div class="bg-red-50 p-4 rounded">数据集不存在：${id}</div>`);
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '数据检索', href: '#/search' }, { label: d.name }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-5">
        <div class="bg-white rounded-lg border border-zw-line p-6">
          <h1 class="text-xl font-semibold">${d.name}</h1>
          <div class="text-xs text-zw-mute mt-1">提供方 ${d.provider} · 负责人 ${d.providerOwner} · 所在专区「${d.zone}」</div>
          <p class="text-sm leading-relaxed mt-4 text-zw-ink">${d.desc}</p>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-6">
          <h2 class="font-semibold mb-3 text-sm">字段清单（${d.fields.length} 个）</h2>
          <div class="border border-zw-line rounded overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-zw-bg text-xs text-zw-mute">
                <tr><th class="text-left px-3 py-2">字段名</th><th class="text-left px-3 py-2">类型</th><th class="text-left px-3 py-2">说明</th></tr>
              </thead>
              <tbody>
                ${d.fields.map(f => `
                  <tr class="border-t border-zw-line">
                    <td class="px-3 py-2 font-mono text-xs">${f.name}</td>
                    <td class="px-3 py-2 text-xs"><span class="px-2 py-0.5 bg-zw-bg rounded">${f.type}</span></td>
                    <td class="px-3 py-2 text-xs text-zw-mute">${f.note || '—'}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
          <p class="text-[11px] text-zw-mute mt-2">
            ✓ 含个人标识的字段已脱敏 · 验证 §4 数据脱敏立场
          </p>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-6">
          <h2 class="font-semibold mb-2 text-sm">订阅情况（K11 共享专区）</h2>
          <div class="text-2xl font-semibold text-zw-primary">${d.subscriberCount}<span class="text-sm font-normal text-zw-mute ml-1">个部门已订阅</span></div>
          <div class="text-xs text-zw-mute mt-2">${(d.subscribers || []).join(' · ') || '—'}</div>
          <p class="text-[11px] text-zw-mute mt-3">
            社会证据：高订阅数 = 业务侧已验证的高价值数据集 · 验证 K11「订阅事件流」是否被用户感知
          </p>
        </div>
      </section>

      <aside class="col-span-4 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20">
          <div class="text-xs text-zw-mute mb-1">历史通过率</div>
          <div class="text-3xl font-semibold text-green-600">${(d.approvalRate * 100).toFixed(0)}%</div>
          <div class="text-xs text-zw-mute mt-3">最近更新：${d.updatedAt}</div>
          <a href="#/apply/${d.id}" class="block mt-5 text-center bg-zw-accent text-white px-4 py-3 rounded font-medium hover:bg-orange-600">
            申请使用 →
          </a>
          <button onclick="window.UI.toast('已订阅本数据集（mock）', 'success')" class="block mt-2 w-full text-center bg-zw-bg text-zw-primary px-4 py-2 rounded text-sm hover:bg-blue-50">
            ⊕ 订阅更新
          </button>
        </div>
      </aside>
    </div>`;
  return brainShell('search', main);
};

// ---- Page 4: 申请数据（NL 加速器范式：自动填表） ----
PAGES.apply = function (id) {
  const d = window.MOCK_DATASETS.find(x => x.id === id);
  if (!d) return brainShell('search', `<div class="bg-red-50 p-4 rounded">数据集不存在：${id}</div>`);
  const parsed = window.STATE.parsedConditions || {};
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '数据检索', href: '#/search' }, { label: d.name, href: `#/dataset/${d.id}` }, { label: '申请使用' }])}
    ${stepBar(['检索', '查看', '申请', '提交', '状态'], 2)}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">

        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-900">
          <div class="font-medium mb-1">📋 NL 加速器已自动填表（验证 §7.2）</div>
          <div class="text-xs">下面 4 项由你输入的「${window.STATE.nlQuery || '示例查询'}」自动解析填入；可直接编辑覆盖。每个字段提交前都可被你检视。</div>
        </div>

        <form id="apply-form" class="bg-white rounded-lg border border-zw-line p-6 space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-zw-mute block mb-1">数据目录 <span class="text-green-600">✓ 已自动填</span></label>
              <input type="text" value="${d.name}" class="w-full px-3 py-2 border border-zw-line rounded text-sm bg-zw-bg" readonly />
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">提供方 <span class="text-green-600">✓ 已自动填</span></label>
              <input type="text" value="${d.provider}" class="w-full px-3 py-2 border border-zw-line rounded text-sm bg-zw-bg" readonly />
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">数据范围 <span class="text-green-600">✓ NL 解析</span></label>
              <input type="text" value="${parsed.range || '2024-01-01 至 2024-12-31'}" class="w-full px-3 py-2 border border-zw-line rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">期望完成时间 <span class="text-green-600">✓ NL 解析</span></label>
              <input type="text" value="${parsed.expectBy || '2026-04-21（下周一）'}" class="w-full px-3 py-2 border border-zw-line rounded text-sm" />
            </div>
          </div>

          <div>
            <label class="text-xs text-zw-mute block mb-1">申请理由 <span class="text-red-500">*</span> <span class="text-zw-mute">（NL 未识别，需手填）</span></label>
            <textarea name="purpose" required minlength="10" rows="3"
                      placeholder="说明数据用途、关联文件号等"
                      class="w-full px-3 py-2 border border-zw-line rounded text-sm focus:outline-none focus:border-zw-primary">营商环境季度报告，附件 OA-2026-Q2-014</textarea>
          </div>

          <div>
            <label class="text-xs text-zw-mute block mb-1">使用部门 <span class="text-red-500">*</span></label>
            <select class="w-full px-3 py-2 border border-zw-line rounded text-sm">
              <option>市发改委综合处（默认本部门）</option>
              <option>其他部门 · 需额外授权</option>
            </select>
          </div>

          <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900">
            <label class="flex items-start gap-2">
              <input type="checkbox" checked disabled class="mt-0.5" />
              <span><strong>同意行为上链留痕</strong>（合规要求，默认勾选不可取消）· 验证 K9「数享链上链 + 可证迹」</span>
            </label>
          </div>

          <div class="pt-3 flex items-center gap-3">
            <button type="submit" class="px-5 py-2.5 bg-zw-accent text-white rounded font-medium hover:bg-orange-600">提交申请</button>
            <button type="button" class="px-5 py-2.5 bg-white border border-zw-line text-zw-mute rounded text-sm hover:bg-zw-bg">保存草稿</button>
            <a href="#/dataset/${d.id}" class="text-xs text-zw-mute hover:text-zw-primary ml-auto">取消</a>
          </div>
        </form>
      </section>

      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 text-xs">
          <div class="font-medium mb-2 text-sm">原型验证点</div>
          <ul class="space-y-2 text-zw-mute leading-relaxed">
            <li>• 「✓ 已自动填」标识能否让用户快速识别 AI 做了什么</li>
            <li>• 必填项 NL 拒绝代填（申请理由），强制人手输入 — 验证 §7.5</li>
            <li>• 提交按钮必须人点（NL 不能直接执行写操作）</li>
            <li>• 上链留痕勾选默认且不可取消（K9）</li>
          </ul>
        </div>
      </aside>
    </div>`;
  return brainShell('search', main);
};

PAGES.apply_onMount = function (id) {
  const form = document.getElementById('apply-form');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const reqId = `REQ-2026-04-18-${String(Math.floor(Math.random() * 9000) + 1000)}`;
    const d = window.MOCK_DATASETS.find(x => x.id === id);
    window.STATE.appliedRequests.push({
      id: reqId,
      datasetId: id,
      datasetName: d.name,
      submittedAt: new Date().toLocaleString('zh-CN'),
      purpose: form.querySelector('textarea[name="purpose"]').value,
      status: 'pending',
      auditId: 'AE-' + Math.random().toString(16).slice(2, 10),
      chainAnchor: 'pending', // 30 秒后变 anchored（在 requestStatus 页演示）
    });
    window.UI.toast('申请已受理（mock）', 'success');
    window.location.hash = '#/request/' + reqId;
  });
};

// ---- Page 5: 申请状态 ----
PAGES.requestStatus = function (id) {
  const r = (window.STATE.appliedRequests || []).find(x => x.id === id) ||
            window.MOCK_REQUESTS.find(x => x.id === id);
  if (!r) return brainShell('request', `<div class="bg-red-50 p-4 rounded">申请不存在：${id}</div>`);
  const isPending = r.status === 'pending';
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: r.id }])}
    ${stepBar(['检索', '查看', '申请', '提交', '状态'], 4)}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-${isPending ? 'amber' : 'green'}-50 border border-${isPending ? 'amber' : 'green'}-200 rounded-lg p-5">
          <div class="flex items-center gap-2">
            <span class="text-2xl">${isPending ? '⏳' : '✅'}</span>
            <div>
              <div class="font-semibold text-${isPending ? 'amber' : 'green'}-900">
                ${isPending ? '申请已受理，待提供方审批' : '申请已通过'}
              </div>
              <div class="text-xs text-${isPending ? 'amber' : 'green'}-700 mt-0.5">
                Request ID: <code>${r.id}</code> · ${r.datasetName}
              </div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">申请详情</h2>
          <dl class="text-sm grid grid-cols-3 gap-y-3">
            <dt class="text-zw-mute text-xs">数据集</dt><dd class="col-span-2">${r.datasetName}</dd>
            <dt class="text-zw-mute text-xs">申请理由</dt><dd class="col-span-2">${r.purpose || '—'}</dd>
            <dt class="text-zw-mute text-xs">提交时间</dt><dd class="col-span-2">${r.submittedAt}</dd>
            ${r.approvedAt ? `<dt class="text-zw-mute text-xs">通过时间</dt><dd class="col-span-2">${r.approvedAt}</dd>` : ''}
          </dl>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">审计与上链（K9 / D4）</h2>
          <div class="space-y-2 text-sm">
            <div class="flex items-center gap-2">
              <span class="text-zw-mute text-xs w-24">audit_id</span>
              <code class="text-xs bg-zw-bg px-2 py-1 rounded font-mono">${r.auditId}</code>
              <span class="text-xs text-green-600">✓ 同步落库（D4 上半 — 审计未落库即拒绝写操作）</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-zw-mute text-xs w-24">chain_anchor</span>
              <code id="chain-anchor" class="text-xs bg-zw-bg px-2 py-1 rounded font-mono">
                ${r.chainAnchor === 'pending' ? '<span class="pending-dot"></span>pending（异步锚定中…）' : r.chainAnchor + ' ✓'}
              </code>
            </div>
            <p class="text-[11px] text-zw-mute mt-2 leading-relaxed">
              ✓ 写操作（提交申请）必须先成功写入 audit_event 才返回成功（同步阻塞）<br/>
              ✓ 区块链锚定异步进行（D4 下半），不阻塞业务；失败可降级 + 告警 + 重试
            </p>
          </div>
        </div>
      </section>

      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 text-xs">
          <div class="font-medium mb-2 text-sm">下一步</div>
          <ul class="space-y-2 text-zw-mute leading-relaxed">
            <li>• 提供方审批通过后，会自动配置数据交换任务</li>
            <li>• 数据准备好后会通过站内消息 + 邮件通知</li>
            <li>• 全程可在「我的申请」追溯，每一步都有 audit_event</li>
          </ul>
          <div class="mt-4 pt-4 border-t border-zw-line">
            <a href="#/" class="block w-full text-center bg-zw-primary text-white py-2 rounded text-sm">回到工作台</a>
          </div>
        </div>
      </aside>
    </div>`;
  return brainShell('request', main);
};

PAGES.requestStatus_onMount = function (id) {
  // 模拟 chain_anchor 30 秒内异步完成（原型加速到 4 秒）
  const r = (window.STATE.appliedRequests || []).find(x => x.id === id);
  if (r && r.chainAnchor === 'pending') {
    setTimeout(() => {
      r.chainAnchor = '0x' + Math.random().toString(16).slice(2, 14) + '...c91';
      const el = document.getElementById('chain-anchor');
      if (el) {
        el.innerHTML = r.chainAnchor + ' <span class="text-green-600">✓</span>';
        window.UI.toast('chain_anchor 已完成', 'success');
      }
    }, 4000);
  }
};

// ---- Page 6: 申请审批（§7.3 第 4 页 · 提供方管理员视角） ----
PAGES.requestReview = function (id) {
  const r = window.MOCK_TODO_REVIEWS.find(x => x.id === id);
  if (!r) return brainShell('review', `<div class="bg-red-50 p-4 rounded">待审批申请不存在：${id}</div>`);
  const ds = window.MOCK_DATASETS.find(x => x.id === r.datasetId);
  const isProvider = window.STATE.role === 'admin' || window.STATE.role === 'platform';
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '申请审批', href: '#/' }, { label: r.id }])}

    ${!isProvider ? `
    <div class="bg-amber-50 border border-amber-200 text-amber-900 p-3 rounded mb-4 text-sm">
      ⚠️ 当前角色「${roleLabel(window.STATE.role)}」无审批权限。请把右上角角色切到「提供方管理员」或「平台管理员」体验完整流程。审批按钮已禁用 — 验证 §3.1 K10 三类角色 + Skill 级 ACL。
    </div>` : ''}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <div class="flex items-center justify-between mb-3">
            <h1 class="text-lg font-semibold">${r.dataset}</h1>
            ${r.urgent ? '<span class="text-xs px-2 py-0.5 rounded sev-mid">紧急</span>' : ''}
          </div>
          <dl class="text-sm grid grid-cols-3 gap-y-3">
            <dt class="text-zw-mute text-xs">Request ID</dt><dd class="col-span-2"><code>${r.id}</code></dd>
            <dt class="text-zw-mute text-xs">申请人</dt><dd class="col-span-2">${r.applicant}（${r.applicantDept}）</dd>
            <dt class="text-zw-mute text-xs">申请理由</dt><dd class="col-span-2">${r.purpose}</dd>
            <dt class="text-zw-mute text-xs">数据范围</dt><dd class="col-span-2">${r.range}</dd>
            <dt class="text-zw-mute text-xs">期望完成</dt><dd class="col-span-2">${r.expectBy}</dd>
            <dt class="text-zw-mute text-xs">提交时间</dt><dd class="col-span-2">${r.submittedAt}</dd>
          </dl>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">大脑辅助决策（§6 / 大脑主动建议范式）</h2>
          <div class="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-900 leading-relaxed">
            🤖 同部门历史：${r.applicantDept} 过去 12 个月共申请本类数据
            <strong class="text-zw-primary">${r.historyApprovedFromSameDept + r.historyRejectedFromSameDept}</strong> 次，
            通过 <strong class="text-green-700">${r.historyApprovedFromSameDept}</strong>，
            驳回 <strong class="text-red-700">${r.historyRejectedFromSameDept}</strong>。
            申请理由 <strong>包含</strong>正式公文号（OA-2026-Q1-208），关联系统已校验有效。
            <br/>建议：<strong>通过</strong>（置信度 0.91）。
            <div class="text-[11px] text-blue-700 mt-2 opacity-80">
              依据：request.history.stats / oa.doc.exists（${r.purpose.match(/OA-\S+/) || '—'}）·
              <strong>不替你点按钮</strong>，需要你检视后人工决定（§7.5 写操作不让 NL/Agent 自决）
            </div>
          </div>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">数据集摘要</h2>
          ${ds ? `
            <p class="text-sm leading-relaxed">${ds.desc}</p>
            <div class="text-xs text-zw-mute mt-2">字段 ${ds.fields.length} 个 · 历史通过率 ${(ds.approvalRate*100).toFixed(0)}% · 已订阅 ${ds.subscriberCount}</div>
            <a href="#/dataset/${ds.id}" class="text-xs text-zw-primary hover:underline mt-2 inline-block">查看完整字段清单 →</a>
          ` : '<p class="text-zw-mute text-sm">数据集信息缺失</p>'}
        </div>
      </section>

      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 space-y-3">
          <h2 class="font-semibold text-sm">审批决定（K4 · request.review）</h2>
          <textarea id="review-note" rows="4" placeholder="必要的审批意见或驳回理由（驳回 / 补正必填）"
                    class="w-full px-3 py-2 border border-zw-line rounded text-sm focus:outline-none focus:border-zw-primary"></textarea>
          <button ${isProvider ? '' : 'disabled'} onclick="window.PAGES._review('${r.id}', 'approve')"
                  class="w-full px-4 py-2.5 ${isProvider ? 'bg-green-600 hover:bg-green-700' : 'bg-gray-300 cursor-not-allowed'} text-white rounded font-medium text-sm">通过</button>
          <button ${isProvider ? '' : 'disabled'} onclick="window.PAGES._review('${r.id}', 'request_changes')"
                  class="w-full px-4 py-2.5 ${isProvider ? 'bg-amber-500 hover:bg-amber-600' : 'bg-gray-300 cursor-not-allowed'} text-white rounded text-sm">要求补正</button>
          <button ${isProvider ? '' : 'disabled'} onclick="window.PAGES._review('${r.id}', 'reject')"
                  class="w-full px-4 py-2.5 ${isProvider ? 'bg-red-600 hover:bg-red-700' : 'bg-gray-300 cursor-not-allowed'} text-white rounded text-sm">驳回</button>
          <p class="text-[11px] text-zw-mute leading-relaxed pt-2 border-t border-zw-line">
            ✓ 任一决定都会写入 audit_event（D4 上半阻塞）+ 异步上链（D4 下半）<br/>
            ✓ 申请人会收到站内消息 + 邮件通知<br/>
            ✓ 此操作的 audit_id 与申请提交的 audit_id 链式关联，可在「合规督导 / 审计回溯」全程追溯
          </p>
        </div>
      </aside>
    </div>`;
  return brainShell('review', main);
};

PAGES._review = function (reqId, decision) {
  const note = (document.getElementById('review-note') || {}).value || '';
  if ((decision === 'reject' || decision === 'request_changes') && note.trim().length < 4) {
    window.UI.toast('驳回 / 补正必须填写理由（至少 4 字）', 'error');
    return;
  }
  const label = decision === 'approve' ? '已通过' : decision === 'reject' ? '已驳回' : '已要求补正';
  window.UI.toast(`${reqId} ${label}（mock）· audit_id: AE-${Math.random().toString(16).slice(2, 10)} 已写入`, 'success');
  setTimeout(() => { window.location.hash = '#/'; }, 900);
};

// ============================================================
// §7.3 第 3 页：资源 / 目录 / 服务管理（K1+K2+K3）
// 三 tab 切换：catalog（数据目录）/ resource（数据资源）/ service（融合服务）
// ============================================================
PAGES.manage = function (tab) {
  tab = tab || 'catalog';
  const role = window.STATE.role;
  const canWrite = (role === 'op' || role === 'admin' || role === 'platform');
  const tabs = [
    { key: 'catalog',  label: '数据目录',     icon: '📋', desc: 'K2 catalog' },
    { key: 'resource', label: '数据资源',     icon: '🗄️', desc: 'K1 resource' },
    { key: 'service',  label: '融合服务',     icon: '🔌', desc: 'K3 service' },
  ];
  let body = '';
  if (tab === 'catalog') {
    body = `
      <div class="bg-white rounded-lg border border-zw-line">
        <table class="w-full text-sm">
          <thead class="bg-zw-bg text-xs text-zw-mute">
            <tr><th class="text-left px-4 py-2.5">目录名</th><th class="text-left px-3 py-2">提供方</th><th class="text-left px-3 py-2">字段</th><th class="text-left px-3 py-2">所在专区</th><th class="text-left px-3 py-2">订阅</th><th class="text-left px-3 py-2">状态</th></tr>
          </thead>
          <tbody>
            ${window.MOCK_DATASETS.map(d => `
              <tr class="border-t border-zw-line hover:bg-zw-bg">
                <td class="px-4 py-2.5"><a href="#/dataset/${d.id}" class="text-zw-primary hover:underline font-medium">${d.name}</a><div class="text-[11px] text-zw-mute mt-0.5">${d.id}</div></td>
                <td class="px-3 py-2.5">${d.provider}</td>
                <td class="px-3 py-2.5"><span class="text-xs px-1.5 py-0.5 bg-zw-bg rounded">${d.fields.length}</span></td>
                <td class="px-3 py-2.5 text-xs">${d.zone}</td>
                <td class="px-3 py-2.5 text-xs">${d.subscriberCount}</td>
                <td class="px-3 py-2.5"><span class="text-xs px-2 py-0.5 rounded sev-low">已发布</span></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } else if (tab === 'resource') {
    body = `
      <div class="bg-white rounded-lg border border-zw-line">
        <table class="w-full text-sm">
          <thead class="bg-zw-bg text-xs text-zw-mute">
            <tr><th class="text-left px-4 py-2.5">名称</th><th class="text-left px-3 py-2">类型</th><th class="text-left px-3 py-2">连接</th><th class="text-left px-3 py-2">行数</th><th class="text-left px-3 py-2">最近探活</th><th class="text-left px-3 py-2">状态</th><th class="text-left px-3 py-2">操作</th></tr>
          </thead>
          <tbody>
            ${window.MOCK_RESOURCES.map(r => `
              <tr class="border-t border-zw-line hover:bg-zw-bg">
                <td class="px-4 py-2.5 font-mono text-xs">${r.name}<div class="text-[11px] text-zw-mute mt-0.5">${r.id} · ${r.owner}</div></td>
                <td class="px-3 py-2.5"><span class="text-xs px-1.5 py-0.5 bg-zw-bg rounded">${r.type}</span></td>
                <td class="px-3 py-2.5 text-xs text-zw-mute font-mono truncate" style="max-width:240px">${r.dsn}</td>
                <td class="px-3 py-2.5 text-xs">${r.rowCount === null ? '—' : r.rowCount.toLocaleString()}</td>
                <td class="px-3 py-2.5 text-xs">${r.lastProbeAt}</td>
                <td class="px-3 py-2.5"><span class="text-xs px-2 py-0.5 rounded ${r.state === 'connected' ? 'sev-low' : r.state === 'degraded' ? 'sev-mid' : 'sev-high'}">${r.state === 'connected' ? '✓ 在线' : r.state === 'degraded' ? '⚠ 降级' : '✗ 离线'}</span></td>
                <td class="px-3 py-2.5"><button onclick="window.UI.toast('已重新探活：${r.name}（mock）','success')" class="text-xs text-zw-primary hover:underline">重新探活</button></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } else {
    body = `
      <div class="bg-white rounded-lg border border-zw-line">
        <table class="w-full text-sm">
          <thead class="bg-zw-bg text-xs text-zw-mute">
            <tr><th class="text-left px-4 py-2.5">服务名</th><th class="text-left px-3 py-2">关联目录</th><th class="text-left px-3 py-2">URL</th><th class="text-left px-3 py-2">鉴权</th><th class="text-left px-3 py-2">QPS / 限</th><th class="text-left px-3 py-2">状态</th><th class="text-left px-3 py-2">操作</th></tr>
          </thead>
          <tbody>
            ${window.MOCK_SERVICES.map(s => `
              <tr class="border-t border-zw-line hover:bg-zw-bg">
                <td class="px-4 py-2.5 font-mono text-xs">${s.name}<div class="text-[11px] text-zw-mute mt-0.5">${s.id} · 发布 ${s.publishedAt}</div></td>
                <td class="px-3 py-2.5 text-xs">${s.catalogId}</td>
                <td class="px-3 py-2.5 text-xs text-zw-mute font-mono truncate" style="max-width:200px">${s.url}</td>
                <td class="px-3 py-2.5 text-xs"><span class="px-1.5 py-0.5 bg-zw-bg rounded">${s.auth}</span></td>
                <td class="px-3 py-2.5 text-xs"><span class="${s.qpsNow > s.rateLimit * 0.8 ? 'text-amber-600' : ''}">${s.qpsNow}</span><span class="text-zw-mute"> / ${s.rateLimit}</span></td>
                <td class="px-3 py-2.5"><span class="text-xs px-2 py-0.5 rounded ${s.state === 'live' ? 'sev-low' : 'sev-mid'}">${s.state === 'live' ? '✓ 在线' : '暂停'}</span></td>
                <td class="px-3 py-2.5">
                  ${canWrite ? `<button onclick="if(confirm('确认下线服务 ${s.name}？此操作会写入 audit_event。')){window.UI.toast('已下线（mock）· audit_id: AE-' + Math.random().toString(16).slice(2,10),'success');}" class="text-xs text-red-600 hover:underline">下线</button>` : '<span class="text-xs text-zw-mute">无权限</span>'}
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  }
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '资源 / 目录 / 服务管理' }])}

    <div class="bg-white rounded-lg border border-zw-line p-4 flex items-center gap-2">
      ${tabs.map(t => `
        <a href="#/manage/${t.key}" class="px-4 py-2 rounded text-sm ${t.key === tab ? 'bg-zw-primary text-white' : 'text-zw-ink hover:bg-zw-bg'}">
          <span class="opacity-70">${t.icon}</span> ${t.label} <span class="text-[10px] opacity-60 ml-1">${t.desc}</span>
        </a>`).join('')}
      <div class="ml-auto flex items-center gap-2">
        ${canWrite ? `<button onclick="window.UI.toast('打开「+ 新增 ${tabs.find(t=>t.key===tab).label}」表单（原型仅展示，提交后将写入 audit_event 并更新目录）','info')" class="px-3 py-1.5 bg-zw-accent text-white rounded text-xs hover:bg-orange-600">+ 新增</button>` : ''}
      </div>
    </div>

    <div class="text-xs text-zw-mute">${tab === 'catalog' ? `共 ${window.MOCK_DATASETS.length} 条目录` : tab === 'resource' ? `共 ${window.MOCK_RESOURCES.length} 个资源 · 探活节奏 5 min/次` : `共 ${window.MOCK_SERVICES.length} 个服务 · 实时 QPS 来源 dashboard.realtime`}</div>

    ${body}

    <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 leading-relaxed">
      <strong>原型验证点</strong>：
      ① 目录 / 资源 / 服务三层在同一页用 tab 切换 → 验证 §7.1 不做 20+ 子系统；
      ② 「新增」「下线」属写操作，按钮按角色 ACL 自动禁用 → 验证 §3.1 K10；
      ③ 写操作均需二次确认且会写 audit_event → 验证 D4 上半同步落审计。
    </div>`;
  return brainShell('manage', main);
};

// ============================================================
// §7.3 第 5 页：数据交换任务（K5）
// ============================================================
PAGES.exchange = function () {
  const list = window.MOCK_EXCHANGE_TASKS;
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '数据交换任务' }])}

    <div class="bg-white rounded-lg border border-zw-line">
      <div class="px-4 py-3 border-b border-zw-line flex items-center justify-between">
        <div class="text-sm">共 <strong>${list.length}</strong> 个交换任务 · ${list.filter(t=>t.state==='healthy').length} 健康 · ${list.filter(t=>t.state==='failed').length} 失败</div>
        <div class="text-xs text-zw-mute">每个 request_id 对应一个 exchange task；K5 = K4 审批通过的副作用</div>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-zw-bg text-xs text-zw-mute">
          <tr><th class="text-left px-4 py-2.5">任务 ID</th><th class="text-left px-3 py-2">数据集</th><th class="text-left px-3 py-2">使用方</th><th class="text-left px-3 py-2">模式</th><th class="text-left px-3 py-2">最近运行</th><th class="text-left px-3 py-2">最近字节</th><th class="text-left px-3 py-2">状态</th></tr>
        </thead>
        <tbody>
          ${list.map(t => `
            <tr class="border-t border-zw-line hover:bg-zw-bg cursor-pointer" onclick="window.location.hash='#/exchange/${t.id}'">
              <td class="px-4 py-2.5"><span class="font-mono text-xs text-zw-primary">${t.id}</span><div class="text-[11px] text-zw-mute mt-0.5">${t.requestId}</div></td>
              <td class="px-3 py-2.5">${t.datasetName}</td>
              <td class="px-3 py-2.5 text-xs">${t.consumer}</td>
              <td class="px-3 py-2.5"><span class="text-xs px-1.5 py-0.5 bg-zw-bg rounded">${t.mode === 'incremental' ? '增量 · ' + t.cron : '一次性'}</span></td>
              <td class="px-3 py-2.5 text-xs">${t.lastRunAt}</td>
              <td class="px-3 py-2.5 text-xs">${t.lastBytes ? (t.lastBytes/1024/1024).toFixed(1) + ' MB' : '—'}</td>
              <td class="px-3 py-2.5"><span class="text-xs px-2 py-0.5 rounded ${t.state==='healthy'?'sev-low':t.state==='failed'?'sev-high':'sev-mid'}">${t.state==='healthy'?'✓ 健康':t.state==='failed'?'✗ 失败':'⏸ 暂停'}</span></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900">
      <strong>原型验证点</strong>：
      ① 申请 / 审批 / 交换 三阶段共享同一 request_id（点详情可看到 audit 链）→ 验证 §7.5 全程审计；
      ② 失败任务的错误是「audit_event 写入失败 → 终止」→ 验证 D4 上半熔断在 K5 也生效；
      ③ 「立即重跑」属写操作，需二次确认 + 写新 audit_event。
    </div>`;
  return brainShell('exchange', main);
};

PAGES.exchangeDetail = function (id) {
  const t = window.MOCK_EXCHANGE_TASKS.find(x => x.id === id);
  if (!t) return brainShell('exchange', `<div class="bg-red-50 p-4 rounded">交换任务不存在：${id}</div>`);
  const role = window.STATE.role;
  const canRetry = (role === 'op' || role === 'admin' || role === 'platform');
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '数据交换任务', href: '#/exchange' }, { label: t.id }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h1 class="text-lg font-semibold">${t.datasetName}</h1>
              <div class="text-xs text-zw-mute mt-1">任务 ${t.id} · 申请 ${t.requestId} · 使用方 ${t.consumer}</div>
            </div>
            <span class="text-xs px-2 py-0.5 rounded ${t.state==='healthy'?'sev-low':t.state==='failed'?'sev-high':'sev-mid'}">${t.state==='healthy'?'✓ 健康':t.state==='failed'?'✗ 失败':'⏸ 暂停'}</span>
          </div>
          <dl class="grid grid-cols-3 gap-y-3 text-sm">
            <dt class="text-zw-mute text-xs">同步模式</dt><dd class="col-span-2">${t.mode === 'incremental' ? '增量 · ' + t.cron : '一次性全量'}</dd>
            <dt class="text-zw-mute text-xs">最近运行</dt><dd class="col-span-2">${t.lastRunAt} · ${(t.lastBytes/1024/1024).toFixed(1)} MB · ${(t.lastDurationMs/1000).toFixed(1)} s</dd>
          </dl>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">运行历史（最近 ${t.history.length} 次）</h2>
          <table class="w-full text-sm">
            <thead class="bg-zw-bg text-xs text-zw-mute">
              <tr><th class="text-left px-3 py-2">时间</th><th class="text-left px-3 py-2">结果</th><th class="text-left px-3 py-2">字节</th><th class="text-left px-3 py-2">耗时</th><th class="text-left px-3 py-2">备注</th></tr>
            </thead>
            <tbody>
              ${t.history.map(h => `
                <tr class="border-t border-zw-line">
                  <td class="px-3 py-2 text-xs">${h.at}</td>
                  <td class="px-3 py-2"><span class="text-xs px-2 py-0.5 rounded ${h.ok?'sev-low':'sev-high'}">${h.ok?'✓ 成功':'✗ 失败'}</span></td>
                  <td class="px-3 py-2 text-xs">${h.bytes ? (h.bytes/1024/1024).toFixed(2) + ' MB' : '—'}</td>
                  <td class="px-3 py-2 text-xs">${h.ms ? (h.ms/1000).toFixed(2) + ' s' : '—'}</td>
                  <td class="px-3 py-2 text-xs text-zw-mute">${h.err || ''}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </section>

      <aside class="col-span-4 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 space-y-3">
          <h2 class="font-semibold text-sm">操作</h2>
          ${canRetry ? `
          <button onclick="if(confirm('确认立即重跑任务 ${t.id}？')){window.UI.toast('已触发重跑（mock）· 新 audit_id: AE-' + Math.random().toString(16).slice(2,10),'success');}" class="w-full px-4 py-2.5 bg-zw-primary text-white rounded text-sm">立即重跑</button>
          <button onclick="if(confirm('确认暂停？暂停期间不再触发新批次。')){window.UI.toast('已暂停（mock）','info');}" class="w-full px-4 py-2.5 bg-amber-500 text-white rounded text-sm">暂停</button>
          ` : `<div class="bg-amber-50 border border-amber-200 text-amber-900 p-2.5 rounded text-xs">当前角色「${roleLabel(role)}」无操作权限（K10 ACL）</div>`}
          <p class="text-[11px] text-zw-mute leading-relaxed pt-2 border-t border-zw-line">
            重跑 / 暂停 / 删除 均为写操作，会先写 audit_event 再异步上链；与 K4 申请审批共享同一审计链。
          </p>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5 text-xs">
          <h3 class="font-semibold mb-2 text-sm">关联跳转</h3>
          <a href="#/request/${t.requestId}" class="block text-zw-primary hover:underline mb-1.5">→ 查看原始申请 ${t.requestId}</a>
          <a href="#/dispute" class="block text-zw-primary hover:underline mb-1.5">→ 提交关于此任务的异议</a>
          <a href="#/compliance" class="block text-zw-primary hover:underline">→ 在合规督导查 audit 链</a>
        </div>
      </aside>
    </div>`;
  return brainShell('exchange', main);
};

// ============================================================
// §7.3 第 6 页：异议处理（K8 之 a）
// ============================================================
PAGES.dispute = function () {
  const list = window.MOCK_DISPUTES;
  const open = list.filter(d => d.status === 'open' || d.status === 'escalated').length;
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '异议处理' }])}

    <div class="grid grid-cols-12 gap-5">
      <aside class="col-span-3">
        <div class="bg-white rounded-lg border border-zw-line p-4 sticky top-20 space-y-3">
          <h2 class="text-sm font-semibold">概览</h2>
          <div class="grid grid-cols-2 gap-2 text-center">
            <div class="bg-amber-50 rounded p-2"><div class="text-xl font-semibold text-amber-600">${open}</div><div class="text-[10px] text-zw-mute">待处理</div></div>
            <div class="bg-green-50 rounded p-2"><div class="text-xl font-semibold text-green-600">${list.filter(d => d.status === 'resolved').length}</div><div class="text-[10px] text-zw-mute">已解决</div></div>
          </div>
          <div class="text-xs text-zw-mute leading-relaxed pt-2 border-t border-zw-line">
            异议是数据使用方对已交付数据的反馈通道；提交后会与原 request_id 链式关联，避免「数据交了就完事」。
          </div>
          <a href="#/" onclick="event.preventDefault();window.UI.toast('打开「+ 提交异议」表单（原型省略表单 UI；提交后会写 audit_event 并通知提供方）','info')" class="block w-full text-center bg-zw-accent text-white px-4 py-2 rounded text-sm hover:bg-orange-600">+ 提交新异议</a>
        </div>
      </aside>

      <section class="col-span-9 space-y-3">
        ${list.map(d => `
          <a href="#/dispute/${d.id}" class="block bg-white rounded-lg border border-zw-line p-4 card-hover">
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <code class="text-xs font-mono text-zw-primary">${d.id}</code>
                  <span class="text-xs px-2 py-0.5 rounded ${d.status==='open'?'sev-mid':d.status==='escalated'?'sev-high':d.status==='resolved'?'sev-low':'bg-zw-bg text-zw-mute'}">${({open:'待处理',processing:'处理中',resolved:'已解决',escalated:'已升级'})[d.status]}</span>
                  <span class="text-xs px-1.5 py-0.5 rounded ${d.severity==='high'?'sev-high':d.severity==='mid'?'sev-mid':'sev-low'}">${({high:'高',mid:'中',low:'低'})[d.severity]}</span>
                </div>
                <div class="text-sm font-medium mt-1">${d.summary}</div>
                <div class="text-xs text-zw-mute mt-1">${d.datasetName} · 申请 ${d.requestId} · 提出于 ${d.raisedAt}</div>
              </div>
              <div class="text-right text-xs text-zw-mute">
                <div>${d.raisedDept}</div>
                <div class="mt-0.5">${d.raisedBy}</div>
              </div>
            </div>
          </a>`).join('')}
      </section>
    </div>`;
  return brainShell('dispute', main);
};

PAGES.disputeDetail = function (id) {
  const d = window.MOCK_DISPUTES.find(x => x.id === id);
  if (!d) return brainShell('dispute', `<div class="bg-red-50 p-4 rounded">异议不存在：${id}</div>`);
  const role = window.STATE.role;
  const canHandle = (role === 'admin' || role === 'platform');
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '异议处理', href: '#/dispute' }, { label: d.id }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <div class="flex items-center gap-2 mb-3">
            <code class="text-xs font-mono text-zw-primary">${d.id}</code>
            <span class="text-xs px-2 py-0.5 rounded ${d.status==='open'?'sev-mid':d.status==='escalated'?'sev-high':d.status==='resolved'?'sev-low':'bg-zw-bg text-zw-mute'}">${({open:'待处理',processing:'处理中',resolved:'已解决',escalated:'已升级'})[d.status]}</span>
            <span class="text-xs px-1.5 py-0.5 rounded ${d.severity==='high'?'sev-high':d.severity==='mid'?'sev-mid':'sev-low'}">严重度 ${({high:'高',mid:'中',low:'低'})[d.severity]}</span>
          </div>
          <h1 class="text-lg font-semibold">${d.summary}</h1>
          <p class="text-sm text-zw-ink mt-2 leading-relaxed">${d.detail}</p>
          <div class="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-900 mt-3">
            <strong>处理建议：</strong>${d.suggestion}
          </div>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">处理时间线</h2>
          <ol class="space-y-3 text-sm">
            ${d.timeline.map((ev, i) => `
              <li class="flex gap-3">
                <div class="flex flex-col items-center">
                  <div class="w-2 h-2 rounded-full ${i === d.timeline.length - 1 ? 'bg-zw-primary' : 'bg-zw-line'}"></div>
                  ${i < d.timeline.length - 1 ? '<div class="w-px flex-1 bg-zw-line"></div>' : ''}
                </div>
                <div class="flex-1 pb-3">
                  <div class="text-xs text-zw-mute">${ev.at} · ${ev.actor}</div>
                  <div class="text-sm mt-0.5">${ev.action}</div>
                </div>
              </li>`).join('')}
          </ol>
        </div>
      </section>

      <aside class="col-span-4 space-y-3">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 space-y-3">
          <h2 class="font-semibold text-sm">处理决定（K8）</h2>
          <textarea id="dispute-note" rows="3" placeholder="处理说明（accept / escalate 必填）" class="w-full px-3 py-2 border border-zw-line rounded text-sm focus:outline-none focus:border-zw-primary"></textarea>
          ${d.status === 'resolved' || d.status === 'escalated' ? `
            <div class="bg-zw-bg rounded p-2.5 text-xs text-zw-mute">本异议已${d.status==='resolved'?'解决':'升级到 '+d.escalatedTo}，无需进一步操作</div>
          ` : !canHandle ? `
            <div class="bg-amber-50 border border-amber-200 text-amber-900 p-2.5 rounded text-xs">当前角色「${roleLabel(role)}」无处理权限 — 验证 K10 ACL</div>
          ` : `
            <button onclick="window.PAGES._handleDispute('${d.id}','accept')" class="w-full px-4 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm">已修正 / 接受</button>
            <button onclick="window.PAGES._handleDispute('${d.id}','escalate')" class="w-full px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded text-sm">升级到平台合规组</button>
            <button onclick="window.PAGES._handleDispute('${d.id}','reject')" class="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded text-sm">驳回（需说明）</button>
          `}
          <p class="text-[11px] text-zw-mute leading-relaxed pt-2 border-t border-zw-line">
            ✓ 任一处理决定写 audit_event<br/>
            ✓ 严重度「高」的异议会触发自动告警；连续 3 条同部门高异议会冻结其新申请权（D14 平台级风险联动）
          </p>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-4 text-xs">
          <h3 class="font-semibold mb-2 text-sm">关联</h3>
          <a href="#/request/${d.requestId}" class="block text-zw-primary hover:underline mb-1.5">→ 原始申请 ${d.requestId}</a>
          <a href="#/dataset/${d.datasetId}" class="block text-zw-primary hover:underline mb-1.5">→ 数据集 ${d.datasetName}</a>
          <a href="#/compliance" class="block text-zw-primary hover:underline">→ 合规追溯（K8/K9）</a>
        </div>
      </aside>
    </div>`;
  return brainShell('dispute', main);
};

PAGES._handleDispute = function (id, decision) {
  const note = (document.getElementById('dispute-note') || {}).value || '';
  if ((decision === 'accept' || decision === 'escalate' || decision === 'reject') && note.trim().length < 4) {
    window.UI.toast('处理决定必须填写说明（至少 4 字）', 'error');
    return;
  }
  const label = decision === 'accept' ? '已接受' : decision === 'escalate' ? '已升级到平台合规组' : '已驳回';
  window.UI.toast(`异议 ${id} ${label}（mock）· audit_id: AE-${Math.random().toString(16).slice(2, 10)}`, 'success');
  setTimeout(() => { window.location.hash = '#/dispute'; }, 900);
};

// ============================================================
// §7.3 第 7 页：合规督导 + 审计回溯（K8 之 b / K9）
// ============================================================
PAGES.compliance = function () {
  const events = window.MOCK_AUDIT_EVENTS;
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '合规督导 / 审计回溯' }])}

    <div class="bg-white rounded-lg border border-zw-line p-5 mb-4">
      <h2 class="font-semibold text-sm mb-3">检索条件（演示「§7.5 上周谁调用过 X 数据」即时可查）</h2>
      <div class="grid grid-cols-4 gap-3 text-sm">
        <div>
          <label class="text-xs text-zw-mute block mb-1">时间窗</label>
          <select class="w-full px-3 py-2 border border-zw-line rounded text-sm">
            <option>最近 24 小时</option><option selected>最近 7 天</option><option>最近 30 天</option><option>自定义...</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-zw-mute block mb-1">主体（actor）</label>
          <select class="w-full px-3 py-2 border border-zw-line rounded text-sm">
            <option>全部</option><option>仅人类</option><option>仅 Agent</option><option>仅系统</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-zw-mute block mb-1">数据集</label>
          <select class="w-full px-3 py-2 border border-zw-line rounded text-sm">
            <option>全部</option>${window.MOCK_DATASETS.map(d => `<option>${d.name}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="text-xs text-zw-mute block mb-1">操作</label>
          <select class="w-full px-3 py-2 border border-zw-line rounded text-sm">
            <option>全部</option><option>仅写操作</option><option>仅只读</option>
          </select>
        </div>
      </div>
      <div class="mt-3 flex items-center justify-between">
        <button onclick="window.UI.toast('已应用筛选（原型固定返回 28 条样例）','info')" class="px-4 py-2 bg-zw-primary text-white rounded text-sm">检索</button>
        <div class="text-xs text-zw-mute">查询本身也会被审计 — 验证 K9「合规无差别对待」</div>
      </div>
    </div>

    <div class="bg-white rounded-lg border border-zw-line">
      <div class="px-4 py-3 border-b border-zw-line text-sm flex items-center justify-between">
        <div>共 <strong>${events.length}</strong> 条 audit_event</div>
        <div class="text-xs text-zw-mute">
          <button onclick="window.UI.toast('已对当前结果集做上链一致性校验（mock 全部通过 ✓）','success')" class="text-zw-primary hover:underline">▷ 触发上链一致性校验</button>
        </div>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-zw-bg text-xs text-zw-mute">
          <tr><th class="text-left px-4 py-2.5">时间</th><th class="text-left px-3 py-2">主体</th><th class="text-left px-3 py-2">类型</th><th class="text-left px-3 py-2">操作 / Skill</th><th class="text-left px-3 py-2">数据集</th><th class="text-left px-3 py-2">request_id</th><th class="text-left px-3 py-2">chain_anchor</th></tr>
        </thead>
        <tbody>
          ${events.slice(0, 18).map(e => `
            <tr class="border-t border-zw-line hover:bg-zw-bg">
              <td class="px-4 py-2 text-xs">${e.at}</td>
              <td class="px-3 py-2 text-xs">${e.actor.name}</td>
              <td class="px-3 py-2"><span class="text-[10px] px-1.5 py-0.5 rounded ${e.actor.type==='human'?'bg-blue-50 text-blue-700':e.actor.type==='agent'?'bg-amber-50 text-amber-700':'bg-zw-bg text-zw-mute'}">${e.actor.type}</span></td>
              <td class="px-3 py-2 text-xs"><code class="font-mono text-[11px]">${e.action.skill}</code> ${e.action.verb==='write'?'<span class="text-[10px] px-1 rounded bg-red-50 text-red-600 ml-1">写</span>':''}</td>
              <td class="px-3 py-2 text-xs">${(window.MOCK_DATASETS.find(d=>d.id===e.datasetId)||{}).name || '—'}</td>
              <td class="px-3 py-2 text-xs">${e.requestId ? `<a href="#/request/${e.requestId}" class="text-zw-primary hover:underline">${e.requestId}</a>` : '—'}</td>
              <td class="px-3 py-2 text-xs">${e.chainAnchor ? (e.chainAnchor.state === 'retry-ok' ? `<span class="text-amber-600" title="首次失败已重试成功">⚠ 重试 ✓</span> <code class="text-[10px] font-mono">${e.chainAnchor.value}</code>` : `<code class="text-[10px] font-mono text-green-700">${e.chainAnchor.value}</code>`) : '—'}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      <div class="px-4 py-3 border-t border-zw-line text-xs text-zw-mute flex items-center justify-between">
        <div>显示前 18 条 / 共 ${events.length} 条</div>
        <div>
          <button onclick="window.UI.toast('已导出 CSV（mock）','success')" class="text-zw-primary hover:underline">▷ 导出 CSV</button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4 mt-4">
      <div class="bg-white rounded-lg border border-zw-line p-5 text-xs">
        <h3 class="font-semibold mb-2 text-sm">「§7.5 上周谁调用过 X 数据」即时回答</h3>
        <p class="text-zw-mute leading-relaxed">在「数据集」下拉选「免疫规划接种数据集（市级）」+ 时间窗 7 天 → 点检索，列表会过滤出全部访问该数据集的事件，含人 / Agent / 系统三类主体，每条都有 chain_anchor 可重放。</p>
      </div>
      <div class="bg-white rounded-lg border border-zw-line p-5 text-xs">
        <h3 class="font-semibold mb-2 text-sm">D4 上半同步落审计的可观测证据</h3>
        <p class="text-zw-mute leading-relaxed">上方第 6 行「retry-ok」事件展示：首次上链失败 → 自动重试 → 成功；业务侧不感知中断（D4 下半不阻塞业务）；该事件对应的 audit_event 早已在写操作时同步落盘（D4 上半）。</p>
      </div>
    </div>`;
  return brainShell('compliance', main);
};

// ============================================================
// §7.3 第 8 页：Skill 市场（注册 / 审批）
// ============================================================
PAGES.skillMarket = function () {
  const role = window.STATE.role;
  const isPlatform = role === 'platform';
  const skills = window.MOCK_SKILLS;
  const proposals = window.MOCK_SKILL_PROPOSALS;
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: 'Skill 市场' }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-semibold">已发布 Skill（共 ${skills.length} 个 · 覆盖 K1/K3/K4/K5/K7/K8/K11/K12）</h2>
            <a href="#/agent/skills" class="text-xs text-zw-primary hover:underline">在 Agent 入口查看 →</a>
          </div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            ${skills.map(s => `
              <a href="#/agent/skill/${encodeURIComponent(s.id)}" class="block p-3 bg-zw-bg rounded card-hover">
                <div class="flex items-center justify-between">
                  <code class="font-mono text-xs">${s.id}</code>
                  ${s.isWrite ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600">写</span>' : ''}
                </div>
                <div class="text-xs text-zw-mute mt-1.5 truncate">${s.desc}</div>
              </a>`).join('')}
          </div>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-semibold">Skill 注册申请（${proposals.filter(p => p.status === 'pending').length} 待审批 / ${proposals.length} 总）</h2>
            ${isPlatform ? '<span class="text-xs text-zw-mute">你是平台管理员，可批准 / 驳回</span>' : `<span class="text-xs text-zw-mute">仅平台管理员可审批 — 当前 ${roleLabel(role)} 只读</span>`}
          </div>
          <div class="space-y-2.5">
            ${proposals.map(p => `
              <div class="border border-zw-line rounded p-4">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <code class="font-mono text-sm font-medium">${p.skillId}</code>
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-zw-bg">${p.domain}</span>
                    ${p.isWrite ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600">写操作</span>' : ''}
                    <span class="text-[10px] px-2 py-0.5 rounded ${p.status==='pending'?'sev-mid':p.status==='approved'?'sev-low':'sev-high'}">${({pending:'待审批',approved:'已批准',rejected:'已驳回'})[p.status]}</span>
                  </div>
                  <div class="text-xs text-zw-mute">${p.id}</div>
                </div>
                <p class="text-sm text-zw-ink">${p.summary}</p>
                <div class="text-xs text-zw-mute mt-1.5">${p.proposer} · 提交于 ${p.submittedAt}</div>
                ${p.status === 'rejected' ? `<div class="bg-red-50 border border-red-200 rounded p-2 mt-2 text-xs text-red-800"><strong>驳回理由：</strong>${p.rejectReason}</div>` : ''}
                ${p.reviewerNotes ? `<div class="bg-blue-50 border border-blue-200 rounded p-2 mt-2 text-xs text-blue-900"><strong>审核意见：</strong>${p.reviewerNotes}</div>` : ''}
                ${p.status === 'pending' && isPlatform ? `
                <div class="mt-3 flex gap-2">
                  <button onclick="window.UI.toast('Skill ${p.skillId} 已批准 · 即将写 audit_event 并发布到 Agent 入口','success');setTimeout(()=>window.location.hash='#/agent/skills',900)" class="px-3 py-1.5 bg-green-600 text-white rounded text-xs hover:bg-green-700">批准并发布</button>
                  <button onclick="if(prompt('请输入驳回理由（≥10 字）：')){window.UI.toast('Skill ${p.skillId} 已驳回（mock）','info');}" class="px-3 py-1.5 bg-red-600 text-white rounded text-xs hover:bg-red-700">驳回</button>
                </div>` : ''}
              </div>`).join('')}
          </div>
        </div>
      </section>

      <aside class="col-span-4 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20">
          <h2 class="font-semibold text-sm mb-3">提交新 Skill</h2>
          <p class="text-xs text-zw-mute leading-relaxed mb-3">提供方 / 第三方 / 平台都可提交 Skill 注册申请；写操作类 Skill 一律先经平台合规审批后才能发布。</p>
          <a href="#/skill-market/propose" class="block w-full text-center bg-zw-accent text-white px-4 py-2.5 rounded text-sm hover:bg-orange-600">+ 填写 manifest</a>
          <p class="text-[11px] text-zw-mute leading-relaxed mt-3 pt-3 border-t border-zw-line">
            ✓ Skill 注册即「契约公开」 · 同一 manifest 4 入口共享<br/>
            ✓ 验证 §6 + §7.6：Agent 入口不是后加的，是与 WebUI 同级的 surface
          </p>
        </div>
      </aside>
    </div>`;
  return brainShell('skill-market', main);
};

PAGES.skillPropose = function () {
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: 'Skill 市场', href: '#/skill-market' }, { label: '提交 Skill 注册申请' }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8">
        <form id="propose-form" class="bg-white rounded-lg border border-zw-line p-6 space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-zw-mute block mb-1">Skill ID（小写点号分隔）<span class="text-red-500">*</span></label>
              <input name="skillId" type="text" value="population.query" class="w-full px-3 py-2 border border-zw-line rounded text-sm font-mono" />
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">所属域 <span class="text-red-500">*</span></label>
              <select name="domain" class="w-full px-3 py-2 border border-zw-line rounded text-sm">
                <option>catalog</option><option>request</option><option>compliance</option><option>zone</option><option>dashboard</option><option>national</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">版本</label>
              <input name="version" type="text" value="1.0.0" class="w-full px-3 py-2 border border-zw-line rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-zw-mute block mb-1">写操作？<span class="text-zw-mute text-[11px]">（写操作需平台合规审批）</span></label>
              <label class="flex items-center gap-2 mt-2"><input type="checkbox" name="isWrite" /><span class="text-sm">是 — 触发 audit + chain</span></label>
            </div>
          </div>
          <div>
            <label class="text-xs text-zw-mute block mb-1">简要描述 <span class="text-red-500">*</span></label>
            <textarea name="desc" rows="2" class="w-full px-3 py-2 border border-zw-line rounded text-sm">常住人口属性查询（年龄段 / 籍贯 / 学历，已脱敏）— 用于人口流动分析</textarea>
          </div>
          <div>
            <label class="text-xs text-zw-mute block mb-1">Input Schema（JSON Schema） <span class="text-red-500">*</span></label>
            <textarea name="inputSchema" rows="6" class="w-full font-mono text-xs px-3 py-2 border border-zw-line rounded">{
  "type": "object",
  "required": ["region"],
  "properties": {
    "region": { "type": "string" },
    "year":   { "type": "integer", "minimum": 2020, "maximum": 2030 }
  }
}</textarea>
          </div>
          <div>
            <label class="text-xs text-zw-mute block mb-1">Output Schema <span class="text-red-500">*</span></label>
            <textarea name="outputSchema" rows="5" class="w-full font-mono text-xs px-3 py-2 border border-zw-line rounded">{
  "type": "object",
  "properties": {
    "items": { "type": "array" },
    "total": { "type": "integer" }
  }
}</textarea>
          </div>
          <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900">
            <label class="flex items-start gap-2">
              <input type="checkbox" checked disabled class="mt-0.5" />
              <span>同意「契约一旦发布 = 公开承诺」原则；后续破坏性变更需先发 v2 并保留 v1 ≥ 6 个月（D11 契约稳定性约束）</span>
            </label>
          </div>
          <div class="pt-2 flex items-center gap-3">
            <button type="submit" class="px-5 py-2.5 bg-zw-accent text-white rounded font-medium hover:bg-orange-600">提交注册申请</button>
            <a href="#/skill-market" class="text-xs text-zw-mute hover:text-zw-primary ml-auto">取消</a>
          </div>
        </form>
      </section>
      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 text-xs space-y-3">
          <div class="font-medium text-sm">原型验证点</div>
          <ul class="space-y-2 text-zw-mute leading-relaxed">
            <li>• Skill ID + Schema 是 4 入口共享的契约（同一 manifest）</li>
            <li>• 「写操作」勾选后必须经平台合规审批</li>
            <li>• 提交后异步 lint：JSON Schema 是否合规、是否与既有 Skill 冲突</li>
            <li>• 通过审批后会自动出现在 Agent 入口的 Skill 清单</li>
          </ul>
        </div>
      </aside>
    </div>`;
  return brainShell('skill-market', main);
};

PAGES.skillPropose_onMount = function () {
  const f = document.getElementById('propose-form');
  if (!f) return;
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const id = f.querySelector('[name="skillId"]').value.trim();
    if (!/^[a-z][a-z0-9_.-]*$/.test(id)) { window.UI.toast('Skill ID 格式不对（小写点号分隔）', 'error'); return; }
    try { JSON.parse(f.querySelector('[name="inputSchema"]').value); JSON.parse(f.querySelector('[name="outputSchema"]').value); }
    catch (er) { window.UI.toast('Schema JSON 格式错误：' + er.message, 'error'); return; }
    window.UI.toast(`Skill ${id} 注册申请已提交 · audit_id: AE-${Math.random().toString(16).slice(2, 10)} · 等待平台合规审批`, 'success');
    setTimeout(() => { window.location.hash = '#/skill-market'; }, 1100);
  });
};

// ============================================================
// §7.3 第 9 页：平台运营面板（与 K12 大屏区分：内部 KPI + 配额调整）
// ============================================================
PAGES.ops = function () {
  const k = window.MOCK_RUNTIME_KPI;
  const role = window.STATE.role;
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '平台运营面板' }])}

    <div class="bg-blue-50 border border-blue-200 rounded p-3 text-xs text-blue-900 mb-3">
      <strong>区别于 K12 指挥中心大屏</strong>：本面板给<strong>平台管理员</strong>看，关注「平台自身健康 + 资源配额」；K12 给<strong>厅局领导</strong>看，关注「全市数据流通价值」。两个面板共用底层 audit_event 流但视角不同 — 验证 §7.7.3 受众分层。
    </div>

    <div class="grid grid-cols-4 gap-3 mb-4">
      <div class="bg-white rounded-lg border border-zw-line p-4"><div class="text-xs text-zw-mute">已发布 Skill</div><div class="text-2xl font-semibold mt-1">${k.totalSkills}</div></div>
      <div class="bg-white rounded-lg border border-zw-line p-4"><div class="text-xs text-zw-mute">在线服务</div><div class="text-2xl font-semibold mt-1">${k.liveServices}</div></div>
      <div class="bg-white rounded-lg border border-zw-line p-4"><div class="text-xs text-zw-mute">今日总调用</div><div class="text-2xl font-semibold mt-1">${k.callsToday.toLocaleString()}</div></div>
      <div class="bg-white rounded-lg border border-zw-line p-4"><div class="text-xs text-zw-mute">今日 audit_event</div><div class="text-2xl font-semibold mt-1">${k.auditEventsToday.toLocaleString()}</div></div>
    </div>

    <div class="grid grid-cols-12 gap-4">
      <div class="bg-white rounded-lg border border-zw-line p-5 col-span-8">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold text-sm">近 7 日调用量趋势</h2>
          <span class="text-xs text-zw-mute">来源：dashboard.realtime（Skill）</span>
        </div>
        <div id="chart-ops-trend" style="width:100%;height:240px;"></div>
      </div>

      <div class="bg-white rounded-lg border border-zw-line p-5 col-span-4">
        <h2 class="font-semibold text-sm mb-3">资源池利用率</h2>
        <div class="space-y-3 text-sm">
          ${Object.entries(k.poolUtilization).map(([key, v]) => `
            <div>
              <div class="flex items-center justify-between text-xs mb-1"><span class="text-zw-mute">${({compute:'计算',ai:'AI 推理',network:'网络',db:'数据库'})[key]}</span><span class="font-medium">${(v*100).toFixed(0)}%</span></div>
              <div class="bg-zw-bg rounded h-2"><div class="${v>0.8?'bg-red-500':v>0.6?'bg-amber-500':'bg-green-500'} h-2 rounded" style="width:${(v*100)}%"></div></div>
            </div>`).join('')}
        </div>
        <div class="mt-4 pt-3 border-t border-zw-line">
          ${role === 'platform' ? `<button onclick="if(confirm('调整资源池配额会触发滚动重启 + audit_event。确认？')){window.UI.toast('已调整（mock）','success');}" class="w-full text-xs px-3 py-2 bg-zw-primary text-white rounded">调整配额（仅平台管理员）</button>`
          : `<div class="text-xs text-zw-mute">配额调整仅平台管理员可见 — K10 ACL</div>`}
        </div>
      </div>

      <div class="bg-white rounded-lg border border-zw-line p-5 col-span-12">
        <h2 class="font-semibold text-sm mb-3">TOP Skill 调用量（今日）</h2>
        <div id="chart-ops-top" style="width:100%;height:280px;"></div>
      </div>
    </div>

    <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 mt-4">
      <strong>原型验证点</strong>：
      ① 「调整配额」按角色 ACL 隐藏 / 禁用 → 验证 §3.1 K10；
      ② 各项 KPI 来源于同一份 audit_event 流（§7.5）+ dashboard.realtime Skill（K12）→ 验证「数据无副本，统一事实」；
      ③ 拒绝率（${(k.rejectRate*100).toFixed(1)}%）超阈值时会自动提醒平台管理员（D14）。
    </div>`;
  return brainShell('ops', main);
};

PAGES.ops_onMount = function () {
  if (!window.echarts) return;
  const k = window.MOCK_RUNTIME_KPI;
  const e1 = document.getElementById('chart-ops-trend');
  if (e1) {
    echarts.init(e1).setOption({
      tooltip: { trigger: 'axis' },
      grid:    { left: 40, right: 16, top: 16, bottom: 28 },
      xAxis:   { type: 'category', data: ['4-12','4-13','4-14','4-15','4-16','4-17','4-18'] },
      yAxis:   { type: 'value' },
      series:  [{ type: 'line', data: k.callsTrend7d, smooth: true, areaStyle: { color: 'rgba(11,57,131,0.12)' }, lineStyle: { color: '#0b3983' }, itemStyle: { color: '#0b3983' } }]
    });
  }
  const e2 = document.getElementById('chart-ops-top');
  if (e2) {
    echarts.init(e2).setOption({
      tooltip: { trigger: 'axis' },
      grid:    { left: 160, right: 24, top: 12, bottom: 24 },
      xAxis:   { type: 'value' },
      yAxis:   { type: 'category', data: k.topSkills.slice().reverse().map(s => s.id), axisLabel: { fontSize: 10 } },
      series:  [{ type: 'bar', data: k.topSkills.slice().reverse().map(s => s.calls), itemStyle: { color: '#e88c30' }, barWidth: '55%' }]
    });
  }
};

// ============================================================
// §7.3 第 10 页：共享专区列表（K11）
// ============================================================
PAGES.zones = function () {
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '共享专区' }])}

    <div class="bg-white rounded-lg border border-zw-line p-5 mb-4">
      <h1 class="text-lg font-semibold">共享专区</h1>
      <p class="text-sm text-zw-mute mt-1 leading-relaxed">
        专区 = 「主题化的数据集合 + 默认订阅口径」。订阅整个专区比逐个数据集申请快 5 倍以上 — 验证 K11 的实际价值。
      </p>
    </div>

    <div class="grid grid-cols-2 gap-4">
      ${window.MOCK_ZONES.map(z => `
        <a href="#/zone/${z.id}" class="block bg-white rounded-lg border border-zw-line p-5 card-hover">
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="text-base font-semibold">${z.name}</div>
              <div class="text-xs text-zw-mute mt-1">${z.owner}</div>
            </div>
            <div class="text-right">
              <div class="text-xs text-zw-mute">订阅部门</div>
              <div class="text-xl font-semibold text-zw-primary">${z.subscriberDeptCount}</div>
            </div>
          </div>
          <p class="text-xs text-zw-ink leading-relaxed mt-2">${z.desc}</p>
          <div class="mt-3 flex items-center justify-between text-xs text-zw-mute">
            <span>${z.datasetIds.length} 个数据集</span>
            <span>更新 ${z.updatedAt}</span>
          </div>
        </a>`).join('')}
    </div>

    <div class="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 mt-4">
      <strong>原型验证点</strong>：
      ① 4 个专区中 2 个已上线（健康 / 民生）+ 2 个筹建（营商 / 城市治理） → 验证 K11 是「分阶段铺开」而非一次到位；
      ② 进入专区后，「订阅整个专区」是<strong>一键操作</strong>（写操作 + audit）→ 验证 K11 的核心交互；
      ③ 专区订阅事件流出现在合规督导审计回溯里 → 验证统一审计。
    </div>`;
  return brainShell('zones', main);
};

PAGES.zoneDetail = function (id) {
  const z = window.MOCK_ZONES.find(x => x.id === id);
  if (!z) return brainShell('zones', `<div class="bg-red-50 p-4 rounded">专区不存在：${id}</div>`);
  const datasets = z.datasetIds.map(did => window.MOCK_DATASETS.find(d => d.id === did)).filter(Boolean);
  const main = `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: '共享专区', href: '#/zones' }, { label: z.name }])}

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-8 space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h1 class="text-xl font-semibold">${z.name}</h1>
          <div class="text-xs text-zw-mute mt-1">负责发布厅局 ${z.owner} · 已订阅 ${z.subscriberDeptCount} 个部门 · 上次更新 ${z.updatedAt}</div>
          <p class="text-sm leading-relaxed mt-3">${z.desc}</p>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-3">本专区数据集（${datasets.length}）</h2>
          ${datasets.length === 0 ? `<p class="text-sm text-zw-mute">本专区尚在筹建，暂无可订阅数据集。</p>` : `
            <div class="space-y-2">
              ${datasets.map(d => `
                <a href="#/dataset/${d.id}" class="block p-3 bg-zw-bg rounded card-hover">
                  <div class="flex items-center justify-between">
                    <div>
                      <div class="text-sm font-medium">${d.name}</div>
                      <div class="text-xs text-zw-mute mt-0.5">${d.provider} · 通过率 ${(d.approvalRate*100).toFixed(0)}% · 订阅 ${d.subscriberCount}</div>
                    </div>
                    <span class="text-xs text-zw-primary">查看 →</span>
                  </div>
                </a>`).join('')}
            </div>`}
        </div>
      </section>

      <aside class="col-span-4">
        <div class="bg-white rounded-lg border border-zw-line p-5 sticky top-20 space-y-3">
          <h2 class="font-semibold text-sm">一键订阅（K11）</h2>
          <p class="text-xs text-zw-mute leading-relaxed">订阅本专区后，新加入的数据集会自动出现在你的工作台「最近浏览的目录」中。</p>
          ${datasets.length === 0
            ? `<button disabled class="w-full px-4 py-3 bg-gray-300 text-white rounded text-sm cursor-not-allowed">专区筹建中，暂不可订阅</button>`
            : `<button onclick="if(confirm('确认订阅整个「${z.name}」？此操作会写入 audit_event。')){window.UI.toast('已订阅 · subscription_id: SUB-' + Math.random().toString(16).slice(2,8) + ' · audit_id: AE-' + Math.random().toString(16).slice(2,10),'success');}" class="w-full px-4 py-3 bg-zw-accent text-white rounded text-sm font-medium hover:bg-orange-600">订阅整个专区</button>`}
          <p class="text-[11px] text-zw-mute leading-relaxed pt-2 border-t border-zw-line">
            订阅是<strong>写操作</strong>，与申请走同一条 audit / chain 流（D4）；可在「合规督导」追溯。
          </p>
        </div>
      </aside>
    </div>`;
  return brainShell('zones', main);
};

// ============================================================
// 场景 2：大屏（K12）
// ============================================================

PAGES.dashboard = function () {
  const outage = window.STATE.brainOutage === true;
  const sum    = window.MOCK_DASHBOARD_SUMMARY;
  return `
    <div class="dash-stage">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h1 class="text-2xl font-semibold">政务大脑 · 指挥中心</h1>
          <p class="text-xs opacity-70 mt-0.5">T1 模板 · §7.7.3 五类必有看板（上排）+ §6 演示位（下排右）</p>
        </div>
        <div class="text-xs opacity-80 flex items-center gap-4">
          <span>主大脑 <span class="${outage ? 'text-red-400' : 'text-green-300'}">${outage ? '✗' : '✓'}</span></span>
          <span>大屏 <span class="text-green-300">✓</span></span>
          <span>最近刷新 <span class="dash-num" id="dash-time">${new Date().toLocaleTimeString('zh-CN')}</span></span>
          <button id="outage-toggle" class="px-2 py-1 text-[10px] rounded ${outage ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600/70 hover:bg-red-600'} text-white">
            ${outage ? '恢复主大脑' : '模拟主大脑故障'}
          </button>
        </div>
      </div>

      ${outage ? `
      <div class="mb-3 rounded p-2.5 text-xs flex items-center gap-2" style="background:rgba(245,158,11,0.18);border:1px solid rgba(245,158,11,0.4);color:#fde68a">
        ⚠️ <strong>主大脑离线</strong> · 大屏切换到「快照模式」（数据为 13:50 抓取，5 分钟前）。验证 §7.7.1 故障隔离对用户可见，整屏不会白掉。
      </div>` : ''}

      <!-- 上排：T1 五类必有看板（§7.7.3） -->
      <div class="grid grid-cols-12 gap-3 mb-3">
        <!-- ① 实时数据流通量 -->
        <div class="dash-card col-span-6">
          <div class="text-xs opacity-70 mb-1 flex items-center justify-between">
            <span>① 实时数据流通量（24h，KB/h）</span>
            ${outage ? '<span class="text-amber-300 text-[10px]">快照</span>' : ''}
          </div>
          <div id="chart-flow" style="width:100%;height:200px;"></div>
        </div>
        <!-- ② Skill 调用 QPS -->
        <div class="dash-card col-span-3">
          <div class="text-xs opacity-70 mb-1">② Skill 调用 QPS</div>
          <div class="dash-num text-3xl">${outage ? '—' : window.MOCK_DASHBOARD_QPS.current}</div>
          <div class="text-xs opacity-60 mt-1">今日峰值 ${window.MOCK_DASHBOARD_QPS.peakToday}</div>
          <div id="chart-qps" style="width:100%;height:80px;margin-top:8px;"></div>
        </div>
        <!-- ③ 在线 Agent 数 -->
        <div class="dash-card col-span-3">
          <div class="text-xs opacity-70 mb-1">③ 在线 Agent 数</div>
          <div class="dash-num text-3xl">${outage ? '—' : sum.agentsOnline}</div>
          <div class="text-xs opacity-60 mt-1">个在跑</div>
          <div class="mt-3 text-xs opacity-80 leading-relaxed">
            提供方 9 · 申请方 8 · 平台 6
          </div>
        </div>
      </div>

      <!-- 下排：异常告警 + 国家通道 + AI 建议 -->
      <div class="grid grid-cols-12 gap-3">
        <!-- ④ 异常告警 -->
        <div class="dash-card col-span-4 cursor-pointer card-hover" onclick="window.location.hash='#/dashboard/alert'">
          <div class="text-xs opacity-70 mb-2 flex items-center justify-between">
            <span>④ 异常告警</span>
            <span class="text-amber-300 text-[10px]">点击钻取 →</span>
          </div>
          <div class="grid grid-cols-3 gap-2 mb-2">
            <div class="text-center p-2 rounded" style="background:rgba(34,197,94,0.15)"><div class="dash-num text-2xl text-green-300">0</div><div class="text-[10px] opacity-70">高</div></div>
            <div class="text-center p-2 rounded" style="background:rgba(245,158,11,0.15)"><div class="dash-num text-2xl text-amber-300">${sum.alerts.length}</div><div class="text-[10px] opacity-70">中</div></div>
            <div class="text-center p-2 rounded" style="background:rgba(125,211,252,0.15)"><div class="dash-num text-2xl text-sky-300">5</div><div class="text-[10px] opacity-70">提示</div></div>
          </div>
          <div class="text-xs opacity-80 mt-2 leading-relaxed">最近：<span class="text-amber-200">${sum.alerts[0].skill}</span> · ${sum.alerts[0].summary}</div>
        </div>

        <!-- ⑤ 国家通道状态 -->
        <div class="dash-card col-span-3">
          <div class="text-xs opacity-70 mb-2">⑤ 国家通道状态</div>
          <div class="space-y-2.5 text-xs">
            <div class="flex items-center justify-between"><span>省厅通道</span><span class="text-green-300">✓ 正常</span></div>
            <div class="flex items-center justify-between"><span>国家通道</span><span class="text-green-300">✓ 正常</span></div>
            <div class="flex items-center justify-between"><span>最近心跳</span><span class="opacity-80 dash-num">13:54:50</span></div>
            <div class="flex items-center justify-between"><span>今日上行</span><span class="dash-num">1,247 任务</span></div>
            <div class="flex items-center justify-between"><span>今日下行</span><span class="dash-num">386 任务</span></div>
          </div>
          <div class="text-[10px] opacity-50 mt-3 pt-2 border-t border-white/10">国家共享平台 K7 通道（national.relay.*）</div>
        </div>

        <!-- §6 演示位：AI 主动建议（不属于 T1 必有看板） -->
        <div class="dash-card col-span-5" style="background:rgba(232,140,48,0.08);border-color:rgba(232,140,48,0.25)">
          <div class="text-xs mb-2 flex items-center gap-2">
            <span class="text-amber-300 text-base">🤖</span>
            <span class="opacity-80">大脑主动建议</span>
            <span class="ml-auto text-[10px] opacity-60">§6 演示位 · 非 T1 必有看板</span>
          </div>
          <div class="font-medium text-sm">${sum.aiSuggestion.title}</div>
          <p class="text-xs opacity-80 mt-1.5 leading-relaxed">${sum.aiSuggestion.body}</p>
          <div class="mt-2.5 space-y-1.5">
            ${sum.aiSuggestion.actions.map((a, i) => `
              <div class="text-xs flex items-start gap-2 opacity-90"><span class="text-amber-300">${i + 1}.</span><span>${a}</span></div>
            `).join('')}
          </div>
          <div class="text-[10px] opacity-50 mt-2.5">依据：${sum.aiSuggestion.basedOn.join(' · ')} · 置信度 ${(sum.aiSuggestion.confidence * 100).toFixed(0)}%</div>
          <div class="mt-2.5 flex gap-2">
            <button onclick="window.UI.toast('已采纳建议（mock，不会真的提资源池配额——验证 §7.5 不让 NL 直接执行写操作）', 'success')" class="px-3 py-1.5 bg-amber-500 text-white rounded text-xs hover:bg-amber-600">采纳</button>
            <button onclick="window.UI.toast('已忽略本条建议', 'info')" class="px-3 py-1.5 bg-white/10 text-white rounded text-xs hover:bg-white/20">忽略</button>
          </div>
        </div>
      </div>
    </div>`;
};

PAGES.dashboard_onMount = function () {
  const outage = window.STATE.brainOutage === true;
  // 流通量图（outage 时仍画，但调暗 + 提示已为快照）
  const flow = window.MOCK_DASHBOARD_FLOW;
  if (window.echarts && document.getElementById('chart-flow')) {
    const c1 = echarts.init(document.getElementById('chart-flow'));
    c1.setOption({
      tooltip: { trigger: 'axis' },
      grid:    { left: 36, right: 12, top: 16, bottom: 24 },
      xAxis:   { type: 'category', data: flow.hours, axisLabel: { color: '#a8b8d4', fontSize: 9 } },
      yAxis:   { type: 'value', axisLabel: { color: '#a8b8d4', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      series:  [{ type: 'bar', data: flow.flow, itemStyle: { color: outage ? '#475569' : '#3b82f6' }, barWidth: '60%' }]
    });
  }
  // QPS 趋势线
  const qps = window.MOCK_DASHBOARD_QPS;
  if (window.echarts && document.getElementById('chart-qps')) {
    const c2 = echarts.init(document.getElementById('chart-qps'));
    c2.setOption({
      grid: { left: 0, right: 0, top: 4, bottom: 4 },
      xAxis: { type: 'category', show: false, data: qps.trend.map((_, i) => i) },
      yAxis: { type: 'value', show: false },
      series: [{ type: 'line', data: qps.trend, smooth: true, symbol: 'none',
                lineStyle: { color: outage ? '#64748b' : '#fbbf24', width: 1.5 },
                areaStyle: { color: outage ? 'rgba(100,116,139,0.18)' : 'rgba(251,191,36,0.18)' } }]
    });
  }
  // 时钟刷新（outage 时停留在 13:50:00 — 体现「快照」语义）
  if (window._dashTimer) clearInterval(window._dashTimer);
  if (outage) {
    const el = document.getElementById('dash-time');
    if (el) el.textContent = '13:50:00（快照）';
  } else {
    window._dashTimer = setInterval(() => {
      const el = document.getElementById('dash-time');
      if (!el) { clearInterval(window._dashTimer); return; }
      el.textContent = new Date().toLocaleTimeString('zh-CN');
    }, 1000);
  }
  // 故障 toggle
  const tog = document.getElementById('outage-toggle');
  if (tog) {
    tog.addEventListener('click', () => {
      window.STATE.brainOutage = !window.STATE.brainOutage;
      window.UI.toast(window.STATE.brainOutage
        ? '已模拟主大脑离线 — 大屏切换到快照模式（§7.7.1 故障隔离演示）'
        : '已恢复主大脑 — 大屏切回实时', 'info');
      PAGES._rerender();
    });
  }
};

PAGES.dashboardAlert = function () {
  const alerts = window.MOCK_DASHBOARD_SUMMARY.alerts;
  return `
    <div class="dash-stage">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 class="text-2xl font-semibold">异常告警 · 钻取详情</h1>
          <p class="text-xs opacity-70 mt-0.5">验证 §7.7「5% 一键钻取」边界 — 仅 1 层钻取，不开新窗</p>
        </div>
        <a href="#/dashboard" class="px-3 py-1.5 bg-white/10 text-white rounded text-xs hover:bg-white/20">← 返回指挥中心</a>
      </div>

      <div class="space-y-3">
        ${alerts.map(a => `
          <div class="dash-card">
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-base font-medium">${a.skill}</div>
                <div class="text-xs opacity-70 mt-0.5">告警 ID ${a.id} · 自 ${a.since} 起</div>
              </div>
              <span class="px-2 py-1 rounded text-xs sev-${a.severity}">${a.severity === 'high' ? '高' : a.severity === 'mid' ? '中' : '低'}</span>
            </div>
            <div class="text-sm opacity-90 mb-3">${a.summary}</div>
            <div class="bg-black/20 rounded p-3 text-xs">
              <div class="opacity-70 mb-1">自动诊断：</div>
              <div>${a.diagnosis}</div>
              ${a.ticket && a.ticket !== '—' ? `<div class="mt-2 opacity-70">关联工单：<span class="text-amber-300">${a.ticket}</span></div>` : ''}
            </div>
          </div>`).join('')}
      </div>

      <div class="mt-6 dash-card opacity-70 text-xs">
        <strong>钻取边界（§7.7）</strong>：大屏只允许 1 层钻取（指挥中心 → 详情）；不允许从大屏直接发起写操作（如「重启 Skill」「关闭告警」），需操作员通过主 WebUI 完成 — 验证 N7 大屏只读约束。
      </div>
    </div>`;
};

// ============================================================
// 场景 3：Agent 入口（4 入口对等的可视化展示）
// ============================================================

PAGES.agentHome = function () {
  const entries = [
    {
      key: 'web', icon: '🖥️', name: 'Web UI',
      who: '人类操作员（提供方 / 申请方 / 平台管理员）',
      example: '浏览器访问主 WebUI（≤10 个核心场景页 + NL 加速器）',
      code: 'https://zw-brain.gov.local/',
      goto: '#/'
    },
    {
      key: 'cli', icon: '⌨️', name: 'CLI',
      who: '运维 / 数据工程师 / 脚本',
      example: '命令行直接调用 Skill，便于嵌入 CI/批处理',
      code: 'zw-brain skill invoke catalog.search --q "低保"\nzw-brain skill list --domain request'
    },
    {
      key: 'mcp', icon: '🔌', name: 'MCP',
      who: '外部 Agent / IDE 集成（如 Claude / Cursor）',
      example: 'Model Context Protocol，让 Agent 直接发现并调用 Skill',
      code: '{\n  "mcpServers": {\n    "zw-brain": { "url": "wss://zw-brain.gov.local/mcp" }\n  }\n}'
    },
    {
      key: 'a2a', icon: '🤝', name: 'A2A',
      who: '其他大脑 / Agent 平台',
      example: 'Agent-to-Agent 协议，跨大脑/跨平台编排',
      code: 'POST /a2a/v1/invoke\n{ "agent_card": "...", "skill_id": "request.status.query", ... }'
    },
  ];
  return `
    ${crumbs([{ label: '工作台', href: '#/' }, { label: 'Agent 入口（开发者门户）' }])}

    <div class="bg-white rounded-lg border border-zw-line p-6 mb-5">
      <h1 class="text-xl font-semibold">Agent 入口 / 开发者门户</h1>
      <p class="text-sm text-zw-mute mt-1 leading-relaxed">
        政务大脑同一套 Skill 契约可通过 4 种 surface 调用：人类用 Web UI，Agent / 程序用 CLI / MCP / A2A。
        <strong>4 入口完全对等</strong>，共享同一份 manifest（验证 §6 + §7.6 立场）。
      </p>
      <div class="mt-3 inline-block bg-amber-50 text-amber-800 text-xs px-3 py-1.5 rounded border border-amber-200">
        💡 本区不算 §7.3 的 10 个 WebUI 核心场景页 — 它是给开发者看的契约文档站
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4">
      ${entries.map(e => `
        <div class="bg-white rounded-lg border border-zw-line p-5 ${e.goto ? 'card-hover cursor-pointer' : ''}" ${e.goto ? `onclick="window.location.hash='${e.goto}'"` : ''}>
          <div class="flex items-center gap-3 mb-2">
            <span class="text-2xl">${e.icon}</span>
            <h2 class="font-semibold">${e.name}</h2>
            ${e.key === 'mcp' ? '<span class="ml-auto text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded">推荐入口</span>' : ''}
          </div>
          <div class="text-xs text-zw-mute mb-2">受众：${e.who}</div>
          <p class="text-sm text-zw-ink mb-3">${e.example}</p>
          <pre class="code text-[11px]">${e.code}</pre>
          ${e.key !== 'web' ? `<a href="#/agent/skills?from=${e.key}" class="inline-block mt-3 text-xs text-zw-primary hover:underline">浏览 ${e.name} 视角的 Skill 清单 →</a>` : ''}
        </div>
      `).join('')}
    </div>

    <div class="mt-6 bg-white rounded-lg border border-zw-line p-5">
      <h2 class="font-semibold mb-2 text-sm">契约源（自动生成，禁止手改）</h2>
      <p class="text-xs text-zw-mute leading-relaxed">
        本页 4 个入口共享同一份 Skill manifest，源是
        <code class="bg-zw-bg px-1.5 py-0.5 rounded">docs/agent_integration.md</code>
        （由 <code class="bg-zw-bg px-1.5 py-0.5 rounded">scripts/export_agent_contract.py</code> 从代码自动生成）。
        preflight 段 4 强制契约文档与代码不漂移；4 入口任一更改，4 个入口的展示都会同步。
      </p>
    </div>
  `;
};

PAGES.agentSkills = function () {
  const skills = window.MOCK_SKILLS;
  const byDomain = {};
  skills.forEach(s => { (byDomain[s.domain] = byDomain[s.domain] || []).push(s); });
  return `
    ${crumbs([
      { label: '工作台', href: '#/' },
      { label: 'Agent 入口', href: '#/agent' },
      { label: 'Skill 清单' }
    ])}

    <div class="grid grid-cols-12 gap-5">
      <aside class="col-span-3">
        <div class="bg-white rounded-lg border border-zw-line p-4 sticky top-20">
          <input type="text" placeholder="搜索 Skill / 自然语言..."
                 class="w-full px-3 py-2 border border-zw-line rounded text-sm mb-3" />
          <div class="text-xs text-zw-mute font-medium mb-2">按域分类</div>
          <div class="space-y-1 text-sm">
            ${Object.keys(byDomain).map(dom => `
              <div class="flex items-center justify-between px-2 py-1.5 rounded hover:bg-zw-bg cursor-pointer">
                <span>${dom}</span>
                <span class="text-xs text-zw-mute">${byDomain[dom].length}</span>
              </div>`).join('')}
          </div>
        </div>
      </aside>

      <section class="col-span-9 space-y-2">
        <div class="text-sm text-zw-mute mb-2">${skills.length} 个 Skill 已注册 · 按域分组</div>
        ${Object.entries(byDomain).map(([dom, list]) => `
          <div>
            <div class="text-xs text-zw-mute font-medium mt-3 mb-2">${dom}</div>
            ${list.map(s => `
              <a href="#/agent/skill/${encodeURIComponent(s.id)}" class="block bg-white rounded-lg border border-zw-line p-4 mb-2 card-hover">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <code class="font-mono text-sm font-medium">${s.id}</code>
                    <span class="text-[10px] px-1.5 py-0.5 rounded ${s.stability === 'stable' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}">${s.stability}</span>
                    ${s.isWrite ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600">写操作</span>' : ''}
                    ${s.readOnly ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">只读</span>' : ''}
                  </div>
                  <span class="text-xs text-zw-mute">v${s.version}</span>
                </div>
                <div class="text-sm text-zw-ink mt-1">${s.desc}</div>
                <div class="text-xs text-zw-mute mt-1.5">订阅者 ${s.subscriberCount} · ${s.owner}</div>
              </a>
            `).join('')}
          </div>
        `).join('')}
      </section>
    </div>`;
};

PAGES.agentSkillDetail = function (id) {
  id = decodeURIComponent(id);
  const s = window.MOCK_SKILLS.find(x => x.id === id);
  if (!s) return `<div class="bg-red-50 p-4 rounded">Skill 不存在：${id}</div>`;
  const exampleArgs = JSON.stringify(
    Object.fromEntries(Object.entries(s.inputSchema.properties || {}).map(([k, v]) => [k, v.example || v.default || (v.type === 'string' ? 'demo' : v.type === 'integer' ? 1 : null)])),
    null, 2
  );
  return `
    ${crumbs([
      { label: '工作台', href: '#/' },
      { label: 'Agent 入口', href: '#/agent' },
      { label: 'Skill 清单', href: '#/agent/skills' },
      { label: s.id }
    ])}

    <div class="bg-white rounded-lg border border-zw-line p-6 mb-4">
      <div class="flex items-center gap-3 mb-2">
        <code class="font-mono text-lg font-semibold">${s.id}</code>
        <span class="text-xs px-2 py-0.5 rounded ${s.stability === 'stable' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}">${s.stability}</span>
        <span class="text-xs text-zw-mute">v${s.version}</span>
        ${s.isWrite ? '<span class="text-xs px-2 py-0.5 rounded bg-red-50 text-red-600">写操作（触发 audit + chain）</span>' : ''}
      </div>
      <p class="text-sm text-zw-ink">${s.desc}</p>
      <div class="text-xs text-zw-mute mt-2">所属域 <code>${s.domain}</code> · 拥有者 ${s.owner} · 订阅者 ${s.subscriberCount}</div>
    </div>

    <div class="grid grid-cols-2 gap-4 mb-4">
      <div class="bg-white rounded-lg border border-zw-line p-5">
        <h2 class="font-semibold text-sm mb-2">Input Schema</h2>
        <pre class="code">${escapeHtml(JSON.stringify(s.inputSchema, null, 2))}</pre>
      </div>
      <div class="bg-white rounded-lg border border-zw-line p-5">
        <h2 class="font-semibold text-sm mb-2">Output Schema</h2>
        <pre class="code">${escapeHtml(JSON.stringify(s.outputSchema, null, 2))}</pre>
      </div>
    </div>

    <div class="bg-white rounded-lg border border-zw-line p-5 mb-4">
      <h2 class="font-semibold text-sm mb-3">4 入口调用方式（共享同一 Skill ID + 同一 schema）</h2>
      <div class="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div class="font-medium mb-1">🖥️ Web UI</div>
          <pre class="code text-[11px]">在主 WebUI 第 ${guessWebUIPage(s)} 页操作，
NL 加速器自动调用：
  ${s.id}(${formatArgsInline(exampleArgs)})</pre>
        </div>
        <div>
          <div class="font-medium mb-1">⌨️ CLI</div>
          <pre class="code text-[11px]">$ zw-brain skill invoke ${s.id} \\
    ${formatArgsCli(exampleArgs)}</pre>
        </div>
        <div>
          <div class="font-medium mb-1">🔌 MCP</div>
          <pre class="code text-[11px]">{
  "method": "tools/call",
  "params": {
    "name": "${s.id}",
    "arguments": ${exampleArgs.replace(/\n/g, '\n    ')}
  }
}</pre>
        </div>
        <div>
          <div class="font-medium mb-1">🤝 A2A</div>
          <pre class="code text-[11px]">POST /a2a/v1/invoke
{
  "skill_id": "${s.id}",
  "args": ${exampleArgs.replace(/\n/g, '\n  ')},
  "agent_card": "did:agent:..."
}</pre>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-lg border border-zw-line p-5">
      <h2 class="font-semibold text-sm mb-3">模拟调用</h2>
      <p class="text-xs text-zw-mute mb-3">编辑下方参数后点「调用」，原型会返回 mock 响应。<strong>不会触发任何真实操作</strong>。</p>
      <a href="#/agent/invoke/${encodeURIComponent(s.id)}" class="inline-block px-4 py-2 bg-zw-primary text-white rounded text-sm">→ 进入模拟调用</a>
    </div>`;
};

PAGES.agentInvoke = function (id) {
  id = decodeURIComponent(id);
  const s = window.MOCK_SKILLS.find(x => x.id === id);
  if (!s) return `<div class="bg-red-50 p-4 rounded">Skill 不存在：${id}</div>`;
  const exampleArgs = JSON.stringify(
    Object.fromEntries(Object.entries(s.inputSchema.properties || {}).map(([k, v]) => [k, v.example || v.default || (v.type === 'string' ? 'demo' : v.type === 'integer' ? 1 : null)])),
    null, 2
  );
  return `
    ${crumbs([
      { label: '工作台', href: '#/' },
      { label: 'Agent 入口', href: '#/agent' },
      { label: 'Skill 清单', href: '#/agent/skills' },
      { label: s.id, href: `#/agent/skill/${encodeURIComponent(s.id)}` },
      { label: '模拟调用' }
    ])}

    <div class="grid grid-cols-2 gap-5">
      <div class="space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-2">请求参数（可编辑）</h2>
          <textarea id="invoke-args" rows="12" class="w-full font-mono text-xs px-3 py-2 border border-zw-line rounded">${exampleArgs}</textarea>
          <div class="mt-3 flex items-center gap-2">
            <button id="invoke-btn" class="px-4 py-2 bg-zw-primary text-white rounded text-sm">调用</button>
            <span class="text-xs text-zw-mute">入口：MCP（模拟）</span>
          </div>
        </div>

        <div class="bg-white rounded-lg border border-zw-line p-5 text-xs">
          <h3 class="font-semibold mb-2 text-sm">实际发出的 MCP message</h3>
          <pre id="invoke-request" class="code">// 点「调用」按钮后显示</pre>
        </div>
      </div>

      <div class="space-y-4">
        <div class="bg-white rounded-lg border border-zw-line p-5">
          <h2 class="font-semibold text-sm mb-2">响应</h2>
          <pre id="invoke-response" class="code">// 点「调用」按钮后显示</pre>
        </div>

        <div id="invoke-audit" class="bg-white rounded-lg border border-zw-line p-5 text-xs hidden">
          <h3 class="font-semibold mb-2 text-sm">审计与上链（${s.isWrite ? '写操作触发' : '只读操作仅记审计'}）</h3>
          <div class="space-y-1.5">
            <div><span class="text-zw-mute">audit_id：</span><code id="audit-id" class="bg-zw-bg px-2 py-0.5 rounded font-mono"></code></div>
            ${s.isWrite ? '<div><span class="text-zw-mute">chain_anchor：</span><code id="chain-anchor-3" class="bg-zw-bg px-2 py-0.5 rounded font-mono"></code></div>' : ''}
          </div>
          <p class="text-[11px] text-zw-mute mt-3">
            Agent 调用与人类调用走同一审计 + 上链路径 — 验证 K9「合规无差别对待」
          </p>
        </div>
      </div>
    </div>`;
};

PAGES.agentInvoke_onMount = function (id) {
  id = decodeURIComponent(id);
  const s = window.MOCK_SKILLS.find(x => x.id === id);
  const btn = document.getElementById('invoke-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    let args; try { args = JSON.parse(document.getElementById('invoke-args').value); }
    catch (e) { window.UI.toast('JSON 格式错误：' + e.message, 'error'); return; }
    const reqMsg = { method: 'tools/call', params: { name: id, arguments: args } };
    document.getElementById('invoke-request').textContent = JSON.stringify(reqMsg, null, 2);
    document.getElementById('invoke-response').textContent = '⏳ 调用中…（mock 网络延迟）';
    await window.UI.sleep(400);
    const mockResp = mockSkillResponse(s, args);
    document.getElementById('invoke-response').textContent = JSON.stringify(mockResp, null, 2);
    document.getElementById('invoke-audit').classList.remove('hidden');
    document.getElementById('audit-id').textContent = 'AE-mock-' + Math.random().toString(16).slice(2, 10);
    if (s.isWrite) {
      const el = document.getElementById('chain-anchor-3');
      if (el) {
        el.innerHTML = '<span class="pending-dot"></span>pending';
        setTimeout(() => { el.innerHTML = '0xmock-' + Math.random().toString(16).slice(2, 14) + ' ✓'; }, 2500);
      }
    }
    window.UI.toast('调用完成（mock）', 'success');
  });
};

// ============================================================
// 工具函数
// ============================================================

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function roleLabel(r) {
  return ({
    op: '提供方操作员',
    admin: '提供方管理员',
    leader: '厅局领导',
    platform: '平台管理员',
    'agent-dev': '外部 Agent 开发者',
  })[r] || r;
}

function formatArgsInline(jsonStr) {
  try { return Object.entries(JSON.parse(jsonStr)).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', '); }
  catch { return jsonStr; }
}
function formatArgsCli(jsonStr) {
  try {
    return Object.entries(JSON.parse(jsonStr)).map(([k, v]) => `--${k.replace(/_/g, '-')} ${JSON.stringify(v)}`).join(' \\\n    ');
  } catch { return jsonStr; }
}
function guessWebUIPage(s) {
  const map = { 'catalog': '2 / 3', 'request': '2 / 4', 'zone': '10', 'dashboard': '（不在 WebUI，仅大屏）', 'national': '7' };
  return map[s.domain] || '2';
}
function mockSkillResponse(s, args) {
  if (s.id === 'request.status.query') {
    return { status: 'approved', approved_at: '2026-04-15T10:23:00+08:00', approver: '陈科长', data_url: 'https://internal.gov.local/data/...' };
  }
  if (s.id === 'catalog.search') {
    return { items: window.MOCK_DATASETS.slice(0, args.topK || 3).map((d, i) => ({ id: d.id, name: d.name, provider: d.provider, score: 0.95 - i * 0.07 })) };
  }
  if (s.id === 'request.submit') {
    return { request_id: 'REQ-mock-' + Date.now().toString().slice(-6), audit_id: 'AE-mock-x', chain_anchor: 'pending' };
  }
  if (s.id === 'national.relay.query') {
    return { status: 'in_progress', progress: 0.62 };
  }
  if (s.id === 'zone.subscribe') {
    return { subscription_id: 'SUB-mock-' + Math.random().toString(16).slice(2, 8) };
  }
  if (s.id === 'dashboard.realtime') {
    return { flow_24h: window.MOCK_DASHBOARD_FLOW.flow.slice(0, 5).concat(['...']), qps_current: window.MOCK_DASHBOARD_QPS.current, agents_online: window.MOCK_DASHBOARD_SUMMARY.agentsOnline };
  }
  if (s.id === 'request.review') {
    return { request_id: args.request_id, decision: args.decision, audit_id: 'AE-mock-' + Math.random().toString(16).slice(2,8), chain_anchor: 'pending' };
  }
  if (s.id === 'catalog.register') {
    return { catalog_id: 'ds-mock-' + Math.random().toString(16).slice(2,6), audit_id: 'AE-mock-' + Math.random().toString(16).slice(2,8) };
  }
  if (s.id === 'service.publish') {
    return { service_id: 'svc-mock-' + Math.random().toString(16).slice(2,6), url: 'https://api.gov.local/share/' + (args.catalog_id || 'demo') + '/v1' };
  }
  if (s.id === 'exchange.run') {
    return { task_id: args.task_id, run_id: 'RUN-' + Date.now().toString().slice(-6), state: 'queued' };
  }
  if (s.id === 'dispute.handle') {
    return { dispute_id: args.dispute_id, decision: args.decision, audit_id: 'AE-mock-' + Math.random().toString(16).slice(2,8) };
  }
  if (s.id === 'compliance.audit') {
    return { events: window.MOCK_AUDIT_EVENTS.slice(0, 5), total: window.MOCK_AUDIT_EVENTS.length };
  }
  return { ok: true, mock: true };
}

// 触发当前路由的重新渲染（NL 解析后用）
PAGES._rerender = function () {
  const h = window.location.hash;
  window.location.hash = '#/__noop';
  setTimeout(() => { window.location.hash = h; }, 0);
};
