/* prototype smoke test — node fake DOM
 * 验证：v4 高保真原型在 R1–R8 角色下都能渲染；关键状态迁移后，列表 / 详情 / 治理 / 大屏投影保持一致
 * 使用：node prototype/scripts/smoke.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const BASE = path.join(__dirname, '..', 'ui', 'js');
const FILES = ['mocks.js', 'pages.js', 'app.js'];
const SOURCE = Object.fromEntries(FILES.map(file => [file, fs.readFileSync(path.join(BASE, file), 'utf8')]));

const ROUTES = [
  ['workbench', []],
  ['discovery', []],
  ['resourceDetail', ['res-jbxx-ledger']],
  ['resourceDetail', ['res-market-activity']],
  ['requestFlow', []],
  ['requestDetail', ['REQ-2026-04-25-0011']],
  ['requestDetail', ['REQ-2026-04-24-0007']],
  ['reviewDetail', ['REQ-2026-04-25-0011']],
  ['reviewDetail', ['REQ-2026-04-24-0007']],
  ['deliveryExchange', []],
  ['deliveryTaskDetail', ['DLV-2026-04-25-0011']],
  ['deliveryTaskDetail', ['DLV-2026-04-24-0008']],
  ['deliveryTaskDetail', ['DLV-2026-04-23-0004']],
  ['provider', []],
  ['complianceOps', []],
  ['disputeDetail', ['DSP-2026-04-25-0003']],
  ['disputeDetail', ['DSP-2026-04-24-0006']],
  ['zonesPack', []],
  ['zoneDetail', ['business']],
  ['zoneDetail', ['governance']],
  ['integrationAdmin', []],
  ['packageDetail', ['PKG-2026-04-25-001']],
  ['packageDetail', ['PKG-2026-04-24-002']],
  ['dashboard', []],
  ['dashboardAlert', ['AL-2026-04-25-002']],
];

const ROLES = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'];
const AI_REQUIRED_PAGES = new Set([
  'discovery', 'requestFlow', 'requestDetail', 'reviewDetail',
  'deliveryExchange', 'deliveryTaskDetail',
  'complianceOps', 'disputeDetail',
  'integrationAdmin', 'packageDetail'
]);

const KEYWORD_EXPECTATIONS = {
  workbench: ['R1–R8 真实角色链路'],
  discovery: ['法人单位基础信息台账模板', 'data-ai-surface'],
  resourceDetail: ['可复用', '标准字段'],
  requestFlow: ['预填补录', 'data-ai-surface'],
  requestDetail: ['已预填字段', '待补录 / 差异字段'],
  reviewDetail: ['自动汇总结果', '异常项'],
  deliveryExchange: ['回流', 'data-ai-surface'],
  deliveryTaskDetail: ['回流共享说明', '回流候选对象'],
  provider: ['模板版本', '服务治理'],
  complianceOps: ['减负指标', 'data-ai-surface'],
  disputeDetail: ['争议处理时间线', '推进调查'],
  zonesPack: ['专题包列表', '前台看到的是高频场景入口'],
  zoneDetail: ['包含资产', '订阅 / 作为默认入口'],
  integrationAdmin: ['不让外部辅助接管主状态写权', 'data-ai-surface'],
  packageDetail: ['AI 草拟的审核意见', '审核动作'],
  dashboard: ['指挥辅助结论'],
  dashboardAlert: ['K12 异常钻取'],
};

let passed = 0;
let failed = 0;

function createElement(id = '') {
  return {
    id,
    value: '',
    textContent: '',
    innerHTML: '',
    className: '',
    dataset: {},
    style: {},
    children: [],
    _listeners: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(event, callback) {
      this._listeners[event] = callback;
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    removeChild() {},
    remove() {},
  };
}

function createRuntime() {
  const elements = new Map();
  const listeners = {};

  function getElement(id) {
    if (!elements.has(id)) elements.set(id, createElement(id));
    return elements.get(id);
  }

  const fakeDoc = {
    body: { appendChild() {}, removeChild() {} },
    createElement(tag) {
      return createElement(tag);
    },
    getElementById(id) {
      return getElement(id);
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener(event, callback) {
      listeners[event] = callback;
    },
  };

  const sandbox = {
    console,
    setTimeout(callback) {
      if (typeof callback === 'function') callback();
      return 1;
    },
    clearTimeout() {},
    setInterval() { return 1; },
    clearInterval() {},
    Date,
    JSON,
    Math,
    Object,
    Array,
    String,
    Number,
    Boolean,
    RegExp,
    encodeURIComponent,
    decodeURIComponent,
    parseInt,
    parseFloat,
  };

  sandbox.window = sandbox;
  sandbox.document = fakeDoc;
  sandbox.location = { hash: '#/p1-workbench' };
  sandbox.scrollTo = function () {};
  sandbox.echarts = { init() { return { setOption() {} }; } };
  sandbox.__listeners = listeners;
  sandbox.addEventListener = function (event, callback) {
    listeners[event] = callback;
  };

  const ctx = vm.createContext(sandbox);
  for (const file of FILES) {
    vm.runInContext(SOURCE[file], ctx, { filename: file });
  }

  const roleSwitch = getElement('role-switch');
  roleSwitch.value = 'r1';
  getElement('app');
  getElement('health-brain');
  getElement('health-dashboard');
  getElement('dash-chart');

  if (typeof listeners.DOMContentLoaded === 'function') listeners.DOMContentLoaded();

  return ctx;
}

function renderPage(ctx, page, args = []) {
  const fn = ctx.PAGES[page];
  if (typeof fn !== 'function') throw new Error(`missing page renderer: ${page}`);
  const html = fn.apply(null, args);
  if (typeof html !== 'string') throw new Error(`page ${page} did not return html`);
  return html;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertIncludes(text, needle, message) {
  assert(text.includes(needle), `${message} (missing: ${needle})`);
}

function assertNotIncludes(text, needle, message) {
  assert(!text.includes(needle), `${message} (unexpected: ${needle})`);
}

function requestById(ctx, id) {
  return ctx.MOCK_REQUESTS.find(item => item.id === id);
}

function deliveryById(ctx, id) {
  return ctx.MOCK_DELIVERY_TASKS.find(item => item.id === id);
}

function packageById(ctx, id) {
  return ctx.MOCK_CAPABILITY_PACKAGES.find(item => item.id === id);
}

function lastAuditType(ctx) {
  const last = ctx.MOCK_AUDIT_EVENTS[ctx.MOCK_AUDIT_EVENTS.length - 1];
  return last && last.type;
}

function test(name, fn) {
  try {
    fn();
    console.log(`[PASS] ${name}`);
    passed += 1;
  } catch (error) {
    console.error(`[FAIL] ${name}: ${error.message}`);
    failed += 1;
  }
}

for (const role of ROLES) {
  for (const [page, args] of ROUTES) {
    test(`render role=${role} page=${page}`, () => {
      const ctx = createRuntime();
      ctx.STATE.role = role;
      const html = renderPage(ctx, page, args);
      assert(html.length >= 120, 'output too short');
      const isDashboard = page === 'dashboard' || page === 'dashboardAlert';
      if (!isDashboard) assertIncludes(html, 'v4 Prototype 导航', 'missing prototype shell marker');
      if (AI_REQUIRED_PAGES.has(page)) assertIncludes(html, 'data-ai-surface', 'missing AI surface marker on key page');
      for (const needle of KEYWORD_EXPECTATIONS[page] || []) {
        assertIncludes(html, needle, `missing keyword on ${page}`);
      }
    });
  }
}

test('approve request propagates to request and delivery views', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r2';
  ctx.ACTIONS.approveRequest('REQ-2026-04-25-0011');

  const request = requestById(ctx, 'REQ-2026-04-25-0011');
  const delivery = deliveryById(ctx, 'DLV-2026-04-25-0011');
  assert(request.status === 'supplementing', 'request should enter supplementing');
  assert(delivery.status === 'supplementing', 'delivery should enter supplementing');
  assert(delivery.backflow.status === '待补录完成', 'backflow should wait for supplement completion');
  assert(lastAuditType(ctx) === 'request.approve', 'audit should record approval');

  const flowHtml = renderPage(ctx, 'requestFlow');
  assertIncludes(flowHtml, '补录中', 'request flow should show supplementing status');
  const deliveryHtml = renderPage(ctx, 'deliveryExchange');
  assertIncludes(deliveryHtml, '当前等待基层完成差异补录', 'delivery queue should explain supplementing state');

  ctx.STATE.role = 'r3';
  const detailHtml = renderPage(ctx, 'requestDetail', ['REQ-2026-04-25-0011']);
  assertIncludes(detailHtml, '提交差异补录', 'grassroots should be able to submit supplement');
});

test('submit supplement propagates to summary-pending views', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r2';
  ctx.ACTIONS.approveRequest('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r3';
  ctx.ACTIONS.submitSupplement('REQ-2026-04-25-0011');

  const request = requestById(ctx, 'REQ-2026-04-25-0011');
  const delivery = deliveryById(ctx, 'DLV-2026-04-25-0011');
  assert(request.status === 'summary-pending', 'request should enter summary pending');
  assert(request.diffFields.every(item => item.state === '已补录'), 'all diff fields should be marked filled');
  assert(delivery.status === 'reconciling', 'delivery should enter reconciling');
  assert(delivery.backflow.status === '待确认', 'backflow should become pending confirmation');
  assert(lastAuditType(ctx) === 'supplement.submit', 'audit should record supplement submit');

  ctx.STATE.role = 'r5';
  const flowHtml = renderPage(ctx, 'requestFlow');
  assertIncludes(flowHtml, '待汇总确认', 'request flow should show summary pending');
  const reviewHtml = renderPage(ctx, 'reviewDetail', ['REQ-2026-04-25-0011']);
  assertIncludes(reviewHtml, '确认自动汇总', 'review page should expose summary confirmation');
  const taskHtml = renderPage(ctx, 'deliveryTaskDetail', ['DLV-2026-04-25-0011']);
  assertIncludes(taskHtml, '查看回流门槛', 'backflow should still be gated before summary confirmation');
});

test('confirm summary enables backflow confirmation', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r2';
  ctx.ACTIONS.approveRequest('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r3';
  ctx.ACTIONS.submitSupplement('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r5';
  ctx.ACTIONS.confirmSummary('REQ-2026-04-25-0011');

  const request = requestById(ctx, 'REQ-2026-04-25-0011');
  const delivery = deliveryById(ctx, 'DLV-2026-04-25-0011');
  assert(request.status === 'completed', 'request should be completed after summary confirmation');
  assert(delivery.backflow.status === '待确认', 'backflow should await provider confirmation');
  assert(lastAuditType(ctx) === 'summary.confirm', 'audit should record summary confirm');

  const flowHtml = renderPage(ctx, 'requestFlow');
  assertIncludes(flowHtml, '已汇总', 'request flow should show completed status');
  ctx.STATE.role = 'r6';
  const taskHtml = renderPage(ctx, 'deliveryTaskDetail', ['DLV-2026-04-25-0011']);
  assertIncludes(taskHtml, '确认回流共享', 'delivery detail should expose backflow confirmation');
});

test('confirm backflow syncs provider zone and dashboard projections', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r2';
  ctx.ACTIONS.approveRequest('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r3';
  ctx.ACTIONS.submitSupplement('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r5';
  ctx.ACTIONS.confirmSummary('REQ-2026-04-25-0011');
  ctx.STATE.role = 'r6';
  ctx.ACTIONS.confirmBackflow('DLV-2026-04-25-0011');

  const delivery = deliveryById(ctx, 'DLV-2026-04-25-0011');
  assert(delivery.status === 'completed', 'delivery should be completed after backflow confirmation');
  assert(delivery.backflow.status === '已确认', 'backflow should be confirmed');
  assert(lastAuditType(ctx) === 'backflow.confirm', 'audit should record backflow confirmation');
  assert(ctx.MOCK_PROVIDER.overview[0].value === 'v1.3', 'provider version should sync to v1.3');
  assert(ctx.MOCK_ZONES[0].trust[1] === '模板版本：v1.3，默认入口已同步', 'zone trust info should sync');
  assert(ctx.MOCK_DASHBOARD.burdenMetrics[1].value === '1 / 单任务', 'dashboard burden metric should shrink');
  assert(ctx.MOCK_DASHBOARD.burdenMetrics[2].value === '96%', 'dashboard auto summary metric should improve');

  const providerHtml = renderPage(ctx, 'provider');
  assertIncludes(providerHtml, 'v1.3', 'provider page should show updated version');
  const zoneHtml = renderPage(ctx, 'zoneDetail', ['business']);
  assertIncludes(zoneHtml, '模板版本：v1.3，默认入口已同步', 'zone detail should show synced trust info');
  const deliveryHtml = renderPage(ctx, 'deliveryExchange');
  assertIncludes(deliveryHtml, '回流已确认，模板与专题入口应已同步', 'delivery queue should reflect confirmed backflow');
  const dashboardHtml = renderPage(ctx, 'dashboard');
  assertIncludes(dashboardHtml, '1 / 单任务', 'dashboard should show improved burden metric');
  assertIncludes(dashboardHtml, '96%', 'dashboard should show improved auto-summary metric');
});

test('return for fix keeps failure honest across request and delivery views', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r2';
  ctx.ACTIONS.returnForFix('REQ-2026-04-25-0011');

  const request = requestById(ctx, 'REQ-2026-04-25-0011');
  const delivery = deliveryById(ctx, 'DLV-2026-04-25-0011');
  assert(request.status === 'need-fix', 'request should enter need-fix');
  assert(delivery.status === 'warning', 'delivery should enter warning state');
  assert(delivery.backflow.status === '不适用', 'backflow should become not applicable');
  assert(lastAuditType(ctx) === 'request.return-for-fix', 'audit should record return for fix');

  ctx.STATE.role = 'r1';
  const detailHtml = renderPage(ctx, 'requestDetail', ['REQ-2026-04-25-0011']);
  assertIncludes(detailHtml, '补齐后重新提交', 'request detail should expose resubmit action');
  const flowHtml = renderPage(ctx, 'requestFlow');
  assertIncludes(flowHtml, '待补正', 'request flow should show need-fix status');
  const taskHtml = renderPage(ctx, 'deliveryTaskDetail', ['DLV-2026-04-25-0011']);
  assertIncludes(taskHtml, '不适用', 'delivery detail should not pretend backflow still applies');
});

test('reject package enforces terminal guardrail in list and detail views', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r7';
  ctx.ACTIONS.rejectPackage('PKG-2026-04-25-001');

  const item = packageById(ctx, 'PKG-2026-04-25-001');
  assert(item.status === 'rejected', 'package should become rejected');
  assert(lastAuditType(ctx) === 'package.reject', 'audit should record package rejection');

  const listHtml = renderPage(ctx, 'integrationAdmin');
  assertIncludes(listHtml, '已驳回', 'integration list should show rejected status');
  const detailHtml = renderPage(ctx, 'packageDetail', ['PKG-2026-04-25-001']);
  assertIncludes(detailHtml, '查看当前状态', 'terminal package should stop exposing approval CTA');
  assertNotIncludes(detailHtml, ">批准<", 'terminal package should not keep approve button');
});

test('approve package syncs status and AI review wording', () => {
  const ctx = createRuntime();
  ctx.STATE.role = 'r7';
  ctx.ACTIONS.approvePackage('PKG-2026-04-25-001');

  const item = packageById(ctx, 'PKG-2026-04-25-001');
  assert(item.status === 'approved', 'package should become approved');
  assert(item.aiReview.summary.includes('只读辅助暴露面内生效'), 'ai review summary should be updated');
  assert(lastAuditType(ctx) === 'package.approve', 'audit should record package approval');

  const listHtml = renderPage(ctx, 'integrationAdmin');
  assertIncludes(listHtml, '已上线', 'integration list should show approved status');
  const detailHtml = renderPage(ctx, 'packageDetail', ['PKG-2026-04-25-001']);
  assertIncludes(detailHtml, '已上线', 'detail should show approved status');
});

test('dashboard outage mode stays read-only snapshot', () => {
  const ctx = createRuntime();
  ctx.ACTIONS.toggleOutage();
  assert(ctx.STATE.brainOutage === true, 'brain outage flag should toggle on');

  const dashboardHtml = renderPage(ctx, 'dashboard');
  assertIncludes(dashboardHtml, '快照模式', 'dashboard should show snapshot mode');
  assertIncludes(dashboardHtml, '只读消费治理结果与主旅程事实', 'dashboard should stay read-only');
});

const total = passed + failed;
console.log(`\n[smoke] ${passed}/${total} checks passed`);
process.exit(failed > 0 ? 1 : 0);
