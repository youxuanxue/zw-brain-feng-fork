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

function metricCard(item) {
  return `
    <article class="metric-card">
      <div class="metric-label">${item.label}</div>
      <div class="metric-value">${item.value}</div>
      <div class="metric-trend">${item.trend}</div>
    </article>`;
}

function render(data) {
  app.innerHTML = `
    <main class="dashboard-shell">
      <header class="hero">
        <div>
          <div class="eyebrow">K12 指挥中心大屏</div>
          <h1>减负治理与异常态势只读投影</h1>
          <p>当前模式：<strong>${data.mode}</strong>${data.brainOutage ? ' · 主脑故障已切到快照态' : ' · 主脑运行正常'}</p>
        </div>
        <div class="hero-kpis">
          <div><span>今日主链流转</span><strong>${data.summary.flowToday}</strong></div>
          <div><span>QPS</span><strong>${data.summary.qps}</strong></div>
          <div><span>在线 Agent</span><strong>${data.summary.agentsOnline}</strong></div>
          <div><span>告警</span><strong>${data.summary.alerts}</strong></div>
        </div>
      </header>

      <section class="metrics-grid">
        ${data.burdenMetrics.map(metricCard).join('')}
      </section>

      <section class="insight-card">
        <h2>${data.suggestions.title}</h2>
        <p>${data.suggestions.body}</p>
        <ul>
          ${data.suggestions.evidence.map(item => `<li>${item}</li>`).join('')}
        </ul>
        <div class="next-action">下一步：${data.suggestions.nextAction}</div>
        <div class="owner">责任人：${data.suggestions.owner}</div>
      </section>
    </main>`;
}

loadDashboard().then(render).catch((err) => {
  app.innerHTML = `<main class="dashboard-shell"><section class="insight-card"><h1>加载失败</h1><p>${err.message}</p></section></main>`;
});
