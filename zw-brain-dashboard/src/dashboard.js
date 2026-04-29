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
    <article class="metric-card metric-card-static">
      <div class="metric-label">${item.label}</div>
      <div class="metric-value">${item.value}</div>
      <div class="metric-trend">${item.trend}</div>
    </article>`;
}

function render(data) {
  app.innerHTML = `
    <main class="dashboard-shell">
      <section class="hero">
        <div class="hero-main">
          <div class="eyebrow">运行态势</div>
          <h1>一屏看清数据共享是否畅通、基层负担是否下降、异常责任是否可追。</h1>
          <p>当前模式：<strong>${data.mode}</strong>${data.brainOutage ? ' · 主应用故障，已展示最近快照' : ' · 主应用运行正常'}。重点关注共享交换进展、基层减负变化和异常责任链。</p>
          ${data.brainOutage ? '<div class="snapshot-banner">当前为快照模式：主应用故障不影响大屏继续展示最近一次可用快照，但所有数字停止刷新。</div>' : ''}
          <div class="hero-kpis">
            <div><span>今日闭环任务</span><strong>${data.summary.flowToday}</strong></div>
            <div><span>实时查询压力</span><strong>${data.summary.qps}</strong></div>
            <div><span>在线协同单元</span><strong>${data.summary.agentsOnline}</strong></div>
            <div><span>异常告警</span><strong>${data.summary.alerts}</strong></div>
          </div>
        </div>
        <aside class="hero-side">
          <h2>指挥辅助结论</h2>
          <p style="margin-top:12px">${data.suggestions.body}</p>
          <ul>
            ${data.suggestions.evidence.map(item => `<li>${item}</li>`).join('')}
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
          <h2>${data.suggestions.title}</h2>
          <ul class="evidence-list">
            ${data.suggestions.evidence.map(item => `<li>${item}</li>`).join('')}
          </ul>
          <div class="next-action">建议动作：${data.suggestions.nextAction}</div>
          <div class="owner">责任人：${data.suggestions.owner}</div>
        </aside>
      </section>
    </main>`;
}

loadDashboard().then(render).catch((err) => {
  app.innerHTML = `<main class="dashboard-shell"><section class="panel"><h1>加载失败</h1><p>${err.message}</p></section></main>`;
});
