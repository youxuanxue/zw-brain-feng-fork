# WebUI 渲染债务分诊（81 → 0 净存量）

> **缘起**：`docs/webui-capability-render-debt.md` 台账登记 81 个 live+webui 能力
> 「契约声称大堂供应、产品里看不见」。本文是对这 81 个的**逐个分诊 + 清账**结论。
> 守卫：`scripts/check_webui_capability_rendered.py`（段 52）；台账：
> `scripts/webui_capability_rendered_exemptions.txt`。

## 一、分诊方法（可机械化部分 + 语义判断）

1. **可机械化**：`status==live ∧ compatibility 含 webui ∧ src 下无字面 slug` 由守卫现算（81）。
2. **语义判断**（逐个）：对每个 slug 读 manifest（title/description/journey/side_effects），
   再 grep `zw-brain-web/src` 判断「该能力对应的**用户面任务**是否已在产品 UI 出现
   （哪怕由兄弟 slug 承接），还是真缺位」，以及是否经 **NL 加速器 / AgentRuntime 通用派发** 触达。

## 二、四桶结论

| 桶 | 计数 | 机械动作 | 说明 |
| --- | --- | --- | --- |
| **NL / 生成式派发 / 单一读路径可达** | 5 | 台账该行补「可达 + 入口页」理由 | 经通用派发/注册表派发/统一快照读路径触达，非 slug 字面量，诚实长期豁免 |
| **降 status** | 59 | manifest `compatibility` 去 `webui` | 本期不该在 WebUI 大堂供应（编排/子步骤/基建/助手），能力+seed 保留 |
| **真死** | 17 | manifest `compatibility` 去 `webui` | 无字面消费者亦无派发路径；多为兄弟 slug 已承接或纯内部引用 |
| **接大堂** | 0 | — | IA 已 freeze ≤10 页（D1/D8）；这 81 个均非「用户刚需且必须现在成面板」。少数 borderline（撤回引发的交付替代/取消、订阅终止、目录撤回、服务评价）真未来需求 → 转债，不本期硬接 |

> **上帝视角二次复核纠偏（2026-06-13，67-agent 对抗式审计 + 人工 trace-to-consumer）**：
> 对 77 个降级逐个对抗式核验。workflow 初报「35 误降」，但其中 32 个仅引 `pages.generated.ts`
> （该文件从 manifest webui 标志**生成**，循环论证）或漏了退役上下文（P7/exposure-matrix 已退役）
> 或把"页面存在"当"该能力被调用"。追到真实消费者 + 核退役上下文后只剩 **1 个真误降：
> `system.snapshot`**——它是**全 WebUI 唯一读路径**（`useSnapshot.ts` 经 `/api/snapshot`，32 个
> 前端文件依赖），描述明示"供主 WebUI"，却被一并降级。已回退 webui + 转单一读路径豁免。
> **架构真相**：WebUI 几乎一切读取走这一个 `system.snapshot` 胖快照，per-entity `.view/.query`
> 能力不被 webui 直调（服务 REST/CLI/MCP/A2A）——故那 76 个降级方向正确，slug-grep「无 webui
> 消费者」对它们成立。`catalog.duplicate.check`/`delivery.status.explain` 描述提及 P4/P5 但
> 实为发布子步骤输出/未接组件，定性留人工（降级可辩护）。

> **CI 收口纠偏（2026-06-13）**：初判把 `governance.iam_overview` / `tenant.policy.evaluate`
> 归入降级桶，被 `tests/test_contract_projection.py` 的「5 面契约共享」断言在 CI 抓出为
> **slug-grep 假阴性**——前者经身份治理页(D52)注册表派发消费、后者是 D2 五消费面共享的全局
> 授权基础能力。二者**回退保留 webui + 转生成式派发豁免**，不降级。教训：故意写的契约测试 /
> 生成式 pageAccess 投影是比 slug-grep **更权威**的 webui 在场信号，冲突时信前者。

> **降 status 与 真死 机械动作相同**（去 `webui`），分桶仅供阅读；两者皆为「诚实降级」——
> 能力本体与 seed **保留**，仍 live 在 REST/CLI/MCP/A2A，只是不再声称 WebUI 大堂供应。
> 去 `webui` 后该 slug 自动退出 `pages.generated.ts`（`build_webui_page_registry` 按
> `is_surface_enabled(webui) ∧ is_live` 投影），契约 `--check` 会要求重新生成。

净存量债务 **81 → 0**：保留 webui 的可达项 + 77 个去 webui（守卫不再计入 live+webui）。

## 三、保留 webui 的可达项（守卫升级后：3 自动识别 + 2 NL 豁免）

