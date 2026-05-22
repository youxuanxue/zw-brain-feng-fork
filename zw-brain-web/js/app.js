(function () {
  'use strict';

  // 2026-05-19 retrofit：用户角色对齐旧平台 ROLE_* 7 角色（详见 docs/approved/zw-brain-roles.md）
  const ROLE_NAMES = {
    ROLE_ORGAN_OPERATER: '部门操作员',
    ROLE_ORGAN_MANAGER: '部门管理员',
    ROLE_BUSIAUDIT: '业务运营员',
    ROLE_SECURITY_AUDIT: '安全审计员',
    ROLE_SECURITY_ADMIN: '安全管理员',
    ROLE_SYSTEM: '平台运维员',
    // 平台实施工程师（非客户业务角色）—— M0 迁移监控、内部诊断、
    // 客户验收日打开 P0 给客户高层看一眼。不出现在岗位切换下拉。
    admin: '平台实施工程师',
  };
  const _VALID_ROLES = new Set(Object.keys(ROLE_NAMES));

  let currentRole = 'ROLE_ORGAN_OPERATER';
  // dev/QA only: allow ?role=ROLE_*|admin in URL to set initial role
  // (used for visual-review screenshots + 实施工程师直达 P0)
  try {
    const _urlRole = new URLSearchParams(window.location.search).get('role');
    if (_urlRole && _VALID_ROLES.has(_urlRole)) currentRole = _urlRole;
  } catch (_) { /* non-fatal */ }
  let currentDiscoveryQuery = '';
  let currentSchemaInfo = null;
  let snapshotReady = false;

  const ROUTES = [
    { test: /^#\/login$/, page: 'login', nav: null },
    { test: /^#\/migration-acceptance$/, page: 'migrationAcceptance', nav: 'main' },
    { test: /^#\/profile$/, page: 'profile', nav: null },
    { test: /^#\/workbench$/, page: 'workbench', nav: 'main' },
    { test: /^#\/discovery$/, page: 'discovery', nav: 'main' },
    { test: /^#\/discovery\/catalog-browse$/, page: 'catalogBrowse', nav: 'main' },
    { test: /^#\/discovery\/resource\/(.+)$/, page: 'resourceDetail', nav: 'main' },
    { test: /^#\/request-flow$/, page: 'requestFlow', nav: 'main' },
    { test: /^#\/request-flow\/request\/(.+)$/, page: 'requestDetail', nav: 'main' },
    { test: /^#\/request-flow\/review\/(.+)$/, page: 'reviewDetail', nav: 'main' },
    { test: /^#\/delivery-exchange$/, page: 'deliveryExchange', nav: 'main' },
    { test: /^#\/delivery-exchange\/task\/(.+)$/, page: 'deliveryTaskDetail', nav: 'main' },
    { test: /^#\/delivery-exchange\/credential\/(.+)$/, page: 'deliveryCredential', nav: 'main' },
    { test: /^#\/provider$/, page: 'provider', nav: 'main' },
    { test: /^#\/provider\/wizard\/reverse-catalog$/, page: 'providerWizardReverseCatalog', nav: 'main' },
    { test: /^#\/provider\/wizard\/api-service$/, page: 'providerWizardApiService', nav: 'main' },
    { test: /^#\/provider\/wizard\/quality-rule$/, page: 'providerWizardQualityRule', nav: 'main' },
    { test: /^#\/provider\/inbox\/field-decision$/, page: 'providerInboxFieldDecision', nav: 'main' },
    { test: /^#\/provider\/inbox\/field-decision\/(.+)$/, page: 'providerInboxFieldDecisionDetail', nav: 'main' },
    { test: /^#\/provider\/inbox\/hookup-review$/, page: 'providerInboxHookupReview', nav: 'main' },
    { test: /^#\/provider\/inbox\/demand-match$/, page: 'providerInboxDemandMatch', nav: 'main' },
    { test: /^#\/provider\/inbox\/demand-match\/(.+)$/, page: 'providerInboxDemandMatchDetail', nav: 'main' },
    { test: /^#\/compliance-ops$/, page: 'complianceOps', nav: 'main' },
    { test: /^#\/compliance-ops\/dispute\/(.+)$/, page: 'disputeDetail', nav: 'main' },
    { test: /^#\/zones-pack$/, page: 'zonesPack', nav: 'main' },
    { test: /^#\/zones-pack\/zone\/(.+)$/, page: 'zoneDetail', nav: 'main' },
    { test: /^#\/integration-admin$/, page: 'integrationAdmin', nav: 'main' },
    { test: /^#\/integration-admin\/iam-governance$/, page: 'iamGovernance', nav: 'main' },
    { test: /^#\/integration-admin\/package\/(.+)$/, page: 'packageDetail', nav: 'main' },
    { test: /^#\/$/, page: 'workbench', nav: 'main' },
  ];

  (function assertRouteAccessParity() {
    if (typeof window.ZW_PAGE_ACCESS === 'undefined') return;
    const routePages = new Set(ROUTES.map(r => r.page));
    const missing = [...routePages].filter(p => !Object.prototype.hasOwnProperty.call(window.ZW_PAGE_ACCESS, p));
    if (missing.length) {
      throw new Error(`[zw-brain] ZW_PAGE_ACCESS missing keys for ROUTES: ${missing.join(', ')}`);
    }
  })();

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

  function pickRoleLandingHash() {
    const ACCESS = window.ZW_PAGE_ACCESS || {};
    const CANDIDATES = [
      ['workbench', '#/workbench'],
      ['discovery', '#/discovery'],
      ['deliveryExchange', '#/delivery-exchange'],
      ['complianceOps', '#/compliance-ops'],
      ['zonesPack', '#/zones-pack'],
    ];
    for (const [page, route] of CANDIDATES) {
      if (ACCESS[page] && ACCESS[page].includes(currentRole)) return route;
    }
    return null;
  }

  async function invokeRead(skillId, params = {}) {
    const payload = Object.assign({ role: currentRole }, params);
    const resp = await window.ZW_AUTH.authFetch(`/api/skills/${skillId}${encodeParams(payload)}`, {
      headers: { Accept: 'application/json' },
    });
    return await handleResponse(resp);
  }

  async function invokeWrite(skillId, payload = {}) {
    const resp = await window.ZW_AUTH.authFetch(`/api/skills/${skillId}`, {
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
    window.RUNTIME_MIGRATION_ACCEPTANCE = window.RUNTIME_MIGRATION_ACCEPTANCE || null;
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
    // K12 dashboard 数据块已退役 (R17 / v4.1)；保留 RUNTIME_DASHBOARD 兜底以兼容 pages.js defensive guard
    window.RUNTIME_DASHBOARD = snapshot.dashboard || {};
    window.ZW_WEBUI = snapshot.webui || {};
    window.CATALOG_BROWSE_FILTERS = window.CATALOG_BROWSE_FILTERS || { page: 1, limit: 20, lifecycle: 'active', kind: 'real' };
    window.RUNTIME_CATALOG_BROWSE = window.RUNTIME_CATALOG_BROWSE || { items: [], total: 0, page: 1, limit: 20 };
    const state = Object.assign({}, snapshot.state || {});
    currentRole = state.role || currentRole || 'ROLE_ORGAN_OPERATER';
    currentDiscoveryQuery = state.discoveryQuery || currentDiscoveryQuery || '';
    state.role = currentRole;
    state.discoveryQuery = currentDiscoveryQuery;
    window.STATE = state;
    syncDeploymentChip();
    syncHeaderIdentityAndLegal();
  }

  function syncDeploymentChip() {
    const el = document.getElementById('deployment-label');
    if (!el) return;
    const label = window.ZW_WEBUI && window.ZW_WEBUI.deploymentLabel;
    if (label) {
      el.textContent = label;
      el.hidden = false;
    } else {
      el.textContent = '';
      el.hidden = true;
    }
  }

  function syncHeaderIdentityAndLegal() {
    const cfg = window.ZW_WEBUI || {};
    const user = window.ZW_AUTH && window.ZW_AUTH.getCurrentUser ? window.ZW_AUTH.getCurrentUser() : null;
    const identityEl = document.getElementById('identity-label');
    const identityText = (cfg.identityLabel || '').trim();
    if (identityEl) {
      // When a user is authenticated, the user-menu button already shows the
      // display name. Showing identity-label "当前账号：..." next to it would
      // duplicate the same string. Keep identity-label only as the unauthenticated
      // anchor text (e.g. "当前账号" / a custom identityLabel from config).
      if (user) {
        identityEl.hidden = true;
        identityEl.textContent = '';
      } else {
        identityEl.hidden = false;
        identityEl.textContent = identityText || '当前账号';
      }
    }
    // P7 — when an authenticated user is in session, hide the redundant 登录 nav link.
    const loginEl = document.getElementById('zw-login-nav-link');
    if (loginEl) {
      const isAuthenticated = !!user || (!!identityText && identityText !== '当前账号');
      loginEl.style.display = isAuthenticated ? 'none' : '';
    }
    const loginButton = document.getElementById('zw-login-button');
    if (loginButton) loginButton.hidden = !!user;
    const userMenu = document.getElementById('user-menu');
    if (userMenu) userMenu.hidden = !user;
    const userName = document.getElementById('user-menu-name');
    if (userName && user) userName.textContent = user.displayName || user.username || '当前用户';
    const legalEl = document.getElementById('legal-notice');
    if (legalEl) {
      const text = String(cfg.legalNotice || '').trim();
      legalEl.textContent = text;
      legalEl.hidden = !text;
    }
    const roleControl = document.getElementById('role-control');
    if (roleControl) {
      roleControl.hidden = !cfg.allowRoleSwitch;
    }
  }

  async function refreshSnapshot() {
    const snapshot = await window.ZW_AUTH.authFetch(`/api/snapshot${encodeParams({ role: currentRole })}`, {
      headers: { Accept: 'application/json' },
    }).then(handleResponse);
    hydrateSnapshot(snapshot);
    snapshotReady = true;
  }

  async function refreshSchemaInfo() {
    currentSchemaInfo = await invokeRead('system.schema_info', {});
  }

  function customerSafeError(err, fallback) {
    const raw = String((err && err.message) || err || '');
    if (/lacks permissions|permission|forbidden|403|skill|capability|execute|traceback|stack|http/i.test(raw)) {
      return fallback || '当前账号暂不能完成该操作，请回到可办理入口继续。';
    }
    if (/network|timeout|unavailable|refused|failed|error|500|502|503|504/i.test(raw)) {
      return fallback || '当前服务暂不可用，请稍后重试。';
    }
    return fallback || '操作未完成，请稍后重试。';
  }

  async function syncRouteData(hash) {
    if (!snapshotReady) return;
    const rawRoute = hash || window.location.hash || '';
    // 与 dispatch() 一致：剥掉 query/fragment 噪音
    const route = rawRoute.split('?')[0].split('&')[0];
    try {
      if (route === '#/workbench') {
        window.RUNTIME_WORKBENCH[currentRole] = await invokeRead('workbench.view', { role: currentRole });
      } else if (route === '#/discovery' && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const query = currentDiscoveryQuery || window.STATE?.discoveryQuery || '';
        // data.search requires a non-empty query — on first visit show the seed
        // resources from snapshot and wait for the user to type, rather than
        // erroring out the whole page.
        if (query) {
          const result = await invokeRead('data.search', { query, page: 1 });
          window.RUNTIME_DISCOVERY.resources = result.results;
          window.RUNTIME_DISCOVERY.aiCopilot = result.summary;
          currentDiscoveryQuery = result.query || query;
          window.STATE.discoveryQuery = currentDiscoveryQuery;
        }
      } else if (route === '#/discovery/catalog-browse' && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const filters = window.CATALOG_BROWSE_FILTERS || {};
        const result = await invokeRead('catalog.browse', {
          page: filters.page || 1,
          limit: filters.limit || 20,
          lifecycle: filters.lifecycle || 'active',
          kind: filters.kind || 'real',
        });
        window.RUNTIME_CATALOG_BROWSE = result;
      } else if (route.startsWith('#/discovery/resource/') && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const resource = await invokeRead('catalog.resource_view', { resource_id: id });
        const index = window.RUNTIME_DISCOVERY.resources.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_DISCOVERY.resources[index] = resource; else window.RUNTIME_DISCOVERY.resources.unshift(resource);
      } else if (route === '#/request-flow' && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'])) {
        const result = await invokeRead('request.list', {});
        window.RUNTIME_REQUESTS = result.items;
      } else if (route.startsWith('#/request-flow/request/') && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const request = await invokeRead('request.view', { request_id: id });
        const requestIndex = window.RUNTIME_REQUESTS.findIndex(item => item.id === id);
        if (requestIndex >= 0) window.RUNTIME_REQUESTS[requestIndex] = request; else window.RUNTIME_REQUESTS.unshift(request);
      } else if (route.startsWith('#/request-flow/review/') && roleCan(['ROLE_ORGAN_MANAGER'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const request = await invokeRead('request.view', { request_id: id });
        const approval = await invokeRead('approval.view', { request_id: id });
        const requestIndex = window.RUNTIME_REQUESTS.findIndex(item => item.id === id);
        if (requestIndex >= 0) window.RUNTIME_REQUESTS[requestIndex] = request; else window.RUNTIME_REQUESTS.unshift(request);
        const approvalIndex = window.RUNTIME_APPROVALS.findIndex(item => item.id === id);
        if (approvalIndex >= 0) window.RUNTIME_APPROVALS[approvalIndex] = approval; else window.RUNTIME_APPROVALS.unshift(approval);
      } else if (route === '#/delivery-exchange' && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        // ROLE_ORGAN_OPERATER 没有 delivery.list.execute 权限（治理侧 skill）；snapshot 已带 role-filtered
        // delivery_tasks，refresh 失败时沿用 snapshot 不弹错（其它角色失败仍向上冒泡）。
        try {
          const result = await invokeRead('delivery.list', {});
          window.RUNTIME_DELIVERY_TASKS = result.items;
        } catch (err) {
          if (currentRole !== 'ROLE_ORGAN_OPERATER') throw err;
        }
      } else if (route.startsWith('#/delivery-exchange/task/') && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const id = decodeURIComponent(route.split('/').pop());
        try {
          const task = await invokeRead('delivery.view', { task_id: id });
          const index = window.RUNTIME_DELIVERY_TASKS.findIndex(item => item.id === id);
          if (index >= 0) window.RUNTIME_DELIVERY_TASKS[index] = task; else window.RUNTIME_DELIVERY_TASKS.unshift(task);
        } catch (err) {
          if (currentRole !== 'ROLE_ORGAN_OPERATER') throw err;
        }
      } else if (route.startsWith('#/delivery-exchange/credential/') && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const requestId = decodeURIComponent(route.split('/').pop());
        try {
          const credentialView = await invokeRead('credential.query', { request_id: requestId });
          window.RUNTIME_CREDENTIAL_VIEW = credentialView;
        } catch (err) {
          // 拒绝时仍渲染页面（显示 not_issued + 错误提示）
          window.RUNTIME_CREDENTIAL_VIEW = { request_id: requestId, status: 'error', hint: err.message };
        }
      } else if (route === '#/provider' && roleCan(['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT'])) {
        window.RUNTIME_PROVIDER = await invokeRead('provider.view', {});
      } else if (route === '#/compliance-ops' && roleCan(['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        // K12 dashboard / dashboard.render_command_center Skill 已退役 (R17 / v4.1)
        const disputes = await invokeRead('governance.dispute_list', {});
        const audit = await invokeRead('audit.list', {});
        window.RUNTIME_DISPUTES = disputes.items;
        window.RUNTIME_ALERTS = disputes.alerts || window.RUNTIME_ALERTS;
        window.RUNTIME_TICKETS = disputes.tickets || window.RUNTIME_TICKETS;
        window.RUNTIME_KNOWLEDGE_ARTICLES = disputes.knowledgeArticles || window.RUNTIME_KNOWLEDGE_ARTICLES;
        window.RUNTIME_AUDIT_EVENTS = audit.items;
        window.RUNTIME_AUDIT_AI = audit.summary;
      } else if (route.startsWith('#/compliance-ops/dispute/') && roleCan(['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const dispute = await invokeRead('governance.dispute_view', { dispute_id: id });
        const evidence = await invokeRead('audit.replay_evidence_chain', { dispute_id: id });
        dispute.evidenceReplay = evidence;
        const index = window.RUNTIME_DISPUTES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_DISPUTES[index] = dispute; else window.RUNTIME_DISPUTES.unshift(dispute);
      } else if (route.startsWith('#/zones-pack/zone/') && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const zone = await invokeRead('zone.view', { zone_id: id });
        const index = window.RUNTIME_ZONES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_ZONES[index] = zone; else window.RUNTIME_ZONES.unshift(zone);
      } else if (route === '#/zones-pack' && roleCan(['ROLE_ORGAN_OPERATER', 'ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'])) {
        const result = await invokeRead('zone.list', {});
        window.RUNTIME_ZONES = result.items;
      } else if (route.startsWith('#/integration-admin/package/') && roleCan(['ROLE_BUSIAUDIT'])) {
        const id = decodeURIComponent(route.split('/').pop());
        const pkg = await invokeRead('package.view', { package_id: id });
        const index = window.RUNTIME_CAPABILITY_PACKAGES.findIndex(item => item.id === id);
        if (index >= 0) window.RUNTIME_CAPABILITY_PACKAGES[index] = pkg; else window.RUNTIME_CAPABILITY_PACKAGES.unshift(pkg);
      } else if (route === '#/integration-admin/iam-governance' && roleCan(['ROLE_BUSIAUDIT'])) {
        window.RUNTIME_IAM_GOVERNANCE = await invokeRead('governance.iam_overview', {});
      } else if (route === '#/integration-admin' && roleCan(['ROLE_BUSIAUDIT'])) {
        const result = await invokeRead('package.list', {});
        window.RUNTIME_CAPABILITY_PACKAGES = result.items;
        window.RUNTIME_IAM_GOVERNANCE = await invokeRead('governance.iam_overview', {});
      } else if (route === '#/migration-acceptance' && roleCan(['admin'])) {
        window.RUNTIME_MIGRATION_ACCEPTANCE = await invokeRead('legacy.migration.status.query', {});
      } else if (route === '#/compliance-ops' && roleCan(['ROLE_SECURITY_AUDIT'])) {
        // W4.2: 安全审计员 看 P6 时预拉直达交付清单作绕行督查的数据源
        try {
          window.RUNTIME_R8_DIRECT_ACCESS = await invokeRead('direct_access.delivery.list', { limit: 50 });
        } catch (_) { window.RUNTIME_R8_DIRECT_ACCESS = { items: [], total: 0 }; }
      } else if (route === '#/provider' && roleCan(['ROLE_BUSIAUDIT'])) {
        // 业务运营员 P5 视图：预拉收件箱条数用于工作流卡片标题
        try {
          const draftsResult = await invokeRead('catalog.entry.query', { source: 'reverse', lifecycle_status: 'draft' });
          window.RUNTIME_R7_FIELD_DRAFTS = (draftsResult && draftsResult.items) || [];
        } catch (_) { window.RUNTIME_R7_FIELD_DRAFTS = []; }
        try {
          const browseResult = await invokeRead('catalog.browse', { lifecycle: 'pending_review', limit: 50 });
          window.RUNTIME_R7_HOOKUP_PENDING = (browseResult && browseResult.items) || [];
        } catch (_) { window.RUNTIME_R7_HOOKUP_PENDING = []; }
        try {
          const reqResult = await invokeRead('request.list', {});
          window.RUNTIME_R7_DEMAND_PENDING = ((reqResult && reqResult.items) || []).filter(r => r.status === 'submitted' || r.status === 'pending');
        } catch (_) { window.RUNTIME_R7_DEMAND_PENDING = []; }
        // 业务运营员 Direct Access channel data
        try {
          const directResult = await invokeRead('direct_access.catalog.query', {});
          window.RUNTIME_R7_DIRECT_ACCESS = (directResult && directResult.directAccess) || window.RUNTIME_PROVIDER.directAccess || { catalogs: [], resources: [], demands: [], subscriptions: [] };
        } catch (_) { window.RUNTIME_R7_DIRECT_ACCESS = window.RUNTIME_PROVIDER.directAccess || { catalogs: [], resources: [], demands: [], subscriptions: [] }; }
      } else if (route === '#/provider/inbox/field-decision' && roleCan(['ROLE_BUSIAUDIT'])) {
        const result = await invokeRead('catalog.entry.query', { source: 'reverse', lifecycle_status: 'draft' });
        window.RUNTIME_R7_FIELD_DRAFTS = (result && result.items) || [];
      } else if (route.startsWith('#/provider/inbox/field-decision/') && roleCan(['ROLE_BUSIAUDIT'])) {
        const catalogCode = decodeURIComponent(route.split('/').pop());
        const result = await invokeRead('catalog.entry.reverse_draft.suggest', { schema_ref: catalogCode });
        // For 业务运营员 inbox, the schema_ref equals catalog_code (草稿命名约定)；若找不到，
        // 把 summary_json.draft_field_suggestions 投影成同样形态用作 业务运营员 表单源。
        if (result && result.found) {
          window.RUNTIME_R7_FIELD_DRAFT_DETAIL = result;
        } else {
          const entry = await invokeRead('catalog.entry.query', { catalog_code: catalogCode });
          const summary = (entry && entry.items && entry.items[0] && entry.items[0].summary_json) || {};
          const fields = Array.isArray(summary.draft_field_suggestions) ? summary.draft_field_suggestions : [];
          window.RUNTIME_R7_FIELD_DRAFT_DETAIL = {
            schema_ref: summary.schema_ref || catalogCode,
            fields,
            coverage: {
              green: fields.filter(f => f.confidence === 'green').length,
              yellow: fields.filter(f => f.confidence === 'yellow').length,
              orange: fields.filter(f => f.confidence === 'orange').length,
              total: fields.length,
            },
            found: true,
          };
        }
      } else if (route === '#/provider/inbox/hookup-review' && roleCan(['ROLE_BUSIAUDIT'])) {
        const result = await invokeRead('catalog.browse', { lifecycle: 'pending_review', limit: 50 });
        window.RUNTIME_R7_HOOKUP_PENDING = ((result && result.items) || []).map(item => ({
          resource_code: item.catalog_code,
          id: item.catalog_code,
          kind: '目录-资源挂接',
          status: item.lifecycle_status || 'pending_review',
        }));
      } else if (route === '#/provider/inbox/demand-match' && roleCan(['ROLE_BUSIAUDIT'])) {
        const result = await invokeRead('request.list', {});
        window.RUNTIME_R7_DEMAND_PENDING = ((result && result.items) || []).filter(r => r.status === 'submitted' || r.status === 'pending');
      } else if (route.startsWith('#/provider/inbox/demand-match/') && roleCan(['ROLE_BUSIAUDIT'])) {
        const applicationCode = decodeURIComponent(route.split('/').pop());
        try {
          const request = await invokeRead('request.view', { request_id: applicationCode });
          const matches = await invokeRead('require.resource.match', { application_code: applicationCode });
          window.RUNTIME_R7_DEMAND_DETAIL = {
            demand: request || { application_code: applicationCode },
            matches: (matches && matches.items) || [],
          };
        } catch (_) {
          window.RUNTIME_R7_DEMAND_DETAIL = { demand: { application_code: applicationCode }, matches: [] };
        }
      }
    } catch (err) {
      window.UI.toast(customerSafeError(err, '当前页面数据暂未准备好，请返回可办理入口重试。'), 'error');
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
      const result = await invokeWrite(skillId, Object.assign({ role: currentRole, confirmed: true }, payload));
      await refreshSnapshot();
      await syncRouteData(window.location.hash);
      if (after) after(result); else dispatch();
      if (successMessage) window.UI.toast(successMessage, 'success');
    } catch (err) {
      window.UI.toast(customerSafeError(err, '当前操作未完成，请确认身份范围或稍后重试。'), 'error');
    }
  }

  function dispatch() {
    if (!snapshotReady) return;
    const rawHash = window.location.hash || '#/workbench';
    // 路由前先剥掉 query/fragment 噪音（"#/integration-admin?_t=123" → "#/integration-admin"）
    const hash = rawHash.split('?')[0].split('&')[0];
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

    const access = window.ZW_PAGE_ACCESS && window.ZW_PAGE_ACCESS[matched.page];
    if (access && !roleCan(access)) {
      // 当前角色对该路由无权限：直接跳到首个可用落地页，不渲染 access-denied 死循环。
      const fallback = pickRoleLandingHash();
      if (fallback && fallback !== hash) {
        window.location.hash = fallback;  // hashchange 触发 dispatch 重跑
        return;
      }
      document.getElementById('app').innerHTML = renderError('当前身份暂无可办理入口，请联系管理员。');
      highlightNav(null);
      scheduleSyncProductShellNavTop();
      return;
    }

    const page = window.PAGES && window.PAGES[matched.page];
    if (typeof page !== 'function') {
      document.getElementById('app').innerHTML = renderError('当前办理入口暂未开放，请返回数据共享工作台选择其他事项。');
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
    const unsafe = String(hash || '');
    const escapedHash = unsafe
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
    return `
      <div class="bg-white rounded-2xl p-10 text-center border-default shadow-soft">
        <div class="text-display mb-3">页面未找到</div>
        <p class="text-zw-mute mb-4">没有匹配的业务入口：<code>${escapedHash}</code></p>
        <a href="#/workbench" class="inline-block gov-btn gov-btn-primary px-4 py-2 rounded-lg text-caption">回到数据共享工作台</a>
      </div>`;
  }

  function renderError(message) {
    return `
      <div class="state-card">
        <div class="page-kicker">页面暂未准备好</div>
        <div class="page-hero-title">当前服务没有完成加载。</div>
        <p class="page-hero-subtitle">${message}</p>
        <div class="mt-5 flex gap-3 flex-wrap">
          <a href="#/workbench" class="gov-btn gov-btn-primary">回到数据共享工作台</a>
          <button type="button" class="gov-btn gov-btn-secondary" onclick="window.location.reload()">刷新重试</button>
        </div>
      </div>`;
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
    copyToClipboard(text) {
      const s = String(text || '');
      if (!s) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(s);
        } else {
          const ta = document.createElement('textarea');
          ta.value = s; document.body.appendChild(ta); ta.select();
          document.execCommand('copy'); document.body.removeChild(ta);
        }
        this.toast('已复制完整证据 ID', 'success');
      } catch (_) {
        this.toast('复制未完成，请稍后重试', 'error');
      }
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
    searchFromHome(event) {
      event.preventDefault();
      const input = document.getElementById('home-service-q');
      currentDiscoveryQuery = input ? input.value.trim() : '';
      if (!currentDiscoveryQuery) {
        window.UI.toast('请输入要查找的业务或数据需求', 'error');
        return;
      }
      if (window.STATE) window.STATE.discoveryQuery = currentDiscoveryQuery;
      window.location.hash = '#/discovery';
    },
    async setDiscoveryQuery(event) {
      event.preventDefault();
      const input = document.getElementById('discovery-q');
      currentDiscoveryQuery = input ? input.value.trim() : '';
      if (!currentDiscoveryQuery) {
        window.UI.toast('请输入要查找的业务或数据需求', 'error');
        return;
      }
      try {
        const result = await invokeRead('data.search', { query: currentDiscoveryQuery, page: 1 });
        window.RUNTIME_DISCOVERY.resources = result.results;
        window.RUNTIME_DISCOVERY.aiCopilot = result.summary;
        window.STATE.discoveryQuery = currentDiscoveryQuery;
        dispatch();
        window.UI.toast('已按业务需求更新可复用资源建议', 'success');
      } catch (err) {
        window.UI.toast(customerSafeError(err, '检索暂未完成，请稍后重试。'), 'error');
      }
    },
    async setCatalogBrowseFilter(key, value) {
      const filters = window.CATALOG_BROWSE_FILTERS || (window.CATALOG_BROWSE_FILTERS = { page: 1, limit: 20, lifecycle: 'active', kind: 'real' });
      filters[key] = value;
      if (key !== 'page') filters.page = 1;
      try {
        window.RUNTIME_CATALOG_BROWSE = await invokeRead('catalog.browse', filters);
        dispatch();
      } catch (err) {
        window.UI.toast(customerSafeError(err, '目录刷新暂未完成，请稍后重试。'), 'error');
      }
    },
    createRequest(resourceId) {
      const existing = (window.RUNTIME_REQUESTS || []).find(item => item.resourceId === resourceId && ['pending', 'supplementing', 'summary-pending'].includes(item.status));
      if (existing) {
        window.location.hash = `#/request-flow/request/${existing.id}`;
        window.UI.toast('已续接当前未完成申请', 'info');
        return;
      }
      performWrite('application.resource.submit', { resource_id: resourceId, query: currentDiscoveryQuery || window.STATE?.discoveryQuery || '' }, '已发起共享申请并进入受控准入', async result => {
        await refreshSnapshot();
        const requestId = result?.result?.request_id || result?.request_id;
        if (requestId) {
          window.location.hash = `#/request-flow/request/${requestId}`;
        } else {
          window.location.hash = '#/request-flow';
        }
      });
    },
    submitRequest(requestId) {
      if (!requestId) {
        window.UI.toast('缺少申请编号', 'error');
        return;
      }
      performWrite('request.submit', { request_id: requestId }, '已重新提交并进入受控准入', () => {
        window.location.hash = `#/request-flow/request/${requestId}`;
      });
    },
    approveRequest(requestId) {
      // W4.1: 若 审批人 在 reviewDetail 填了分级授权策略表单，把它带入审批 payload
      const gradeEl = document.getElementById('approval-grade');
      const policy = gradeEl ? {
        grade: gradeEl.value,
        mask_level: (document.getElementById('approval-mask') || {}).value,
        freq_per_day: Number((document.getElementById('approval-freq') || {}).value || 0),
        limit_day: Number((document.getElementById('approval-limitday') || {}).value || 0),
        cascade: (document.getElementById('approval-cascade') || {}).checked === true,
      } : null;
      const payload = { request_id: requestId, decision: 'approve_with_supplement' };
      if (policy && (policy.grade || policy.mask_level || policy.freq_per_day || policy.limit_day)) {
        payload.grade_policy = policy;
      }
      performWrite('application.resource.review', payload, '已通过并下发基层补录任务');
    },
    returnForFix(requestId) {
      performWrite('application.resource.review', { request_id: requestId, decision: 'return_for_fix' }, '已退回补正');
    },
    rejectRequest(requestId) {
      performWrite('application.resource.review', { request_id: requestId, decision: 'reject' }, '已驳回该申请');
    },
    submitSupplement(requestId) {
      performWrite('supplement.submit', { request_id: requestId }, '差异补录已提交，进入汇总确认');
    },
    confirmSummary(requestId) {
      performWrite('summary.confirm', { request_id: requestId }, '已确认自动汇总，进入回流确认');
    },
    confirmBackflow(taskId) {
      performWrite('backflow.confirm', { task_id: taskId }, '回流确认已生效，模板治理链路已更新');
    },
    triggerDeliveryRecovery(taskId) {
      performWrite('delivery.trigger_recovery', { task_id: taskId }, '恢复流程已触发');
    },
    reissueCredential(requestId) {
      // U-3 处置：审批人 / 主管部门手工补签或重新签发
      performWrite('credential.issue', { request_id: requestId, reissue: true }, '凭据已重新签发；旧凭据立即失效', async () => {
        // 强刷凭据视图
        try {
          const credentialView = await invokeRead('credential.query', { request_id: requestId });
          window.RUNTIME_CREDENTIAL_VIEW = credentialView;
          dispatch();
        } catch (err) {
          window.UI.toast('凭据查询失败：' + err.message, 'error');
        }
      });
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
      if (action === 'publish') {
        performWrite('catalog.entry.publish', { catalog_code: catalogId }, '目录条目已发布');
        return;
      }
      performWrite('catalog.manage_entry', { catalog_id: catalogId, action }, '目录说明已修正');
    },
    manageResourceAsset(resourceId, action) {
      if (action === 'publish') {
        performWrite('resource.asset.publish', { resource_code: resourceId }, '资源资产已发布');
        return;
      }
      performWrite('resource.manage_asset', { resource_id: resourceId, action }, '资源资产已暂停共享');
    },
    publishZoneTopicProjection(zoneId) {
      if (currentRole !== 'ROLE_BUSIAUDIT') {
        window.UI.toast('当前身份暂无正式发布权限', 'error');
        return;
      }
      performWrite('zone.publish_topic_projection', { zone_id: zoneId }, '已发布到正式专区');
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
    async startIafLogin(event) {
      if (event) event.preventDefault();
      try {
        await window.ZW_AUTH.startLogin();
      } catch (err) {
        window.UI.toast(customerSafeError(err, '无法启动统一身份登录，请联系系统管理员检查服务状态。'), 'error');
      }
    },
    toggleUserMenu(event) {
      if (event) event.preventDefault();
      const panel = document.getElementById('user-menu-panel');
      const button = document.getElementById('user-menu-button');
      if (!panel || !button) return;
      const nextHidden = !panel.hidden;
      panel.hidden = nextHidden;
      button.setAttribute('aria-expanded', nextHidden ? 'false' : 'true');
    },
    async logout(event) {
      if (event) event.preventDefault();
      try {
        await window.ZW_AUTH.logout();
      } catch (err) {
        window.ZW_AUTH.clearSession();
        window.location.href = '/';
      }
    },
    showProfile(event) {
      if (event) event.preventDefault();
      window.location.hash = '#/profile';
    },
    noop(message) {
      window.UI.toast(message || '当前阶段暂无可办理动作', 'info');
    },

    // ----- W2 提供方部门 反向编目工作流 -------------------------------------------
    async loadReverseCatalogCandidates() {
      try {
        const result = await invokeRead('metadata.schema.discover', { limit: 50 });
        window.RUNTIME_PROVIDER_REVERSE_CANDIDATES = result.items || [];
        window.UI.toast(`已拉取 ${(result.items || []).length} 条候选 schema`, 'success');
        dispatch();
      } catch (err) {
        window.UI.toast(customerSafeError(err, '候选 schema 暂未拉取，请稍后重试。'), 'error');
      }
    },
    async pickReverseCatalogSource(schemaRef) {
      try {
        const result = await invokeRead('catalog.entry.reverse_draft.suggest', { schema_ref: schemaRef });
        if (!window.STATE) window.STATE = {};
        window.STATE.providerReverseCatalog = {
          suggestions: result,
          draftTitle: result.title_suggestion && result.title_suggestion.title,
        };
        window.UI.toast(`已预填 ${result.coverage.total} 个字段（${result.coverage.green} 绿 / ${result.coverage.yellow} 黄 / ${result.coverage.orange} 橙）`, 'success');
        dispatch();
      } catch (err) {
        window.UI.toast(customerSafeError(err, '预填建议暂未生成，请稍后重试。'), 'error');
      }
    },
    resetReverseCatalogWizard() {
      if (window.STATE) window.STATE.providerReverseCatalog = null;
      window.RUNTIME_PROVIDER_REVERSE_CANDIDATES = [];
      dispatch();
    },
    async submitReverseCatalogDraft() {
      const state = (window.STATE && window.STATE.providerReverseCatalog) || {};
      const suggestions = state.suggestions || {};
      const codeInput = document.getElementById('rc-catalog-code');
      const titleInput = document.getElementById('rc-title');
      if (!codeInput || !titleInput) {
        window.UI.toast('草稿表单状态丢失，请重新选 schema。', 'error');
        return;
      }
      const fieldRows = Array.from(document.querySelectorAll('.rc-field-cn')).map(el => {
        const i = Number(el.dataset.i);
        const sensEl = document.querySelector(`.rc-field-sens[data-i="${i}"]`);
        const baseField = (suggestions.fields || [])[i] || {};
        return {
          field_en: baseField.field_en,
          field_cn: el.value,
          confidence: baseField.confidence,
          source: baseField.source,
          data_type: baseField.data_type,
          sensitive_level: sensEl ? sensEl.value : baseField.sensitive_level,
        };
      });
      performWrite(
        'catalog.entry.reverse_draft.create',
        {
          catalog_code: codeInput.value,
          title: titleInput.value,
          schema_ref: suggestions.schema_ref,
          draft_field_suggestions: fieldRows,
        },
        '反向编目草稿已生成并提交 业务运营员 字段口径裁决',
        () => {
          window.location.hash = '#/provider';
        },
      );
    },

    // ----- W2 提供方部门 API 服务化工作流 -----------------------------------------
    async submitApiServicePublish() {
      const resourceId = (document.getElementById('api-resource-id') || {}).value || '';
      const apiPath = (document.getElementById('api-path') || {}).value || '';
      const ipList = (document.getElementById('api-iplist') || {}).value || '';
      const rateLimit = Number((document.getElementById('api-ratelimit') || {}).value || 60);
      const maskLevel = (document.getElementById('api-mask-level') || {}).value || 'partial';
      const appCode = (document.getElementById('api-app') || {}).value || '';
      if (!resourceId || !apiPath) {
        window.UI.toast('请填入资源 ID 与 API 路径', 'error');
        return;
      }
      try {
        await invokeWrite('resource.api.register', {
          role: currentRole, confirmed: true,
          resource_id: resourceId, api_path: apiPath, subscriber_app: appCode,
        });
        await invokeWrite('resource.api.policy.update', {
          role: currentRole, confirmed: true,
          resource_id: resourceId, api_path: apiPath,
          ip_allowlist: ipList, rate_limit_per_min: rateLimit, mask_level: maskLevel,
        });
        await invokeWrite('resource.api.submit_review', {
          role: currentRole, confirmed: true,
          resource_id: resourceId, api_path: apiPath,
        });
        window.UI.toast('API 草稿三步链已提交：注册 → 策略 → 提审', 'success');
        window.location.hash = '#/provider';
      } catch (err) {
        window.UI.toast(customerSafeError(err, 'API 三步链未完成，请检查参数或角色范围。'), 'error');
      }
    },

    // ----- W2 提供方部门 自动检测规则工作流 ---------------------------------------
    submitQualityRule() {
      const code = (document.getElementById('qr-code') || {}).value || '';
      const name = (document.getElementById('qr-name') || {}).value || '';
      const kind = (document.getElementById('qr-kind') || {}).value || '';
      const rawPayload = (document.getElementById('qr-payload') || {}).value || '';
      if (!code || !name || !kind) {
        window.UI.toast('请填规则编码、名称、类型', 'error');
        return;
      }
      let parsed = {};
      try { if (rawPayload) parsed = JSON.parse(rawPayload); } catch (_) {
        window.UI.toast('阈值 json 解析失败，请按 {"key":"value"} 形式输入。', 'error');
        return;
      }
      performWrite('quality.rule.upsert', {
        rule_code: code, rule_name: name, rule_kind: kind, rule_payload_json: parsed,
      }, `规则 ${code} 已保存`);
    },
    runQualityTask() {
      const code = (document.getElementById('qr-run-code') || {}).value || '';
      const target = (document.getElementById('qr-run-target') || {}).value || '';
      if (!code) {
        window.UI.toast('请先填写规则编码', 'error');
        return;
      }
      performWrite('quality.task.run', {
        rule_code: code, target_catalog_code: target || undefined,
      }, `任务已发起 (rule=${code})`);
    },
    replayQualityTask() {
      const code = (document.getElementById('qr-run-code') || {}).value || '';
      const prev = (document.getElementById('qr-replay-prev') || {}).value || '';
      if (!code || !prev) {
        window.UI.toast('需要规则编码 + 上一次失败任务 ref', 'error');
        return;
      }
      performWrite('quality.task.replay', {
        rule_code: code, previous_task_ref: prev, reason: '失败重跑',
      }, `重跑已发起 (prev=${prev})`);
    },

    // ----- W3 业务运营员 字段口径裁决 ---------------------------------------------
    confirmFieldDecision(catalogCode) {
      const fieldRows = Array.from(document.querySelectorAll('.fd-field-cn')).map(el => {
        const i = Number(el.dataset.i);
        const sensEl = document.querySelector(`.fd-field-sens[data-i="${i}"]`);
        const baseField = ((window.RUNTIME_R7_FIELD_DRAFT_DETAIL || {}).fields || [])[i] || {};
        return {
          field_en: baseField.field_en,
          field_cn: el.value,
          confidence: baseField.confidence,
          source: baseField.source,
          data_type: baseField.data_type,
          sensitive_level: sensEl ? sensEl.value : baseField.sensitive_level,
        };
      });
      const comment = (document.getElementById('fd-comment') || {}).value || '';
      performWrite('catalog.entry.reverse_draft.confirm', {
        catalog_code: catalogCode,
        field_decisions: fieldRows,
        comment: comment,
      }, `已通过 ${catalogCode} 字段口径裁决，进入 pending_review`, () => {
        window.location.hash = '#/provider/inbox/field-decision';
      });
    },
    rejectFieldDecision(catalogCode) {
      const comment = (document.getElementById('fd-comment') || {}).value || '';
      if (!comment) {
        window.UI.toast('请填写驳回理由（fd-comment）', 'error');
        return;
      }
      performWrite('catalog.entry.reverse_draft.reject', {
        catalog_code: catalogCode,
        reject_reason: comment,
      }, `已驳回 ${catalogCode}，退回 提供方部门 修字段证据`, () => {
        window.location.hash = '#/provider/inbox/field-decision';
      });
    },

    // ----- W3 业务运营员 挂接审核 -------------------------------------------------
    approveResourceReview(resourceCode) {
      if (!resourceCode) {
        window.UI.toast('缺少资源编码', 'error');
        return;
      }
      performWrite('resource.asset.review', {
        resource_code: resourceCode, decision: 'approve',
      }, `已通过 ${resourceCode} 挂接审核`);
    },
    rejectResourceReview(resourceCode) {
      if (!resourceCode) {
        window.UI.toast('缺少资源编码', 'error');
        return;
      }
      performWrite('resource.asset.review', {
        resource_code: resourceCode, decision: 'reject',
      }, `已驳回 ${resourceCode}，退回 提供方部门`);
    },

    // ----- W4.4 审核汇总人 汇总撤回 -----------------------------------------------
    withdrawSummary(requestId) {
      const reason = (document.getElementById('summary-withdraw-reason') || {}).value || '';
      if (!reason) {
        window.UI.toast('请填写撤回原因', 'error');
        return;
      }
      performWrite('summary.confirm', {
        request_id: requestId, action: 'withdraw', reason: reason,
      }, `已撤回 ${requestId} 汇总，写入审计`);
    },

    // ----- W4.4 审核汇总人 异议四子流程 -------------------------------------------
    evaluateObjection(objectionId) {
      const conclusion = (document.getElementById(`obj-eval-${objectionId}`) || {}).value || '';
      if (!conclusion) {
        window.UI.toast('请填评估结论', 'error');
        return;
      }
      performWrite('objection.case.evaluate', {
        objection_id: objectionId, evaluation_kind: 'ROLE_ORGAN_MANAGER', conclusion: conclusion,
      }, `异议 ${objectionId} 评估已记录`);
    },
    processObjection(objectionId) {
      const action = (document.getElementById(`obj-proc-action-${objectionId}`) || {}).value || '';
      performWrite('objection.case.assign', {
        objection_id: objectionId, target_status: action,
      }, `异议 ${objectionId} 处置 → ${action}`);
    },
    reviewObjectionAuthorization(objectionId) {
      const summary = (document.getElementById(`obj-authz-${objectionId}`) || {}).value || '';
      performWrite('objection.case.review', {
        objection_id: objectionId, decision: 'authorization-impact', note: summary,
      }, `异议 ${objectionId} 授权影响已登记`);
    },
    replyObjection(objectionId) {
      const verdict = (document.getElementById(`obj-use-${objectionId}`) || {}).value || 'accepted';
      performWrite('objection.case.reply', {
        objection_id: objectionId, use_outcome: verdict,
      }, `异议 ${objectionId} 用数反馈已记录`);
    },

    // ----- W4.5 申请人 需求登记前置 -------------------------------------------
    submitDemandRegistration() {
      const purpose = (document.getElementById('apply-demand-purpose') || {}).value || '';
      const fields = (document.getElementById('apply-demand-fields') || {}).value || '';
      const window_ = (document.getElementById('apply-demand-window') || {}).value || '';
      if (!purpose || !fields) {
        window.UI.toast('请填用途与字段口径', 'error');
        return;
      }
      performWrite('require.intent.submit', {
        intent_kind: 'demand-registration',
        purpose: purpose,
        field_scope: fields,
        time_window: window_,
      }, '需求登记已提交，业务运营员 将判定复用可行性');
    },

    // ----- W4.3 基层填报人 异常回传 --------------------------------------------
    openGrassrootsExceptionForm() {
      const reason = window.prompt('请说明异常原因（如：现场无法核实 / 任务范围不对 / 字段证据缺失）');
      if (!reason) return;
      performWrite('supplement.submit', {
        action: 'exception_callback', reason: reason,
      }, '已回传异常，审核汇总人 将判断退回 / 升级口径');
    },

    // ----- W3 业务运营员 供需对接 -------------------------------------------------
    dispatchDemand(applicationCode) {
      const sliceRaw = (document.getElementById('dm-slice') || {}).value || '';
      let dispatchPayload = {};
      try { if (sliceRaw) dispatchPayload = JSON.parse(sliceRaw); } catch (_) {
        window.UI.toast('切片 JSON 解析失败', 'error');
        return;
      }
      const regions = Array.isArray(dispatchPayload.slices) ? dispatchPayload.slices : [];
      performWrite('require.resource.dispatch', {
        application_code: applicationCode,
        dispatch_payload_json: dispatchPayload,
        target_region_codes: regions,
      }, `已派 审核汇总人 切片任务 (application=${applicationCode})`, () => {
        window.location.hash = '#/provider/inbox/demand-match';
      });
    },

    // ----- 申请人 交付后动作：续期 / 异议 / 评价 ---------------------------------
    renewAuthorization(taskId) {
      // Backend skill is `application.grant.renew`; the delivery
      // task id maps to the underlying authorization grant via task → request →
      // grant lineage, so we forward the task id and let the server resolve.
      performWrite('application.grant.renew', {
        delivery_task_id: taskId,
      }, '续期申请已提交，保留原审批边界并延长有效期');
    },
    fileObjection(taskId) {
      const objType = (document.getElementById('apply-objection-type') || {}).value || 'data';
      const desc = (document.getElementById('apply-objection-desc') || {}).value || '';
      if (!desc) {
        window.UI.toast('请描述异议内容', 'error');
        return;
      }
      const typeLabel = ({ data: '数据质量', resource: '资源范围', authorization: '授权边界', usage: '使用体验' })[objType] || objType;
      // `objection.case.submit` expects an existing objection_id; the customer
      // surface here always starts from scratch, so we call `objection.case.create`
      // with status="submitted" to atomically create + advance past draft. The
      // governance dashboard picks it up as a new dispute the same turn.
      performWrite('objection.case.create', {
        target_type: 'delivery_task',
        target_id: taskId,
        objection_kind: objType,
        title: `${typeLabel}异议 · ${taskId}`,
        basis_text: desc,
        status: 'submitted',
      }, '异议已提交，进入 审核汇总人 受理流程', () => {
        window.location.hash = '#/compliance-ops';
      });
    },
    rateService(taskId) {
      const score = (document.getElementById('apply-rating-score') || {}).value || '5';
      const comment = (document.getElementById('apply-rating-comment') || {}).value || '';
      performWrite('service.rating.submit', {
        task_id: taskId,
        score: Number(score),
        comment: comment,
      }, '服务评价已提交，感谢反馈');
    },

    // ----- 审批人 授权管理：暂停 / 收回 ------------------------------------------
    suspendAuthorization(requestId) {
      performWrite('application.grant.suspend', {
        request_id: requestId,
      }, '授权已暂停，申请人 暂时无法访问');
    },
    revokeAuthorization(requestId) {
      performWrite('application.grant.revoke', {
        request_id: requestId,
      }, '授权已收回，申请人 需重新申请');
    },

    // ----- 业务运营员 国家数据直达通道 ------------------------------------------------
    directAccessUpload(kind) {
      // Backend uses the `adapter.national.*` skills for cross-tier reporting;
      // map customer-friendly action names onto the contract route.
      const skill = kind === 'catalog' ? 'adapter.national.catalog.report' : 'adapter.national.resource.report';
      performWrite(skill, {
        adapter_slug: 'adapter-national',
        operation: 'report',
        direction: 'outbound',
        payload_kind: kind,
      }, `${kind === 'catalog' ? '目录' : '资源'}上报已提交`);
    },
    directAccessAcceptDemand() {
      performWrite('adapter.national.application.receive', {
        adapter_slug: 'adapter-national',
        operation: 'receive',
        direction: 'inbound',
      }, '国家需求已受理');
    },
    directAccessManageSubscription() {
      performWrite('delivery.subscription.manage', {
        action: 'review',
      }, '订阅管理操作已提交');
    },

    // ----- 安全审计员 运维工单与交接班 ------------------------------------------------
    createOpsTicket() {
      const ticketType = (document.getElementById('audit-ticket-type') || {}).value || 'alert';
      const title = (document.getElementById('audit-ticket-title') || {}).value || '';
      const assignee = (document.getElementById('audit-ticket-assignee') || {}).value || '';
      if (!title) {
        window.UI.toast('请填写工单标题', 'error');
        return;
      }
      performWrite('ops.ticket.create', {
        ticket_type: ticketType,
        title: title,
        assignee: assignee,
      }, `工单"${title}"已创建`);
    },
    closeOpsTicket(ticketId) {
      performWrite('ops.ticket.close', {
        ticket_id: ticketId,
      }, `工单 ${ticketId} 已关闭`);
    },
    submitShiftHandover() {
      const summary = (document.getElementById('audit-handover-summary') || {}).value || '';
      const pending = (document.getElementById('audit-handover-pending') || {}).value || '';
      const next = (document.getElementById('audit-handover-next') || {}).value || '';
      if (!summary) {
        window.UI.toast('请填写遗留事项摘要', 'error');
        return;
      }
      performWrite('ops.shift_handover.submit', {
        summary: summary,
        pending_tickets: pending.split(',').map(s => s.trim()).filter(Boolean),
        next_shift_assignee: next,
      }, '交接班记录已提交');
    },
  };

  let productShellNavTopResizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(productShellNavTopResizeTimer);
    productShellNavTopResizeTimer = setTimeout(scheduleSyncProductShellNavTop, 120);
  });

  function wireUserMenuDismiss() {
    document.addEventListener('click', event => {
      const menu = document.getElementById('user-menu');
      const panel = document.getElementById('user-menu-panel');
      const button = document.getElementById('user-menu-button');
      if (!menu || !panel || !button || menu.contains(event.target)) return;
      panel.hidden = true;
      button.setAttribute('aria-expanded', 'false');
    });
    window.addEventListener('zw-auth-change', syncHeaderIdentityAndLegal);
  }

  window.addEventListener('hashchange', () => {
    // Jobs 优化：tab 切换立即从 snapshot 缓存渲染，不等后端 skill 调用。
    // syncRouteData 在背景异步执行，完成后若数据有变化触发一次 re-dispatch。
    dispatch();
    // 异步刷新（不阻塞 tab 切换感受）
    syncRouteData(window.location.hash)
      .then(() => {
        // 数据可能更新过，重新渲染（开销小：只是 DOM 替换，无网络）
        dispatch();
      })
      .catch(routeErr => {
        window.UI.toast(customerSafeError(routeErr, '页面数据未就绪，已展示默认内容。'), 'info');
      });
  });

  window.addEventListener('DOMContentLoaded', async () => {
    const switcher = document.getElementById('role-switch');
    wireUserMenuDismiss();
    if (switcher) {
      switcher.addEventListener('change', async event => {
        currentRole = event.target.value;
        if (window.STATE) window.STATE.role = currentRole;
        await refreshSnapshot();
        await syncRouteData(window.location.hash || '#/workbench');
        dispatch();
      });
    }
    try {
      const authenticated = await window.ZW_AUTH.bootstrapAuth();
      if (!authenticated) return;
      await refreshSnapshot();
      await refreshSchemaInfo();
      if (switcher) switcher.value = currentRole;
      if (!window.location.hash) {
        window.location.hash = '#/workbench';
        dispatch();
      } else {
        // Route-specific data is best-effort: a single skill fetch failure
        // should not blank the whole page after a successful snapshot. The
        // target page is responsible for its own empty-state rendering.
        try {
          await syncRouteData(window.location.hash);
        } catch (routeErr) {
          window.UI.toast(customerSafeError(routeErr, '页面数据未就绪，已展示默认内容。'), 'info');
        }
        dispatch();
      }
    } catch (err) {
      document.getElementById('app').innerHTML = renderError(customerSafeError(err, '初始化暂未完成，请刷新或稍后再试。'));
    }
  });
})();
