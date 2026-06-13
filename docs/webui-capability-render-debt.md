# WebUI 渲染债务台账（live+webui 能力「声称大堂供应、实际没渲染」）

> **触发**：2026-05-29 上帝视角穿透 PR #161（网关心跳）发现——capability manifest
> 的 `compatibility` 含 `webui` + `product_scope.status == "live"` 表示「该能力声称在
> WebUI 大堂供应」，但 `export_agent_contract.py --check` 只校验契约投影一致，**不校验
> 真有 `.vue`/`.ts` 渲染消费者**。普查全量 manifest：当前
> <!-- stat:zwbrain.webui-render-debt -->2<!-- /stat --> 个 live+webui 能力在
> `zw-brain-web/src` 下无任何字面量渲染落点——契约全绿，但没人在产品里看得见。

## 一、这是什么债

- **菜单印着「大堂供应」，厨房没给大堂做。** 能力的契约面（REST/CLI/MCP/A2A）可能都通，
  但人类在 WebUI 里看不到它。运营/审计 persona 的「felt experience」缺位。
- 网关运行状态（`ops.service.report.query`）原本是这 107 个之一；PR #161 收尾时给它接了
  B1.1「网关运行」只读面板（`B11ComplianceOps.vue`），从台账移出。
- **[2026-06-13] 分诊清账（chore/webui-capability-render-triage）**：把 81 个逐个分诊四桶
  （全文 `docs/webui-capability-render-triage.md`）——2 个 NL 可达（platform.docs.read/search，
  经 zw-platform-guide Agent 通用派发触达）留台账作长期豁免；79 个降 status/真死「诚实降级」
  （manifest `compatibility` 去 `webui`，能力本体与 seed 保留、仍 live 在 REST/CLI/MCP/A2A，
  只是不再声称 WebUI 大堂供应），退出 live+webui 集合。接大堂 0（IA 已 freeze ≤10 页，无用户
  刚需面板缺位；少数 borderline 真需求转债）。净存量债务 81 → 现存
  <!-- stat:zwbrain.webui-render-debt -->2<!-- /stat --> 个。

## 二、机械守卫（段 52，baseline 棘轮）

- 脚本：`scripts/check_webui_capability_rendered.py`
- 台账：`scripts/webui_capability_rendered_exemptions.txt`（每行一个 slug + 可选 `# 理由/待办`）
- 规则：
  - **只拦净新增**：新增 live+webui 能力若无渲染消费者且不在台账 → preflight 红灯。
  - **台账过期检测**：台账登记了已被页面消费的 slug（应删）或不存在的 slug → 红灯。
- 数量防漂移：本文两处 `zwbrain.webui-render-debt` stat 由 `sync-stats.sh --check` 校验。

## 三、判据：webui 可达 = LIT ∪ ROUTE ∪ PINNED（2026-06-13 升级，根治 slug-grep 系统性假阴性）

> 缘起：上帝视角复核 #273 发现纯 slug 字面量 grep 对「单一 system.snapshot 读路径 +
> 注册表派发」架构系统性假阴性（system.snapshot 即被误判未渲染）。判据从纯 LIT 升级为并集：

- **LIT slug 字面量**：slug 出现在 `zw-brain-web/src/**/*.{vue,ts}`（排除生成产物）。直接派发消费。
- **ROUTE 专属 REST 路由**：能力经专属路由（非通用 `/api/skills/<slug>`，如 `/api/snapshot`）被前端
  消费——从 openapi `x-zwbrain-skill-id` 现取 slug→路由映射，路由串在 src 即可达（自动认
  `system.snapshot` 经 `useSnapshot.ts`→`/api/snapshot`）。
- **PINNED 契约测试钉死 webui**：有手写契约测试断言该 slug 的 compatibility 含 webui——注册表派发 /
  D2 基础能力的**非循环人工锚**（slug-grep 看不到、`pages.generated.ts` 是 manifest 生成的循环
  信号**不算证据**）。自动认 `governance.iam_overview` / `tenant.policy.evaluate`。

**仍需手工豁免的唯一一类 = NL / 内置 Agent 工具可达**（如 `platform.docs.*` 经 zw-platform-guide
Agent，无 slug 字面量、无专属路由、无契约锚）——这是守卫**设计内**的合理长期豁免。回潮锁见
`tests/test_webui_capability_render_guard.py`。

**还债三条路**（逐步把台账清零）：
1. 接真实面板/组件渲染它（LIT）——接好后**从台账删除该行**。
2. 给它专属路由让前端消费（ROUTE）/ 加契约测试钉死 webui（PINNED）——守卫自动识别，无需挂台账。
3. 确认仅经 NL/Agent 工具可达——在该行 `#` 后标注理由，作为守卫设计内的长期合理豁免。

## 四、禁止

- 禁止为消红灯把新能力**随手塞进台账而不写理由**。新增豁免须 PR 描述说明（同 D17/D33
  「软规则配套机械检查」原则——这条守卫本身就是把「契约≠产品」这个软问题硬化）。
