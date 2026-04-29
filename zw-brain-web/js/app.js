(function () {
  'use strict';

  const ROLE_NAMES = {
    r1: '上级业务需求发起人',
    r2: '审批承接人员',
    r3: '镇街填报人员',
    r4: '村社区填报人员',
    r5: '审核汇总人员',
    r6: '台账管理员',
    r7: '目录管理员',
    r8: '合规与减负治理',
  };

  let currentRole = 'r1';
  let currentDiscoveryQuery = '';
  let currentSchemaInfo = null;

  const ROUTES = [
    { test: /^#\/p1-workbench$/, page: 'workbench', nav: 'main' },
    { test: /^#\/p2-discovery$/, page: 'discovery', nav: 'main' },
    { test: /^#\/p2-discovery\/resource\/(.+)$/, page: 'resourceDetail', nav: 'main' },
    { test: /^#\/p3-request-flow$/, page: 'requestFlow', nav: 'main' },
    { test: /^#\/p3-request-flow\/request\/(.+)$/, page: 'requestDetail', nav: 'main' },
    { test: /^#\/p3-request-flow\/review\/(.+)$/, page: 'reviewDetail', nav: 'main' },
    { test: /^#\/p4-delivery-exchange$/, page: 'deliveryExchange', nav: 'main' },
    { test: /^#\/p4-delivery-exchange\/task\/(.+)$/, page: 'deliveryTaskDetail', nav: 'main' },
    { test: /^#\/p5-provider$/, page: 'provider', nav: 'main' },
    { test: /^#\/p6-compliance-ops$/, page: 'complianceOps', nav: 'main' },
    { test: /^#\/p6-compliance-ops\/dispute\/(.+)$/, page: 'disputeDetail', nav: 'main' },
    { test: /^#\/p7-zones-pack$/, page: 'zonesPack', nav: 'main' },
    { test: /^#\/p7-zones-pack\/zone\/(.+)$/, page: 'zoneDetail', nav: 'main' },
    { test: /^#\/p8-integration-admin$/, page: 'integrationAdmin', nav: 'main' },
    { test: /^#\/p8-integration-admin\/package\/(.+)$/, page: 'packageDetail', nav: 'main' },
    { test: /^#\/$/, page: 'workbench', nav: 'main' },
  ];

  function encodeParams(params) {
    const url = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.set(k, String(v));
    });
    const text = url.toString();
    return text ? `?${text}` : '';
  }

  function roleCan(roles) {
    return !roles || roles.includes(currentRole);
  }

  async function invokeRead(skillId, params = {}) {
    const payload = Object.assign({ role: currentRole }, params);
    const resp = await fetch(`/api/skills/${skillId}${encodeParams(payload)}`, {
      headers: { Accept: 'application/json' },
    });
    return await handleResponse(resp);
  }

  async function invokeWrite(skillId, payload = {}) {
    const resp = await fetch(`/api/skills/${skillId}`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    return await handleResponse(resp);
  }

  async function handleResponse(resp) {
    const data = await resp.json();
    if (resp.ok) return data;
    const err = new Error(data.detail || data.error || `HTTP ${resp.status}`);
    err.payload = data;
    err.status = resp.status;
    throw err;
  }

  function hydrateSnapshot(snapshot) {
    window.RUNTIME_WORKBENCH = snapshot.workbench;
    window.RUNTIME_DISCOVERY = snapshot.discovery;
    window.RUNTIME_REQUESTS = snapshot.requests;
    window.RUNTIME_APPROVALS = snapshot.approvals;
    window.RUNTIME_DELIVERY_TASKS = snapshot.delivery_tasks;
    window.RUNTIME_PROVIDER = snapshot.provider;
    window.RUNTIME_DISPUTES = snapshot.disputes;
    window.RUNTIME_AUDIT_EVENTS = snapshot.audit_events;
    window.RUNTIME_AUDIT_AI = snapshot.audit_ai;
    window.RUNTIME_ALERTS = snapshot.alerts;
    window.RUNTIME_TICKETS = snapshot.tickets;
    window.RUNTIME_KNOWLEDGE_ARTICLES = snapshot.knowledge_articles;
    window.RUNTIME_ZONES = snapshot.zones;
    window.RUNTIME_CAPABILITY_PACKAGES = snapshot.capability_packages;
    window.RUNTIME_DASHBOARD = snapshot.dashboard;
    const state = Object.assign({}, snapshot.state || {});
    currentRole = currentRole || state.role || 'r1';
    currentDiscoveryQuery = currentDiscoveryQuery || state.discoveryQuery || '';
    state.role = currentRole;
    state.discoveryQuery = currentDiscoveryQuery || state.discoveryQuery || '';
    window.STATE = state;
  }

  async function refreshSnapshot() {
    const snapshot = await fetch('/api/snapshot', { headers: { Accept: 'application/json' } }).then(handleResponse);
    hydrateSnapshot(snapshot);
  }

  async function refreshSchemaInfo() {
    currentSchemaInfo = await invokeRead('system.schema_info', {});
  }

  async function syncRouteData(hash) {
    const route = hash || window.location.hash || '';
    try {
      if (route === '#/p1-workbench') {
        window.RUNTIME_WORKBENCH[currentRole] = await invokeRead('workbench.view', { role: currentRole });
      } else if (route === '#/p2-discovery') {
        const query = currentDiscoveryQuery || window.STATE?.discoveryQuery || '';
        const result = await invokeRead('data.search', { query, page: 1 });
        window.RUNTIME_DISCOVERY.resources = result.results;
        window.RUNTIME_DISCOVERY.aiCopilot = result.summary;
      } else if (route.startsWith('#/p2-discovery/resource/')) {
        const id = decodeURIComponent(route.split('/').pop());
        const resource = await invokeRead('catalog.resource_view', { resource_id: id });
        const index = window.RUNTIME_DISCOVERY.resources.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_DISCOVERY.resources[index] = resource; else window.RUNTIME_DISCOVERY.resources.unshift(resource);
      } else if (route === '#/p3-request-flow') {
        const result = await invokeRead('request.list', {});
        window.RUNTIME_REQUESTS = result.items;
      } else if (route.startsWith('#/p3-request-flow/request/')) {
        const id = decodeURIComponent(route.split('/').pop());
        const request = await invokeRead('request.view', { request_id: id });
        const approval = await invokeRead('approval.view', { request_id: id });
        const requestIndex = window.RUNTIME_REQUESTS.findIndex(item => item.id === id);
        if (requestIndex >= 0) window.RUNTIME_REQUESTS[requestIndex] = request; else window.RUNTIME_REQUESTS.unshift(request);
        const approvalIndex = window.RUNTIME_APPROVALS.findIndex(item => item.id === id);
        if (approvalIndex >= 0) window.RUNTIME_APPROVALS[approvalIndex] = approval; else window.RUNTIME_APPROVALS.unshift(approval);
      } else if (route === '#/p4-delivery-exchange' && roleCan(['r3', 'r4', 'r5'])) {
        const result = await invokeRead('delivery.list', {});
        window.RUNTIME_DELIVERY_TASKS = result.items;
      } else if (route.startsWith('#/p4-delivery-exchange/task/')) {
        const id = decodeURIComponent(route.split('/').pop());
        const task = await invokeRead('delivery.view', { task_id: id });
        const index = window.RUNTIME_DELIVERY_TASKS.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_DELIVERY_TASKS[index] = task; else window.RUNTIME_DELIVERY_TASKS.unshift(task);
      } else if (route === '#/p5-provider' && roleCan(['r6', 'r7'])) {
        window.RUNTIME_PROVIDER = await invokeRead('provider.view', {});
      } else if (route === '#/p6-compliance-ops' && roleCan(['r8'])) {
        const disputes = await invokeRead('governance.dispute_list', {});
        const audit = await invokeRead('audit.list', {});
        const dashboard = await invokeRead('dashboard.render_command_center', {});
        window.RUNTIME_DISPUTES = disputes.items;
        window.RUNTIME_ALERTS = disputes.alerts || window.RUNTIME_ALERTS;
        window.RUNTIME_TICKETS = disputes.tickets || window.RUNTIME_TICKETS;
        window.RUNTIME_KNOWLEDGE_ARTICLES = disputes.knowledgeArticles || window.RUNTIME_KNOWLEDGE_ARTICLES;
        window.RUNTIME_AUDIT_EVENTS = audit.items;
        window.RUNTIME_AUDIT_AI = audit.summary;
        window.RUNTIME_DASHBOARD = dashboard;
      } else if (route.startsWith('#/p6-compliance-ops/dispute/')) {
        const id = decodeURIComponent(route.split('/').pop());
        const dispute = await invokeRead('governance.dispute_view', { dispute_id: id });
        const evidence = await invokeRead('audit.replay_evidence_chain', { dispute_id: id });
        dispute.evidenceReplay = evidence;
        const index = window.RUNTIME_DISPUTES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_DISPUTES[index] = dispute; else window.RUNTIME_DISPUTES.unshift(dispute);
      } else if (route.startsWith('#/p7-zones-pack/zone/')) {
        const id = decodeURIComponent(route.split('/').pop());
        const zone = await invokeRead('zone.view', { zone_id: id });
        const index = window.RUNTIME_ZONES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_ZONES[index] = zone; else window.RUNTIME_ZONES.unshift(zone);
      } else if (route === '#/p7-zones-pack') {
        const result = await invokeRead('zone.list', {});
        window.RUNTIME_ZONES = result.items;
      } else if (route.startsWith('#/p8-integration-admin/package/') && roleCan(['r7'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const pkg = await invokeRead('package.view', { package_id: id });
        const index = window.RUNTIME_CAPABILITY_PACKAGES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_CAPABILITY_PACKAGES[index] = pkg; else window.RUNTIME_CAPABILITY_PACKAGES.unshift(pkg);
      } else if (route === '#/p8-integration-admin' && roleCan(['r7'])) {
        const result = await invokeRead('package.list', {});
        window.RUNTIME_CAPABILITY_PACKAGES = result.items;
      }
    } catch (err) {
      window.UI.toast(err.message || '页面数据刷新失败', 'error');
    }
  }

  /** 固定业务导航 top 与 #app 内容区顶对齐（避免纯 CSS 估算顶栏高度漂移） */
  function syncProductShellNavTop() {
    const grid = document.querySelector('.product-shell-grid');
    const app = document.getElementById('app');
    if (!grid || !app || grid.classList.contains('is-shell-nav-collapsed')) {
      document.documentElement.style.removeProperty('--zw-nav-align-top');
      return;
    }
    const topPx = Math.round(app.getBoundingClientRect().top);
    document.documentElement.style.setProperty('--zw-nav-align-top', `${topPx}px`);
  }

  function scheduleSyncProductShellNavTop() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => syncProductShellNavTop());
    });
  }

  async function performWrite(skillId, payload, successMessage, after) {
    try {
      await invokeWrite(skillId, Object.assign({ role: currentRole, confirmed: true }, payload));
      await refreshSnapshot();
      await syncRouteData(window.location.hash);
      if (after) after(); else dispatch();
      if (successMessage) window.UI.toast(successMessage, 'success');
    } catch (err) {
      window.UI.toast(err.message || '操作失败', 'error');
    }
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
      scheduleSyncProductShellNavTop();
      return;
    }

    const page = window.PAGES && window.PAGES[matched.page];
    if (typeof page !== 'function') {
      document.getElementById('app').innerHTML = renderError(`页面渲染函数缺失：${matched.page}`);
      scheduleSyncProductShellNavTop();
      return;
    }

    document.getElementById('app').innerHTML = page.apply(null, captures);
    highlightNav(matched.nav);
    window.scrollTo(0, 0);

    const onMount = window.PAGES && window.PAGES[matched.page + '_onMount'];
    if (typeof onMount === 'function') {
      onMount.apply(null, captures);
    }
    scheduleSyncProductShellNavTop();
  }

  function highlightNav(navKey) {
    document.querySelectorAll('.nav-tab').forEach(el => {
      if (el.dataset.nav === navKey) el.classList.add('active');
      else el.classList.remove('active');
    });
  }

  function renderNotFound(hash) {
    return `
      <div class="bg-white rounded-2xl p-10 text-center border-default shadow-soft">
        <div class="text-display mb-3">页面未找到</div>
        <p class="text-zw-mute mb-4">没有匹配的业务入口：<code>${hash}</code></p>
        <a href="#/p1-workbench" class="inline-block gov-btn gov-btn-primary px-4 py-2 rounded-lg text-caption">回到首页工作台</a>
      </div>`;
  }

  function renderError(message) {
    return `<div class="bg-red-50 border-error-thin text-red-700 p-4 rounded">${message}</div>`;
  }

  window.UI = {
    toast(message, type = 'info') {
      const toast = document.createElement('div');
      const color =
        type === 'error' ? 'toast-error' : type === 'success' ? 'toast-success' : 'toast-info';
      toast.className = `ui-toast ${color}`;
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2200);
    },
    toggleBusinessNavCollapse() {
      const grid = document.querySelector('.product-shell-grid');
      if (!grid) return;
      const nextCollapsed = !grid.classList.contains('is-shell-nav-collapsed');
      grid.classList.toggle('is-shell-nav-collapsed', nextCollapsed);
      try {
        window.localStorage.setItem('zw-brain-nav-collapsed', nextCollapsed ? '1' : '0');
      } catch (_) {}
      const expanded = nextCollapsed ? 'false' : 'true';
      document.querySelectorAll('[data-business-nav-toggle]').forEach(el => {
        el.setAttribute('aria-expanded', expanded);
      });
      const rail = document.querySelector('.product-nav-collapsed-rail');
      if (rail) rail.setAttribute('aria-hidden', nextCollapsed ? 'false' : 'true');
      const wrap = document.getElementById('product-nav-panel-body-wrap');
      if (wrap) wrap.setAttribute('aria-hidden', nextCollapsed ? 'true' : 'false');
      scheduleSyncProductShellNavTop();
    },
    roleLabel(role) {
      return ROLE_NAMES[role] || role;
    },
    can(roles) {
      return roleCan(roles);
    },
  };

  window.ACTIONS = {
    async setDiscoveryQuery(event) {
      event.preventDefault();
      const input = document.getElementById('discovery-q');
      currentDiscoveryQuery = input ? input.value.trim() : '';
      if (!currentDiscoveryQuery) {
        window.UI.toast('请输入要检索的涉企需求', 'error');
        return;
      }
      try {
        const result = await invokeRead('data.search', { query: currentDiscoveryQuery, page: 1 });
        window.RUNTIME_DISCOVERY.resources = result.results;
        window.RUNTIME_DISCOVERY.aiCopilot = result.summary;
        window.STATE.discoveryQuery = currentDiscoveryQuery;
        dispatch();
        window.UI.toast('已按真实业务语义重排复用建议', 'success');
      } catch (err) {
        window.UI.toast(err.message || '检索失败', 'error');
      }
    },
    createRequest(resourceId) {
      performWrite('request.create', { resource_id: resourceId, query: currentDiscoveryQuery || window.STATE?.discoveryQuery || '' }, '已发起标准复用申请并进入受控准入', async () => {
        await refreshSnapshot();
        const created = window.RUNTIME_REQUESTS.find(item => item.resourceId === resourceId && item.status === 'pending');
        if (created) {
          window.location.hash = `#/p3-request-flow/request/${created.id}`;
        } else {
          window.location.hash = '#/p3-request-flow';
        }
      });
    },
    submitRequest(requestId = 'REQ-2026-04-25-0011') {
      performWrite('request.submit', { request_id: requestId }, '已重新提交并进入受控准入', () => {
        window.location.hash = `#/p3-request-flow/request/${requestId}`;
      });
    },
    approveRequest(requestId) {
      performWrite('approval.review_decide', { request_id: requestId, decision: 'approve' }, '已通过并下发基层补录任务');
    },
    returnForFix(requestId) {
      performWrite('approval.review_decide', { request_id: requestId, decision: 'return_for_fix' }, '已退回补正');
    },
    rejectRequest(requestId) {
      performWrite('approval.review_decide', { request_id: requestId, decision: 'reject' }, '已驳回该申请');
    },
    submitSupplement(requestId) {
      performWrite('supplement.submit', { request_id: requestId }, '差异补录已提交，进入汇总确认');
    },
    confirmSummary(requestId) {
      performWrite('summary.confirm', { request_id: requestId }, '已确认自动汇总，进入回流确认');
    },
    confirmBackflow(taskId) {
      performWrite('backflow.confirm', { task_id: taskId }, '已确认回流并同步模板治理视图');
    },
    triggerDeliveryRecovery(taskId) {
      performWrite('delivery.trigger_recovery', { task_id: taskId }, '恢复流程已触发');
    },
    configurePackageExposure(packageId, mode) {
      performWrite('package.configure_exposure', { package_id: packageId, mode }, mode === 'tighten' ? '暴露面已收紧' : '暴露面已扩展');
    },
    progressDispute(disputeId) {
      performWrite('compliance.investigate_case', { dispute_id: disputeId, action: 'progress' }, '争议调查已推进');
    },
    escalateDispute(disputeId) {
      performWrite('compliance.investigate_case', { dispute_id: disputeId, action: 'escalate' }, '争议已升级治理');
    },
    manageCatalogEntry(catalogId, action) {
      performWrite('catalog.manage_entry', { catalog_id: catalogId, action }, action === 'publish' ? '目录条目已发布' : '目录说明已修正');
    },
    manageResourceAsset(resourceId, action) {
      performWrite('resource.manage_asset', { resource_id: resourceId, action }, action === 'publish' ? '资源资产已发布' : '资源资产已暂停共享');
    },
    publishZoneTopicProjection(zoneId) {
      performWrite('zone.publish_topic_projection', { zone_id: zoneId }, '专区正式投影已发布');
    },
    reconcileDeliveryReceipt(taskId) {
      performWrite('delivery.reconcile_receipt', { task_id: taskId }, '交付回执已完成对账');
    },
    publishProviderService(serviceId) {
      performWrite('service.publish_or_suspend', { service_id: serviceId, action: 'publish' }, '供给服务已发布');
    },
    suspendProviderService(serviceId) {
      performWrite('service.publish_or_suspend', { service_id: serviceId, action: 'suspend' }, '供给服务已暂停');
    },
    registerPackageVersion(packageId) {
      performWrite('package.register_version', { package_id: packageId }, '能力包版本已登记');
    },
    applyPackageTenantPolicy(packageId) {
      performWrite('package.apply_tenant_policy', { package_id: packageId }, '租户策略已生效');
    },
    approvePackage(packageId) {
      performWrite('package.review_decide', { package_id: packageId, decision: 'approve' }, '能力包已批准上线');
    },
    returnPackageFix(packageId) {
      performWrite('package.review_decide', { package_id: packageId, decision: 'return_for_fix' }, '能力包已退回补充');
    },
    rejectPackage(packageId) {
      performWrite('package.review_decide', { package_id: packageId, decision: 'reject' }, '能力包已驳回');
    },
    toggleOutage() {
      performWrite('system.toggle_outage', {}, '已切换主脑故障态');
    },
    noop(message) {
      window.UI.toast(message || '当前阶段暂无可办理动作', 'info');
    },
  };

  let productShellNavTopResizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(productShellNavTopResizeTimer);
    productShellNavTopResizeTimer = setTimeout(scheduleSyncProductShellNavTop, 120);
  });

  window.addEventListener('hashchange', async () => {
    await syncRouteData(window.location.hash);
    dispatch();
  });
  window.addEventListener('DOMContentLoaded', async () => {
    const switcher = document.getElementById('role-switch');
    if (switcher) {
      switcher.addEventListener('change', async event => {
        currentRole = event.target.value;
        if (window.STATE) window.STATE.role = currentRole;
        await syncRouteData(window.location.hash || '#/p1-workbench');
        dispatch();
      });
    }
    try {
      await refreshSnapshot();
      await refreshSchemaInfo();
      if (switcher) switcher.value = currentRole;
      if (!window.location.hash) {
        window.location.hash = '#/p1-workbench';
      } else {
        await syncRouteData(window.location.hash);
        dispatch();
      }
    } catch (err) {
      document.getElementById('app').innerHTML = renderError(err.message || '初始化失败');
    }
  });
})();
