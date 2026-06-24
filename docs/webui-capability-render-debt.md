# WebUI 渲染债务台账（live+webui 能力「声称大堂供应、实际没渲染」）

> **触发**：2026-05-29 上帝视角穿透 PR #161（网关心跳）发现——capability manifest
> 的 `compatibility` 含 `webui` + `product_scope.status == "live"` 表示「该能力声称在
> WebUI 大堂供应」，但 `export_agent_contract.py --check` 只校验契约投影一致，**不校验
> 真有 `.vue`/`.ts` 渲染消费者**。普查全量 manifest：当前
> <!-- stat:zwbrain.webui-render-debt -->4<!-- /stat --> 个 live+webui 能力在
> `zw-brain-web/src` 下无任何字面量渲染落点——契约全绿，但没人在产品里看得见。

## 一、这是什么债

- **菜单印着「大堂供应」，厨房没给大堂做。** 能力的契约面（REST/CLI/MCP/A2A）可能都通，
  但人类在 WebUI 里看不到它。运营/审计 persona 的「felt experience」缺位。
- 网关运行状态（`ops.service.report.query`）原本是这 107 个之一；PR #161 收尾时给它接了
  B1.1「网关运行」只读面板（`B11ComplianceOps.vue`），从台账移出。
- **[2026-06-13] 分诊清账（chore/webui-capability-render-triage）**：把 81 个逐个分诊四桶
  （全文 `docs/webui-capability-render-triage.md`）——2 个 NL 可达（platform.docs.read/search，
  经 a-zw-platform-guide Agent 通用派发触达）留台账作长期豁免；79 个降 status/真死「诚实降级」
  （manifest `compatibility` 去 `webui`，能力本体与 seed 保留、仍 live 在 REST/CLI/MCP/A2A，
  只是不再声称 WebUI 大堂供应），退出 live+webui 集合。接大堂 0（IA 已 freeze ≤10 页，无用户
  刚需面板缺位；少数 borderline 真需求转债）。净存量债务 81 → 2。
- **[2026-06-14] PINNED 循环判据根治（fix/pr5-guard-meta）**：旧 PINNED 把「手写测试断言 manifest
  的 `compatibility` 含 webui」当可达锚——但 `discover_skills()` 读的就是 manifest，断言 manifest
  = 循环信号（等同 `pages.generated.ts` 由 manifest 生成），证明不了真实前端落点。新判据只认「手写测试
  钉死 `zw-brain-web/src` 下非生成前端文件（.vue/路由/composable）」。trace 坐实原经此循环锚「可达」的
  `governance.iam_overview` / `tenant.policy.evaluate` 在 `web/src` 下**无任何真实 surface**（B1.2 身份
  治理页实际消费的是 `governance.policy_candidate.list/review`），降为诚实债务进台账、待 owner 裁接面板
  or 诚实降级（去 webui）。台账 2 → 现存
  <!-- stat:zwbrain.webui-render-debt -->4<!-- /stat --> 个（2 NL 可达豁免 + 2 待裁循环债）。

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
- **PINNED 手写测试钉死真实前端 surface**：有手写测试既提到该 slug、又在同窗口断言一个
  `zw-brain-web/src` 下的**非生成**前端文件（.vue 组件 / 路由 / composable）——证明确有渲染消费者
  （slug 走专属路由/动态拼串、LIT 看不到字面量，但人工测试钉死了真实 surface）。自动认
  `governance.policy_candidate.list/review`（`test_iam_governance_web_surface` 钉死 `B12IamGovernance.vue`
  + `usePolicyCandidates.ts`）。**[2026-06-14 根治]「测试断言 manifest 自身 compatibility 含 webui」不算
  PINNED**——`discover_skills()` 读的就是 manifest，断言 manifest = 循环信号（等同 `pages.generated.ts`
  由 manifest 生成），证明不了任何真实前端落点。原经此循环锚误判「可达」的 `governance.iam_overview` /
  `tenant.policy.evaluate` 已降为台账债务（见 §一 2026-06-14 条）。

**仍需手工豁免的两类**：①**NL / 内置 Agent 工具可达**（如 `platform.docs.*` 经 a-zw-platform-guide
Agent，无 slug 字面量、无专属路由、无真实 surface 锚）——守卫**设计内**的合理长期豁免；②**待裁循环债**
（`governance.iam_overview` / `tenant.policy.evaluate`，无真实 surface，待 owner 裁接面板 or 诚实降级）。
回潮锁见 `tests/test_webui_capability_render_guard.py`（含「PINNED 不接受 manifest-读-manifest」一条）。

**还债三条路**（逐步把台账清零）：
1. 接真实面板/组件渲染它（LIT）——接好后**从台账删除该行**。
2. 给它专属路由让前端消费（ROUTE）/ 加契约测试钉死 webui（PINNED）——守卫自动识别，无需挂台账。
3. 确认仅经 NL/Agent 工具可达——在该行 `#` 后标注理由，作为守卫设计内的长期合理豁免。

## 四、禁止

- 禁止为消红灯把新能力**随手塞进台账而不写理由**。新增豁免须 PR 描述说明（同 D17/D33
  「软规则配套机械检查」原则——这条守卫本身就是把「契约≠产品」这个软问题硬化）。
