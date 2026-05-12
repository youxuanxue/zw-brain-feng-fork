const app = document.getElementById('app');

async function loadDashboard() {
  const resp = await fetch('/api/skills/dashboard.render_command_center', {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeMetricLabel(label) {
  return {
    '实时查询压力': '查询响应',
    '在线协同单元': '协同岗位',
    '异常告警': '待处置异常',
  }[label] || label;
}

function metricCard(item) {
  return `
    <article class="metric-card metric-card-static">
      <div class="metric-label">${escapeHtml(normalizeMetricLabel(item.label))}</div>
      <div class="metric-value">${escapeHtml(item.value)}</div>
      <div class="metric-trend">${escapeHtml(item.trend)}</div>
    </article>`;
}

function render(data) {
  app.innerHTML = `
    <main class="dashboard-shell">
      <section class="hero">
        <div class="hero-main">
          <div class="eyebrow">运行态势</div>
          <h1>一屏看清共享进展、基层减负和异常处置。</h1>
          <p>当前模式：<strong>${escapeHtml(data.mode)}</strong>${data.brainOutage ? ' · 主办事服务维护中，当前展示最近一次核验快照' : ' · 主办事服务运行正常'}。</p>
          ${data.brainOutage ? `<div class="snapshot-banner">快照模式已启用：展示最近一次核验数据，更新时点 ${escapeHtml(data.snapshotAt || '待同步')}。</div>` : ''}
          <div class="hero-kpis">
            <div><span>今日闭环任务</span><strong>${escapeHtml(data.summary.flowToday)}</strong></div>
            <div><span>查询响应</span><strong>${escapeHtml(data.summary.qps)}</strong></div>
            <div><span>协同岗位</span><strong>${escapeHtml(data.summary.agentsOnline)}</strong></div>
            <div><span>待处置异常</span><strong>${escapeHtml(data.summary.alerts)}</strong></div>
          </div>
        </div>
        <aside class="hero-side">
          <h2>指挥辅助结论</h2>
          <p style="margin-top:12px">${escapeHtml(data.suggestions.body)}</p>
          <ul>
            ${data.suggestions.evidence.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
          </ul>
        </aside>
      </section>

      <section class="metrics-grid">
        ${data.burdenMetrics.map(metricCard).join('')}
      </section>

      <section class="content-grid">
        <div class="panel">
          <h2>共享交换主链路态势</h2>
          <p style="margin-top:10px">展示发现资源、申请审批、基层补录、自动汇总、交付回流和治理审计的实时进展。</p>
          <div class="chain-grid">
            <div class="chain-node"><span>01</span><strong>发现资源</strong><em>模板和专题包成为默认入口</em></div>
            <div class="chain-node"><span>02</span><strong>申请准入</strong><em>重复要数在审批前被识别</em></div>
            <div class="chain-node"><span>03</span><strong>差异补录</strong><em>基层只补现场动态字段</em></div>
            <div class="chain-node"><span>04</span><strong>汇总交付</strong><em>自动汇总后人工确认异常</em></div>
            <div class="chain-node"><span>05</span><strong>回流治理</strong><em>高频字段进入模板升级候选</em></div>
          </div>
        </div>
        <aside class="panel">
          <h2>${escapeHtml(data.suggestions.title)}</h2>
          <ul class="evidence-list">
            ${data.suggestions.evidence.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
          </ul>
          <div class="next-action"><span class="hint-label">建议动作</span>${escapeHtml(data.suggestions.nextAction)}</div>
          <div class="owner"><span class="hint-label">责任人</span>${escapeHtml(data.suggestions.owner)}</div>
        </aside>
      </section>
    </main>`;
}

loadDashboard().then(render).catch(() => {
  app.innerHTML = '<main class="dashboard-shell"><section class="panel"><h1>加载失败</h1><p>当前大屏数据暂不可用，请稍后重试。</p></section></main>';
});