> 守卫判据已从纯 slug-grep 升级为 **LIT ∪ ROUTE ∪ PINNED**（见 docs/webui-capability-render-debt.md §二，
> 根治 debt render-guard-slug-grep-false-negative）。下表前 3 个**由守卫自动识别、不再挂手工豁免**；
> 后 2 个 NL/Agent 工具可达仍是守卫**设计内**的合理豁免。

| slug | 可达信号 | 入口页 / 机制 |
| --- | --- | --- |
| `system.snapshot` | **ROUTE 专属路由（自动认）** | **全 WebUI 唯一读路径**：`useSnapshot.ts:39` 经 `/api/snapshot`（openapi `x-zwbrain-skill-id`）拉统一事实源，32 个前端文件依赖；描述明示"供主 WebUI" |
| `governance.iam_overview` | **PINNED 契约钉死（自动认）** | 身份治理页 `/integration-admin/iam-governance`（D52）经注册表派发消费；`test_governance_iam_overview_contract_is_shared_across_five_surfaces` 钉死 5 面 |
| `tenant.policy.evaluate` | **PINNED 契约钉死（自动认）** | D2 五消费面共享的全局授权评估基础能力（非独立面板，每页授权隐式依赖）；`test_tenant_policy_evaluate_contract_is_shared_across_five_surfaces` 钉死 5 面 |
| `platform.docs.read` | NL 豁免（手工台账） | `PlatformGuideChatPanel.vue` → `usePlatformGuideChat.ts` 经 `/api/agent-runtime/tasks` 调内置 `zw-platform-guide` Agent，本 cap 是该 Agent 的工具 |
| `platform.docs.search` | NL 豁免（手工台账） | 同上（平台向导问答检索工具） |

> ROUTE/PINNED 由 `check_webui_capability_rendered.py` 现取（openapi 路由映射 + tests/ 契约断言扫描），
> 回潮锁 `tests/test_webui_capability_render_guard.py`（5 测）。platform.docs.* 经 Agent 通用派发、
> 前端无字面 slug、无专属路由/契约锚，属守卫设计内真实假阴性的合理长期豁免。

## 四、转债（borderline 真需求，立项指针见 docs/preflight-debt.md）

去 webui 不代表否定需求；以下若业务确认刚需，另立项接面板（走 product-dev 原型→审批）：

- `delivery.replace_or_cancel` / `subscription.terminate` / `delivery.subscription.manage`
  — 订阅/交付生命周期的用户侧中断面（撤回引发的替代-取消、显式终止）。
- `catalog.entry.withdraw` — 目录条目撤回的用户侧治理动作面。
- `service.rating.submit` — 交付完成后的服务评价面。

立项前不预先占 IA 页位（D1/D8 ≤10 页）。

## 五、逐 slug 分诊表

NL 行理由同时落入台账 `scripts/webui_capability_rendered_exemptions.txt`；降/真死行的
manifest `compatibility` 已去 `webui`（故已退出守卫的 live+webui 集合）。

