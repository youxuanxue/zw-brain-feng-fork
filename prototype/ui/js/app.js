/* ---------------------------------------------------------------------------
   政务大脑 GATE-1 原型 · 路由 + 启动
   纯 vanilla：hash 路由，0 build，0 framework
   --------------------------------------------------------------------------- */

(function () {
  'use strict';

  // 全局状态（mock，重新加载页面会重置——原型不做持久化）
  window.STATE = {
    role: 'op',
    nlQuery: '',
    parsedConditions: null,
    pendingRequest: null,
    appliedRequests: [],
    brainOutage: false,
  };

  // ---- 路由表：hash 模式匹配 → 页面 render 函数 ----
  // 主大脑域共 22 条路由 → 覆盖 baseline §7.3 列出的 10 个 WebUI 核心场景页
  const ROUTES = [
    // 工作台（§7.3 第 1 页）
    { test: /^#\/?$/,                      page: 'workbench',     nav: 'brain' },

    // 数据：检索 → 详情 → 申请 → 状态（§7.3 第 2 页一组）
    { test: /^#\/search$/,                 page: 'search',        nav: 'brain' },
    { test: /^#\/dataset\/(.+)$/,          page: 'datasetDetail', nav: 'brain' },
    { test: /^#\/apply\/(.+)$/,            page: 'apply',         nav: 'brain' },
    { test: /^#\/request\/(.+)$/,          page: 'requestStatus', nav: 'brain' },

    // 资源 / 目录 / 服务管理（§7.3 第 3 页 · K1+K2+K3）
    { test: /^#\/manage(?:\/(catalog|resource|service))?$/, page: 'manage',  nav: 'brain' },

    // 申请审批（§7.3 第 4 页 · K4）
    { test: /^#\/review\/(.+)$/,           page: 'requestReview', nav: 'brain' },

    // 数据交换任务（§7.3 第 5 页 · K5）
    { test: /^#\/exchange$/,               page: 'exchange',       nav: 'brain' },
    { test: /^#\/exchange\/(.+)$/,         page: 'exchangeDetail', nav: 'brain' },

    // 异议处理（§7.3 第 6 页 · K8 之 a）
    { test: /^#\/dispute$/,                page: 'dispute',        nav: 'brain' },
    { test: /^#\/dispute\/(.+)$/,          page: 'disputeDetail',  nav: 'brain' },

    // 合规督导 + 审计回溯（§7.3 第 7 页 · K8 之 b / K9）
    { test: /^#\/compliance$/,             page: 'compliance',     nav: 'brain' },

    // Skill 市场（§7.3 第 8 页 · 申请方/平台共用）
    { test: /^#\/skill-market$/,           page: 'skillMarket',    nav: 'brain' },
    { test: /^#\/skill-market\/propose$/,  page: 'skillPropose',   nav: 'brain' },

    // 平台运营面板（§7.3 第 9 页 · 内部 KPI · 区别于 K12 大屏）
    { test: /^#\/ops$/,                    page: 'ops',            nav: 'brain' },

    // 共享专区（§7.3 第 10 页 · K11）
    { test: /^#\/zones$/,                  page: 'zones',          nav: 'brain' },
    { test: /^#\/zone\/(.+)$/,             page: 'zoneDetail',     nav: 'brain' },

    // 大屏（K12）
    { test: /^#\/dashboard$/,              page: 'dashboard',      nav: 'dashboard' },
    { test: /^#\/dashboard\/alert$/,       page: 'dashboardAlert', nav: 'dashboard' },

    // Agent 入口（不算 §7.3 的 10 页 · 给开发者看的契约文档站）
    { test: /^#\/agent$/,                  page: 'agentHome',        nav: 'agent' },
    { test: /^#\/agent\/skills$/,          page: 'agentSkills',      nav: 'agent' },
    { test: /^#\/agent\/skill\/(.+)$/,     page: 'agentSkillDetail', nav: 'agent' },
    { test: /^#\/agent\/invoke\/(.+)$/,    page: 'agentInvoke',      nav: 'agent' },
  ];

  function dispatch() {
    const hash = window.location.hash || '#/';
    let matched = null, captures = [];
    for (const r of ROUTES) {
      const m = hash.match(r.test);
      if (m) { matched = r; captures = m.slice(1); break; }
    }
    if (!matched) {
      document.getElementById('app').innerHTML = renderNotFound(hash);
      highlightNav(null);
      return;
    }
    const fn = window.PAGES && window.PAGES[matched.page];
    if (typeof fn !== 'function') {
      document.getElementById('app').innerHTML = renderError(`页面渲染函数缺失：${matched.page}`);
      return;
    }
    document.getElementById('app').innerHTML = fn.apply(null, captures);
    highlightNav(matched.nav);
    updateHealth();
    // 滚回顶部 + 触发页面级 onMount（如果有）
    window.scrollTo(0, 0);
    if (window.PAGES && typeof window.PAGES[matched.page + '_onMount'] === 'function') {
      window.PAGES[matched.page + '_onMount'].apply(null, captures);
    }
  }

  function highlightNav(navKey) {
    document.querySelectorAll('.nav-tab').forEach(el => {
      if (el.dataset.nav === navKey) el.classList.add('active');
      else el.classList.remove('active');
    });
  }

  function updateHealth() {
    const el = document.getElementById('health-brain');
    if (!el) return;
    if (window.STATE.brainOutage) {
      el.className = 'text-red-400';
      el.textContent = '✗';
    } else {
      el.className = 'text-green-300';
      el.textContent = '✓';
    }
  }

  function renderNotFound(hash) {
    return `
      <div class="bg-white rounded-lg p-10 text-center border border-zw-line">
        <div class="text-2xl mb-3">🧭 404</div>
        <p class="text-zw-mute mb-4">没有匹配的路由：<code>${hash}</code></p>
        <a href="#/" class="inline-block bg-zw-primary text-white px-4 py-2 rounded text-sm">回到首页</a>
      </div>`;
  }
  function renderError(msg) {
    return `<div class="bg-red-50 border border-red-200 text-red-700 p-4 rounded">${msg}</div>`;
  }

  // ---- 角色切换 ----
  document.getElementById('role-switch').addEventListener('change', (e) => {
    window.STATE.role = e.target.value;
    dispatch(); // 重新渲染当前页（不同角色看到的工作台/审批入口不同）
  });

  // ---- 首次加载 + hash 变化 ----
  window.addEventListener('hashchange', dispatch);
  window.addEventListener('DOMContentLoaded', () => {
    if (!window.location.hash) window.location.hash = '#/';
    else dispatch();
  });

  // ---- 全局工具：模板插值 ----
  window.UI = {
    // 模拟异步操作，返回 Promise
    sleep: (ms) => new Promise(r => setTimeout(r, ms)),
    // 简单 toast
    toast(msg, type = 'info') {
      const el = document.createElement('div');
      const color = type === 'error' ? 'bg-red-600' : type === 'success' ? 'bg-green-600' : 'bg-zw-primary';
      el.className = `fixed top-20 right-6 ${color} text-white px-4 py-2 rounded shadow-lg z-50 text-sm`;
      el.textContent = msg;
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 2400);
    },
    // 当前角色判断
    isLeader:   () => window.STATE.role === 'leader',
    isAdmin:    () => window.STATE.role === 'admin' || window.STATE.role === 'platform',
    isAgentDev: () => window.STATE.role === 'agent-dev',
  };
})();
