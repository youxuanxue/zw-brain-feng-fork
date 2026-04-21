/* prototype smoke test — node fake DOM
 * 验证：所有 22 个 PAGES.* 渲染函数在 5 个角色下都不抛错
 * 使用：node prototype/scripts/smoke.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const BASE = path.join(__dirname, '..', 'ui', 'js');
const FILES = ['mocks.js', 'pages.js'];  // app.js 含 DOM 事件监听，跳过

// --- 假 DOM ---
const _events = {};
const fakeDoc = {
  body: { appendChild() {}, removeChild() {}, _children: [] },
  createElement(tag) { return { tag, classList: { add(){}, remove(){}, toggle(){} }, style: {}, addEventListener(){}, appendChild(){}, querySelector(){return null;}, querySelectorAll(){return [];} }; },
  getElementById(id) { return _events[id] || { value: '', textContent: '', innerHTML: '', className: '', dataset: {}, classList: { add(){}, remove(){}, toggle(){} }, addEventListener(){}, appendChild(){} }; },
  querySelector(){return null;},
  querySelectorAll(){return [];},
  addEventListener(){},
};

// --- 假全局 ---
const sandbox = {
  console,
  setTimeout(fn, ms) { /* 不真的执行 */ },
  setInterval(fn, ms) { return 1; },
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
  alert(msg) { /* swallow */ },
  confirm() { return true; },
  prompt() { return 'mock'; },
};
sandbox.window = sandbox;  // 大多数代码用 window.X
sandbox.document = fakeDoc;
sandbox.location = { hash: '#/' };
sandbox.echarts = { init() { return { setOption() {} }; } };
sandbox.UI = {
  toast() {},
  sleep(ms) { return Promise.resolve(); },
  isLeader: () => false,
  isAdmin: () => false,
  isAgentDev: () => false,
};

// 模拟初始 STATE（与 app.js 同步）
sandbox.STATE = {
  role: 'op',
  nlQuery: '',
  parsedConditions: null,
  pendingRequest: null,
  appliedRequests: [],
  brainOutage: false,
};

const ctx = vm.createContext(sandbox);

for (const f of FILES) {
  const code = fs.readFileSync(path.join(BASE, f), 'utf-8');
  vm.runInContext(code, ctx, { filename: f });
}

// --- 路由清单（与 app.js 同步） ---
const ROUTES = [
  ['workbench',        []],
  ['search',           []],
  ['datasetDetail',    ['ds-mzj-immune']],
  ['datasetDetail',    ['ds-non-existent']], // 错误路径
  ['apply',            ['ds-mzj-immune']],
  ['requestStatus',    ['REQ-2026-04-08-0033']],
  ['requestReview',    ['REQ-2026-04-15-0042']],
  ['manage',           [undefined]],         // 默认 catalog
  ['manage',           ['catalog']],
  ['manage',           ['resource']],
  ['manage',           ['service']],
  ['exchange',         []],
  ['exchangeDetail',   ['EX-2026-Q2-014']],
  ['exchangeDetail',   ['EX-2026-Q2-018']],  // failed task
  ['dispute',          []],
  ['disputeDetail',    ['DSP-2026-04-15-007']],
  ['disputeDetail',    ['DSP-2026-04-12-004']],  // resolved
  ['disputeDetail',    ['DSP-2026-04-10-002']],  // escalated
  ['compliance',       []],
  ['skillMarket',      []],
  ['skillPropose',     []],
  ['ops',              []],
  ['zones',            []],
  ['zoneDetail',       ['health']],
  ['zoneDetail',       ['business']],         // empty zone
  ['dashboard',        []],
  ['dashboardAlert',   []],
  ['agentHome',        []],
  ['agentSkills',      []],
  ['agentSkillDetail', ['catalog.search']],
  ['agentSkillDetail', ['request.review']],
  ['agentInvoke',      ['catalog.search']],
];

const ROLES = ['op', 'admin', 'leader', 'platform', 'agent-dev'];

let failed = 0, passed = 0;
for (const role of ROLES) {
  sandbox.STATE.role = role;
  for (const [page, args] of ROUTES) {
    const fn = sandbox.PAGES[page];
    if (typeof fn !== 'function') {
      console.error(`[FAIL] role=${role} page=${page}: not a function`);
      failed++; continue;
    }
    try {
      const html = fn.apply(null, args);
      if (typeof html !== 'string' || html.length < 50) {
        console.error(`[FAIL] role=${role} page=${page}(${args.join(',')}): output too short (${html && html.length})`);
        failed++; continue;
      }
      // 简单语义检查：brain 页应包含「5 个一级条目」字样
      const isBrain = !['dashboard','dashboardAlert','agentHome','agentSkills','agentSkillDetail','agentInvoke'].includes(page);
      if (isBrain && !html.includes('5 个一级条目')) {
        console.error(`[FAIL] role=${role} page=${page}: brain page missing brainShell sidebar marker`);
        failed++; continue;
      }
      passed++;
    } catch (e) {
      console.error(`[FAIL] role=${role} page=${page}(${args.join(',')}): ${e.message}`);
      console.error(e.stack.split('\n').slice(0, 4).join('\n'));
      failed++;
    }
  }
}

const total = passed + failed;
console.log(`\n[smoke] ${passed}/${total} ok across ${ROLES.length} roles × ${ROUTES.length} pages`);
process.exit(failed > 0 ? 1 : 0);