<!-- TRIAGE-TABLE-START -->
| slug | journey | 桶 | 理由 |
| --- | --- | --- | --- |
| `compliance.case.query` | b1 | 真死 | 合规事件查询未被 B11ComplianceOps 采纳（改用 audit.event.*） |
| `compliance.metric.query` | b1 | 真死 | 合规指标查询未被采纳（B11 用 audit.event.statistics） |
| `projection.status.query` | b1 | 真死 | 5 类投影状态查询无页面消费者，亦不在 NL 路由 |
| `system.toggle_outage` | b1 | 真死 | 主脑故障态切换属应急能力，无生产 UI 面板 |
| `tenant.policy.evaluate` | b1 | 真死 | 租户策略评估属后端决策引擎内部调用，非用户操作 |
| `actor.projection.sync` | b1 | 降 status | 用户角色投影同步属后端基建，非用户面板 |
| `backflow.confirm` | b1 | 降 status | 回流确认由流程引擎触发，非用户面板 |
| `capability.exposure.configure` | b1 | 降 status | 能力暴露面配置属后端策略，非用户面板 |
| `capability.package.register` | b1 | 降 status | 能力包注册属系统自动化，非人工 UI 操作 |
| `capability.version.submit` | b1 | 降 status | 能力版本提交属流程自动化环节，非用户面板 |
| `governance.dispute_list` | b1 | 降 status | 争议列表入口；B11 异议面以 audit/objection 家族承接，本 slug 无字面消费者 |
| `governance.dispute_view` | b1 | 降 status | 争议详情；B11DisputeDetail 以兄弟 slug 渲染，本 slug 无字面消费者 |
| `governance.iam_overview` | b1 | 降 status | IAM 总览内容被 D51 登录侧/D55 权限侧/tenant.policy.evaluate 拆散，无页面装载本 slug |
| `ops.catalog.statistics.query` | b1 | 降 status | 运营投影读，B1 面板未承接（D52 瘦身后无 owner 面板） |
| `ops.exchange.statistics.query` | b1 | 降 status | 运营投影读，B13ServiceOps 不含交换统计，无 owner 面板 |
| `org.projection.sync` | b1 | 降 status | 组织治理投影同步属后端基建，非用户面板 |
| `package.apply_tenant_policy` | b1 | 降 status | 租户策略生效属后端配置流，B12 仅读展示 |
| `package.configure_exposure` | b1 | 降 status | 能力包暴露面配置属后端策略，非用户面板 |
| `package.exposure.matrix.query` | b1 | 降 status | UI 查询面 D52.c 已退役（接入中心瘦身），保留协议面(MCP/CLI)；复活须先有 owner 面板 |
| `package.register_version` | b1 | 降 status | 能力包版本登记属系统自动化，非用户 UI 操作 |
| `service.rating.submit` | b1 | 降 status | 服务评价本期未接面板，属交付后可选环节（真需求转债） |
| `platform.docs.read` | infra | NL 可达 | PlatformGuideChatPanel.vue 经 AgentRuntime(zw-platform-guide Agent) 调用为工具；入口=平台向导问答面板 |
| `platform.docs.search` | infra | NL 可达 | 同上，平台向导问答检索工具；入口=平台向导问答面板 |
| `system.schema_info` | infra | 真死 | canonical schema 信息属运维参考工具，无页面消费者 |
| `adapter.external.mapping.query` | infra | 降 status | 外部对象映射调试工具，非用户驱动能力 |
| `adapter.health.probe` | infra | 降 status | 适配器健康回执属 B1 监控基建，非用户面板 |
| `legacy.bsp.mapping.import` | infra | 降 status | 旧权限映射一次性迁移导入（migration-only），非生产用户任务 |
| `legacy.migration.status.query` | infra | 降 status | M0 迁移验收状态聚合属运维/审计可见性，非用户数据旅程 |
| `legacy.sharezone.mapping.import` | infra | 降 status | 旧共享专区一次性迁移导入（migration-only），非 live 旅程能力 |
| `metadata.catalog_item.query` | infra | 降 status | 字段映射证据查询属内部审计/谱系，非用户检索流 |
| `metadata.gather.evidence.query` | infra | 降 status | 元数据采集证据只读快照属内部治理 trace，非用户驱动 |
| `metadata.gather.evidence.upsert` | infra | 降 status | 元数据采集回执记录属内部审计写，非生产用户流 |
| `metadata.schema.snapshot.upsert` | infra | 降 status | Schema 快照记录属内部基建写，非用户面板 |
| `registry.artifact.export` | infra | 降 status | 注册工件导出属运维工件审计，非用户业务数据任务 |
| `system.snapshot` | infra | 降 status | 系统快照由 /api/snapshot REST 基建路由供 WebUI 初始化，非大堂能力面板 |
| `application.resource.submit` | j1 | 真死 | 申请提交由 P3RequestFlow(request.create) 承接，本 slug 无消费者 |
| `catalog.group.query` | j1 | 真死 | 目录分组属发现页内部投影，非独立用户操作 |
| `catalog.share_zone.query` | j1 | 真死 | 专区投影查询属内部导航元数据，非独立用户操作（原 P7 专题包面随 D55①/P6 下线，组件已删） |
| `delivery.view` | j1 | 真死 | 交付详情由 P4Delivery(delivery.list) 行内承接，本 slug 无独立消费者 |
| `objection.metric.query` | j1 | 真死 | 无页面消费异议指标（B 端用 audit.* 家族） |
| `objection.process.query` | j1 | 真死 | 异议过程由 P3/P5ObjectionDetail(案件详情)承接，本 slug 无独立消费者 |
| `request.view` | j1 | 真死 | 申请详情由 P3RequestDetail(request.list) 承接，本 slug 无独立消费者 |
| `zone.list` | j1 | 真死 | 原 P7 专题包列表面随 D55①/P6 下线、零入口孤儿组件已删；本 slug 无字面消费者 |
| `zone.view` | j1 | 真死 | 原 P7 专题包详情面随 D55①/P6 下线、组件已删；本 slug 无字面消费者 |
| `application.grant.renew` | j1 | 降 status | 授权续期属交付生命周期编排，非独立用户面板 |
| `approval.review_decide` | j1 | 降 status | 审批裁决嵌在 P3ReviewDetail(approval.case.decide) 流程，非独立面板 |
| `delivery.access.grant` | j1 | 降 status | 交付访问授权属履约编排，非用户面板 |
| `delivery.exchange.plan` | j1 | 降 status | 数据交换技术编排，非用户面板 |
| `delivery.exchange.publish` | j1 | 降 status | 数据交换运维动作，非用户面板 |
| `delivery.exchange.start` | j1 | 降 status | 数据交换执行控制，非用户面板 |
| `delivery.exchange.stop` | j1 | 降 status | 数据交换停止控制，非用户面板 |
| `delivery.receipt.ingest` | j1 | 降 status | 交付回执摄取属技术履约，非用户面板 |
| `delivery.replace_or_cancel` | j1 | 降 status | 撤回引发的替代/取消由后端编排触发，非独立大堂面板（真需求转债） |
| `delivery.status.explain` | j1 | 降 status | 状态解释助手未接面板（消费侧未迁），P4 交付详情已内联交付信息 |
| `delivery.subscription.manage` | j1 | 降 status | 订阅生命周期由后端编排，本期无独立订阅管理面板（真需求转债） |
| `objection.case.assign` | j1 | 降 status | 异议分发属平台/供给侧路由，后端状态机非用户面板 |
| `objection.case.reject` | j1 | 降 status | 异议驳回裁决嵌在异议案件流程，非独立面板 |
| `recommendation.similar_catalog.suggest` | j1 | 降 status | 相似目录推荐 D55 明确「消费侧不迁」，本期未接面板 |
| `require.intent.refine` | j1 | 降 status | 需求意图结构化属供需流程子步骤，非独立大堂面板 |
| `require.intent.review` | j1 | 降 status | 需求意图校核属供需内部流程，非独立面板 |
| `require.intent.submit` | j1 | 降 status | 需求意图提交属供需流程子步骤，非独立大堂面板 |
| `require.resource.dispatch` | j1 | 降 status | 需求派发给基层属运营编排，后端流程非用户面板 |
| `require.resource.match` | j1 | 降 status | 需求资源匹配属内部撮合引擎，非用户面板 |
| `require.task.handoff` | j1 | 降 status | 任务交接审计属运营流程子步骤，非用户面板 |
| `subscription.terminate` | j1 | 降 status | 订阅显式终止由后端编排触发，本期无独立面板（真需求转债） |
| `summary.confirm` | j1 | 降 status | 自动汇总确认属供需内部 checkpoint，非用户面板 |
| `supplement.submit` | j1 | 降 status | 差异补录属基层供数流程子步骤，非独立大堂面板 |
| `catalog.model.field.query` | j2 | 真死 | 目录模型字段查询属向导校验内部引用，非用户操作 |
| `catalog.model.query` | j2 | 真死 | 目录模型查询属向导校验内部引用，非用户操作 |
| `metadata.schema.discover` | j2 | 真死 | 反向编目候选 lister；P5ReverseCatalogWizard 实际用 catalog.entry.reverse_draft.* 不调本 slug |
| `catalog.duplicate.check` | j2 | 降 status | 发布前重复率检测属向导内子步骤，调用方内联展示，非独立面板 |
| `catalog.entry.withdraw` | j2 | 降 status | 目录撤回属治理动作，由编目管理流程承接，本期未独立成面板（真需求转债） |
| `catalog.manage_entry` | j2 | 降 status | 目录治理包装能力，实际 UX 委托给发布/修订子步骤 |
| `catalog.model.upsert` | j2 | 降 status | 目录模型维护属后端元数据维护，非用户直驱面板 |
| `catalog.resource.bind` | j2 | 降 status | 字段绑定属 schema 映射向导子步骤，非独立面板 |
| `catalog.schema.mapping.upsert` | j2 | 降 status | 字段映射确认属内部证据链记录，非用户录入表单 |
| `provider.view` | j2 | 降 status | 供给侧治理总览属计算投影只读，非直接 cap 调用面板 |
| `resource.api.change` | j2 | 降 status | API 服务变更属管理流程子步骤（register/review/publish 链承接） |
| `resource.api.policy.update` | j2 | 降 status | API 通道策略调优属后端合规配置，非用户表单 |
| `resource.api.revoke` | j2 | 降 status | API 服务撤销属策略动作（withdraw 链承接），非独立面板 |
| `resource.manage_asset` | j2 | 降 status | 资源资产治理包装能力，动作散落 P5ResourceManageList 子步骤 |
<!-- TRIAGE-TABLE-END -->
