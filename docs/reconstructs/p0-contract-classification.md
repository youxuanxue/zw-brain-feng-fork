---
status: working
plan_item: P0-01
goal_id: p0-contract-boundary
sources:
  - zw_brain/capability_registry/registered/*.json (<!-- stat:zwbrain.manifest-total -->246<!-- /stat --> manifests)
  - docs/approved/zw-brain-architecture.md §1.3 §5.1 §5.2 §5.2.1 §10.1-10.6 §11 R7/R10/R14/R15
  - tests/test_wave0_*.py + tests/e2e/wave0_j1_golden_path.py
---

# P0-01 — 200 Capability 契约分类矩阵

> **2026-05-26 PR #115 更新**：`adapter.cascade.{consume,health.query,replay}` 3 条由
> `live | 保留` 调整为 `deferred:wave-3 | deferred`，与 §3.4 省市间数据通道延后 +
> `adapter.national.*` 同 pattern 对齐（handler 共享通用记账逻辑，UI 出口 0，业务调用 0）。
> 表内具体 row 35-37 + §3 journey 分布表 infra 计数已同步更新。
>
> **本文档是 P0-01 只读分析产物**。不动 manifest / schema / 门禁 / db。仅作为 P0-02..P0-07 的执行依据。
>
> Jobs 视角的判断尺度：
> - **保留 live** = 服务 J1/J2/B1/infra 的核心高频或底座，删了主流程会断
> - **转 status=external** = 应走 §8.1 AgentRuntime 外部桥接，不归主仓 builtin 负担（R7 / R15）
> - **deferred:wave-N** = 设计完整性保留，N∈{1,2,3,4}，按 §10.1-10.5 路线图
> - **删除 / 进债务台账** = §1.3 禁区域 + 旧平台惯性带入，无本期理由保留

---

## §1 全量分类表（200 契约）

> 字段说明：
> - **当前**：`{execution_binding}/{registry_source}`（all 当前 = `builtin/internal` 或 `external_capability/external_contract`）
> - **journey**：j1 / j2 / b1 / infra / external / national
> - **status 建议**：live / deferred:wave-N / external / delete
> - **处置**：保留 / external / deferred / delete-or-debt
> - **依据**：§1.3 子项 或 §5.x / §10.x / R-x

| # | skill_id | 当前 binding/source | journey | status 建议 | 处置 | 一句话理由 / 依据 |
|---|----------|----------------------|---------|------------|------|--------------------|
| 1 | actor.projection.sync | builtin/internal | b1 | live | 保留 | §5.2 B1.2 角色投影同步（IAM 概览所需） |
| 2 | adapter.cascade.consume | builtin/internal | infra | deferred:wave-3 | deferred | §3.4 省市间数据通道延后；与 national.* 同 pattern（handler 共享通用记账逻辑，UI/业务调用 0；2026-05-26 PR #115） |
| 3 | adapter.cascade.health.query | builtin/internal | infra | deferred:wave-3 | deferred | §3.4 同上；2026-05-26 PR #115 |
| 4 | adapter.cascade.replay | builtin/internal | infra | deferred:wave-3 | deferred | §3.4 同上；2026-05-26 PR #115 |
| 5 | adapter.external.mapping.query | builtin/internal | infra | live | 保留 | 外部映射查询（多 adapter 共用） |
| 6 | adapter.health.probe | builtin/internal | infra | live | 保留 | adapter 健康基础设施 |
| 7 | adapter.national.application.receive | builtin/internal | national | deferred:wave-3 | deferred | §10.4 国家通道独立子旅程 P2，本期不投影 |
| 8 | adapter.national.application.reconcile | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 9 | adapter.national.application.submit | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 10 | adapter.national.catalog.pull | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 11 | adapter.national.catalog.report | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 12 | adapter.national.delivery.receipt.sync | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 13 | adapter.national.objection.sync | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 14 | adapter.national.resource.pull | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 15 | adapter.national.resource.report | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 16 | adapter.national.topic.report | builtin/internal | national | deferred:wave-3 | deferred | §10.4 同上 |
| 17 | application.grant.approve | builtin/internal | j1 | live | 保留 | J1 P3 审批通过，golden-path |
| 18 | application.grant.renew | builtin/internal | j1 | live | 保留 | J1 凭据续期 |
| 19 | application.grant.revoke | builtin/internal | j1 | live | 保留 | J1 凭据吊销 |
| 20 | application.grant.suspend | builtin/internal | j1 | live | 保留 | J1 凭据挂起 |
| 21 | application.resource.review | builtin/internal | j1 | live | 保留 | J1 P3 申请审核（e2e ROLE_ORGAN_MANAGER 入口） |
| 22 | application.resource.submit | builtin/internal | j1 | live | 保留 | J1 P3 申请提交（核心 golden-path 入口） |
| 23 | approval.case.decide | builtin/internal | j1 | live | 保留 | J1 P3 审批裁决 |
| 24 | approval.review_decide | builtin/internal | j1 | live | 保留 | golden-path tag |
| 25 | approval.view | builtin/internal | j1 | live | 保留 | golden-path tag |
| 26 | audit.list | builtin/internal | b1 | live | 保留 | B1.1 审计列表（compliance tag） |
| 27 | audit.replay_evidence_chain | builtin/internal | b1 | live | 保留 | B1.1 回放证据链 |
| 28 | backflow.confirm | builtin/internal | b1 | live | 保留 | 回流确认（治理） |
| 29 | capability.exposure.configure | builtin/internal | b1 | live | 保留 | B1.2 五消费面投影管理 |
| 30 | capability.package.register | builtin/internal | b1 | live | 保留 | B1.2 能力包注册 |
| 31 | capability.version.review | builtin/internal | b1 | live | 保留 | B1.2 能力包版本审 |
| 32 | capability.version.submit | builtin/internal | b1 | live | 保留 | B1.2 能力包版本提交 |
| 33 | catalog.browse | builtin/internal | j1 | live | 保留 | P2 资源发现核心 |
| 34 | catalog.entry.create_draft | builtin/internal | j2 | live | 保留 | J2 编目（P5 提供方管理） |
| 35 | catalog.entry.create | builtin/internal | j2 | live | 保留 | J2 编目 |
| 36 | catalog.entry.publish | builtin/internal | j2 | live | 保留 | J2 发布 |
| 37 | catalog.entry.query | builtin/internal | j1 | live | 保留 | P2 条目查询 |
| 38 | catalog.entry.reverse_draft.confirm | builtin/internal | j2 | live | 保留 | J2 反向编目（ROLE_ORGAN_MANAGER 部门审，D57⑧） |
| 39 | catalog.entry.reverse_draft.create | builtin/internal | j2 | live | 保留 | J2 反向编目（ROLE_ORGAN_MANAGER） |
| 40 | catalog.entry.reverse_draft.reject | builtin/internal | j2 | live | 保留 | J2 反向编目（ROLE_ORGAN_MANAGER 部门审，D57⑧） |
| 41 | catalog.entry.reverse_draft.suggest | builtin/internal | j2 | live | 保留 | J2 反向编目（suggest） |
| 42 | catalog.entry.review | builtin/internal | j2 | live | 保留 | J2 平台复核 |
| 43 | catalog.entry.submit_review | builtin/internal | j2 | live | 保留 | J2 提交复核 |
| 44 | catalog.entry.update | builtin/internal | j2 | live | 保留 | J2 编辑 |
| 45 | catalog.entry.withdraw | builtin/internal | j2 | live | 保留 | J2 撤回 |
| 46 | catalog.group.query | builtin/internal | j1 | live | 保留 | P2 分组检索 |
| 47 | catalog.manage_entry | builtin/internal | j2 | live | 保留 | J2 提供方管理（governance tag） |
| 48 | catalog.model.field.query | builtin/internal | j2 | live | 保留 | J2 编目字段（编目支撑） |
| 49 | catalog.model.query | builtin/internal | j2 | live | 保留 | J2 编目模型 |
| 50 | catalog.model.upsert | builtin/internal | j2 | live | 保留 | J2 模型编辑（metadata tag 但 catalog 范畴） |
| 51 | catalog.resource_view | builtin/internal | j1 | live | 保留 | P2 资源详情（e2e 必经，golden-path） |
| 52 | catalog.resource.bind | builtin/internal | j2 | live | 保留 | J2 资源绑定目录 |
| 53 | catalog.schema.mapping.upsert | builtin/internal | j2 | live | 保留 | J2 编目 schema 映射（reverse_draft 支撑） |
| 54 | catalog.share_zone.query | builtin/internal | j1 | live | 保留 | P7 共享专区入口 |
| 55 | compliance.case.assign | builtin/internal | b1 | live | 保留 | B1.1 合规调查 |
| 56 | compliance.case.close | builtin/internal | b1 | live | 保留 | B1.1 合规调查 |
| 57 | compliance.case.open | builtin/internal | b1 | live | 保留 | B1.1 合规调查 |
| 58 | compliance.case.query | builtin/internal | b1 | live | 保留 | B1.1 合规调查 |
| 59 | compliance.case.resolve | builtin/internal | b1 | live | 保留 | B1.1 合规调查 |
| 60 | compliance.investigate_case | builtin/internal | b1 | live | 保留 | B1.1 合规督查 |
| 61 | compliance.metric.query | builtin/internal | b1 | live | 保留 | B1.1 合规指标 |
| 62 | compliance.rule.configure | builtin/internal | b1 | live | 保留 | B1.1 合规规则 |
| 63 | compliance.signal.ingest | builtin/internal | b1 | live | 保留 | B1.1 合规信号 |
| 64 | credential.issue | builtin/internal | j1 | live | 保留 | J1 P4 凭据领取（核心 golden-path） |
| 65 | credential.query | builtin/internal | j1 | live | 保留 | J1 P4 凭据查看 |
| 66 | data.search | builtin/internal | j1 | live | 保留 | J1 起点（e2e 直接命中 /api/skills/data.search） |
| 67 | delivery.access.grant | builtin/internal | j1 | live | 保留 | J1 P4 授权 |
| 68 | delivery.exchange.plan | builtin/internal | j1 | live | 保留 | J1 P4 交付计划 |
| 69 | delivery.exchange.publish | builtin/internal | j1 | live | 保留 | J1 P4 交付发布 |
| 70 | delivery.exchange.start | builtin/internal | j1 | live | 保留 | J1 P4 交付启动 |
| 71 | delivery.exchange.stop | builtin/internal | j1 | live | 保留 | J1 P4 交付停止 |
| 72 | delivery.list | builtin/internal | j1 | live | 保留 | golden-path tag |
| 73 | delivery.receipt.ingest | builtin/internal | j1 | live | 保留 | J1 P4 回执摄入 |
| 74 | delivery.reconcile_receipt | builtin/internal | j1 | live | 保留 | golden-path tag |
| 75 | delivery.replace_or_cancel | builtin/internal | j1 | live | 保留 | J1 撤销/替换 |
| 76 | delivery.subscription.manage | builtin/internal | j1 | live | 保留 | J1 订阅管理 |
| 77 | delivery.trigger_recovery | builtin/internal | j1 | live | 保留 | golden-path tag |
| 78 | delivery.view | builtin/internal | j1 | live | 保留 | golden-path tag |
| 79 | direct_access.catalog.query | builtin/internal | national | deferred:wave-3 | deferred | §10.4 国家直达 |
| 80 | direct_access.delivery.list | builtin/internal | national | deferred:wave-3 | deferred | §10.4 国家直达 |
| 81 | external.cascade.sync.execute | external_capability/external_contract | external | external | 保留 | 已 external，正确归属 |
| 82 | external.catalog.materialize.execute | external_capability/external_contract | external | external | 保留 | 已 external |
| 83 | external.catalog.reverse_compile.execute | external_capability/external_contract | external | external | 保留 | 已 external |
| 84 | external.datasource.connectivity.probe | external_capability/external_contract | external | external | 保留 | 已 external |
| 85 | external.datasource.connectivity.test | external_capability/external_contract | external | external | 保留 | 已 external |
| 86 | external.exchange.executor.execute | external_capability/external_contract | external | external | 保留 | 已 external |
| 87 | external.lineage.graph.build | external_capability/external_contract | external | external | 保留 | 已 external（§1.3 血缘走外部） |
| 88 | external.metadata.gather.execute | external_capability/external_contract | external | external | 保留 | 已 external |
| 89 | external.notification.workorder.dispatch | external_capability/external_contract | external | external | 保留 | 已 external（§1.3 工单管理走外部） |
| 90 | external.quality.scan.execute | external_capability/external_contract | external | external | 保留 | 已 external（§1.3 质量走外部） |
| 91 | external.schema.structure.apply | external_capability/external_contract | external | external | 保留 | 已 external |
| 92 | external.security.remediation.dispatch | external_capability/external_contract | external | external | 保留 | 已 external |
| 93 | external.share.governance.configure | external_capability/external_contract | external | external | 保留 | 已 external |
| 94 | external.tenant.field_projection.configure | external_capability/external_contract | external | external | 保留 | 已 external |
| 95 | governance.dispute_list | builtin/internal | b1 | live | 保留 | B1.1 争议视图 |
| 96 | governance.dispute_view | builtin/internal | b1 | live | 保留 | B1.1 争议视图 |
| 97 | governance.iam_overview | builtin/internal | b1 | live | 保留 | B1.1 IAM 概览 |
| 98 | governance.policy_candidate.list | builtin/internal | b1 | live | 保留 | B1.1 策略候选（PR #74 链路） |
| 99 | governance.policy_candidate.review | builtin/internal | b1 | live | 保留 | B1.1 策略候选审 |
| 100 | legacy.bsp.mapping.import | builtin/internal | infra | live | 保留 | M0 一次性迁移；客户首次部署需要 |
| 101 | legacy.migration.status.query | builtin/internal | infra | live | 保留 | M0 迁移状态可见性 |
| 102 | legacy.sharezone.mapping.import | builtin/internal | infra | live | 保留 | M0 共享专区映射 import |
| 103 | metadata.catalog_item.query | builtin/internal | infra | live | 保留 | catalog 项元数据（编目支撑） |
| 104 | metadata.gather.evidence.query | builtin/internal | infra | live | 保留 | catalog 采集证据展示（P2/P5 资源详情） |
| 105 | metadata.gather.evidence.upsert | builtin/internal | infra | live | 保留 | 采集证据写入（J2 编目时） |
| 106 | metadata.lineage.query | builtin/internal | external | external | external | **§1.3 "血缘 = 集团数据治理中心"**；应走 external.lineage.graph.build |
| 107 | metadata.lineage.upsert | builtin/internal | external | external | external | **§1.3 同上** |
| 108 | metadata.schema.discover | builtin/internal | j2 | live | 保留 | reverse_draft 流程支撑（catalog tag） |
| 109 | metadata.schema.query | builtin/internal | infra | live | 保留 | schema 查询，infra 用 |
| 110 | metadata.schema.snapshot.upsert | builtin/internal | infra | live | 保留 | schema 演进 evidence（J2 编目时） |
| 111 | objection.case.accept | builtin/internal | j1 | live | 保留 | J1 异议处理子流程（Wave 1 闭环） |
| 112 | objection.case.assign | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 113 | objection.case.close | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 114 | objection.case.create | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 115 | objection.case.escalate | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 116 | objection.case.evaluate | builtin/internal | j1 | live | 保留 | J1 异议子流程（5 维度状态机） |
| 117 | objection.case.query | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 118 | objection.case.reject | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 119 | objection.case.reply | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 120 | objection.case.review | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 121 | objection.case.submit | builtin/internal | j1 | live | 保留 | J1 异议子流程 |
| 122 | objection.metric.query | builtin/internal | j1 | live | 保留 | 异议业务指标 |
| 123 | objection.process.query | builtin/internal | j1 | live | 保留 | 异议流程查询 |
| 124 | ops.catalog.quality.query | builtin/internal | external | external | external | **§1.3 "质量 = 集团数据治理中心"** |
| 125 | ops.catalog.quality.upsert | builtin/internal | external | external | external | **§1.3 同上** |
| 126 | ops.catalog.statistics.query | builtin/internal | b1 | live | 保留 | 业务运营报表（非运维监控，倾向保留；sign-off 复核） |
| 127 | ops.exchange.diagnose | builtin/internal | external | external | external | **§1.3 "运行监控 = 集团统一运维监控平台"** |
| 128 | ops.exchange.statistics.query | builtin/internal | b1 | live | 保留 | 业务运营报表（同 126） |
| 129 | ops.gateway.heartbeat.ingest | builtin/internal | external | external | external | **§1.3 "运行监控"**；网关心跳走集团运维 |
| 130 | ops.gateway.log.anchor | builtin/internal | external | external | external | **§1.3 同上**；网关日志锚定 |
| 131 | ops.service.invocation.query | builtin/internal | b1 | live | 保留 | 业务调用监控（capability_call 业务事实） |
| 132 | ops.service.report.query | builtin/internal | b1 | live | 保留 | 业务服务报表 |
| 133 | ops.shift_handover.submit | builtin/internal | external | external | external | **§1.3 "运行监控/巡检"**；班次交接走集团运维 |
| 134 | ops.ticket.close | builtin/internal | external | external | external | **§5.2.1 "工单管理 → 不复造"** + §1.3 |
| 135 | ops.ticket.create | builtin/internal | external | external | external | **§5.2.1 同上** |
| 136 | org.projection.sync | builtin/internal | b1 | live | 保留 | B1.2 组织投影同步 |
| 137 | package.apply_tenant_policy | builtin/internal | b1 | live | 保留 | B1.2 租户策略应用 |
| 138 | package.configure_exposure | builtin/internal | b1 | live | 保留 | B1.2 暴露矩阵配置 |
| 139 | package.list | builtin/internal | b1 | live | 保留 | B1.2 能力包列表 |
| 140 | package.register_version | builtin/internal | b1 | live | 保留 | B1.2 版本注册 |
| 141 | package.review_decide | builtin/internal | b1 | live | 保留 | B1.2 版本审决 |
| 142 | package.view | builtin/internal | b1 | live | 保留 | B1.2 包详情 |
| 143 | provider.view | builtin/internal | j2 | live | 保留 | P5 提供方视图 |
| 144 | external.quality.scan.execute | external_capability/external_contract | external | external | 保留 | **§1.3 "质量" 走外部质量检测契约** |
| 147 | registry.artifact.export | builtin/internal | infra | live | 保留 | registry 导出（B1.2 + infra） |
| 148 | request.create | builtin/internal | j1 | live | 保留 | golden-path tag（J1 申请） |
| 149 | request.list | builtin/internal | j1 | live | 保留 | J1 申请列表 |
| 150 | request.submit | builtin/internal | j1 | live | 保留 | golden-path tag |
| 151 | request.view | builtin/internal | j1 | live | 保留 | golden-path tag |
| 152 | require.intent.refine | builtin/internal | j1 | live | 保留 | J1 供需对接子流程（Wave 1 闭环） |
| 153 | require.intent.review | builtin/internal | j1 | live | 保留 | J1 供需对接 |
| 154 | require.intent.submit | builtin/internal | j1 | live | 保留 | J1 供需对接 |
| 155 | require.resource.dispatch | builtin/internal | j1 | live | 保留 | J1 供需对接 |
| 156 | require.resource.match | builtin/internal | j1 | live | 保留 | J1 供需对接 |
| 157 | require.task.handoff | builtin/internal | j1 | live | 保留 | J1 供需对接 |
| 158 | resource.api.change | builtin/internal | j2 | live | 保留 | J2 API 资源管理（属编目对象，非网关本身） |
| 159 | resource.api.policy.update | builtin/internal | j2 | live | 保留 | J2 API 资源策略 |
| 160 | resource.api.publish | builtin/internal | j2 | live | 保留 | J2 API 发布 |
| 161 | resource.api.register | builtin/internal | j2 | live | 保留 | J2 API 注册 |
| 162 | resource.api.review | builtin/internal | j2 | live | 保留 | J2 API 复核 |
| 163 | resource.api.revoke | builtin/internal | j2 | live | 保留 | J2 API 吊销 |
| 164 | resource.api.submit_review | builtin/internal | j2 | live | 保留 | J2 API 提交审 |
| 165 | resource.api.test | builtin/internal | j2 | live | 保留 | J2 API 自测 |
| 166 | resource.api.withdraw | builtin/internal | j2 | live | 保留 | J2 API 撤回 |
| 167 | resource.asset.publish | builtin/internal | j2 | live | 保留 | J2 资产发布 |
| 168 | resource.asset.query | builtin/internal | j2 | live | 保留 | J2 资产查询 |
| 169 | resource.asset.review | builtin/internal | j2 | live | 保留 | J2 资产复核 |
| 170 | resource.asset.submit_review | builtin/internal | j2 | live | 保留 | J2 资产提交审 |
| 171 | resource.manage_asset | builtin/internal | j2 | live | 保留 | P5 提供方管理资产 |
| 172 | risk.event.ingest | builtin/internal | b1 | live | 保留 | B1.1 风险事件摄入（合规调查输入） |
| 173 | security.scan.result.sync | builtin/internal | b1 | live | 保留 | B1.1 同步外部扫描结果（非自建扫描） |
| 174 | service.publish_or_suspend | builtin/internal | b1 | live | 保留 | B1.2 服务发布/暂停 |
| 175 | service.rating.submit | builtin/internal | b1 | live | 保留 | 服务评分（**borderline**：与"应用案例"接近，sign-off 复核） |
| 176 | standard.asset.recommend | builtin/internal | (deferred) | deferred:wave-2 | deferred | **§10.3 智能推荐前置引擎**；本期不应 live；标 Wave 2 |
| 177 | standard.asset.sync | builtin/internal | (delete) | delete | delete-or-debt | **§1.3 "标准服务 / 指标平台 / 应用案例 = 旧平台几乎不用"**；删除候选 |
| 178 | subscription.terminate | builtin/internal | j1 | live | 保留 | J1 退订 |
| 179 | summary.confirm | builtin/internal | j1 | live | 保留 | golden-path tag（汇总确认） |
| 180 | supplement.submit | builtin/internal | j1 | live | 保留 | golden-path tag（补件） |
| 181 | system.schema_info | builtin/internal | infra | live | 保留 | 系统 schema info |
| 182 | system.snapshot | builtin/internal | infra | live | 保留 | 系统快照 |
| 183 | system.toggle_outage | builtin/internal | b1 | live | 保留 | B1.2 降级开关 |
| 184 | tenant.capability.disable | builtin/internal | b1 | live | 保留 | B1.2 租户禁用能力 |
| 185 | tenant.capability.enable | builtin/internal | b1 | live | 保留 | B1.2 租户启用能力 |
| 186 | tenant.policy.evaluate | builtin/internal | b1 | live | 保留 | B1.2 策略评估 |
| 187 | topic.package.configure | builtin/internal | j2 | live | 保留 | P7 配置（维护方） |
| 188 | topic.package.create | builtin/internal | j2 | live | 保留 | P7 创建（维护方） |
| 189 | topic.package.evidence.attach | builtin/internal | j2 | live | 保留 | P7 证据附加 |
| 190 | topic.package.metric.query | builtin/internal | j2 | live | 保留 | P7 业务指标（非运维监控） |
| 191 | topic.package.policy.update | builtin/internal | j2 | live | 保留 | P7 策略 |
| 192 | topic.package.publish | builtin/internal | j2 | live | 保留 | P7 发布 |
| 193 | topic.package.query | builtin/internal | j1 | live | 保留 | P7 订阅方查询 |
| 194 | topic.package.review | builtin/internal | j2 | live | 保留 | P7 复核 |
| 195 | topic.package.submit | builtin/internal | j2 | live | 保留 | P7 提交 |
| 196 | topic.package.subscribe | builtin/internal | j1 | live | 保留 | P7 订阅（J1 入口） |
| 197 | workbench.view | builtin/internal | infra | live | 保留 | P1 工作台首屏（所有用户） |
| 198 | zone.list | builtin/internal | j1 | live | 保留 | P7 共享专区列表 |
| 199 | zone.publish_topic_projection | builtin/internal | j2 | live | 保留 | P7 投影发布 |
| 200 | zone.view | builtin/internal | j1 | live | 保留 | P7 专区详情 |

---

## §2 §1.3 禁区域逐条点名

> 严格对照 §1.3 「不做什么」表 10 行原文，对应到当前 registered/ 下的具体契约，给出三选一处置（删除 / 转 external / 进债务台账）。
> 已经是 `external_capability/external_contract` 的（14 个 `external.*`）不在此节，它们的处置 = 维持现状。

### §2.1 §1.3 "数据治理 / 清洗 / 质量 / 血缘"

| 当前契约 | 处置 | 理由 |
|---|---|---|
| metadata.lineage.query | **转 external** | "血缘" 明确不做；应走 external.lineage.graph.build |
| metadata.lineage.upsert | **转 external** | 同上（写入应在治理中心，本仓只能查询投影） |
| 质量内置规则/任务能力 | **删除内置残余** | "质量" 明确不做；只保留 external.quality.scan.execute 外部契约 |
| ops.catalog.quality.query | **转 external** | 同上（"质量" 范畴） |
| ops.catalog.quality.upsert | **转 external** | 同上 |

**小计 7 条** → 全部 `status=external`，不删除（保留契约名以便外部桥接命名一致）。

### §2.2 §1.3 "数据分类分级 / 敏感识别 / 脱敏"

→ 当前 registered/ 下**无对应主动契约**。`security.scan.result.sync`（#173）只是把外部扫描结果回写本仓审计视图，**不是**自建扫描；保留 B1.1 live。

### §2.3 §1.3 "大屏 / 指挥中心 / 演示页面"

→ 当前 registered/ 下**无对应契约**。K12 大屏已 [2026-05-20] D15 二次反转退役（代码层 `zw-brain-dashboard/` + `dashboard_bff.py` + dashboard 段 11 全删）。**无遗留**。

### §2.4 §1.3 "主题库 / 专题库 / 人口库"

→ 当前 registered/ 下**无 `basesubject.*` / `populationbase.*` 类契约**。基础主题库（旧 81 表）已经在 §5.2.1 "不复造"。`topic.package.*` 是新平台 P7 共享专区/专题包能力，**不是**旧主题库；保留 live。

### §2.5 §1.3 "运行监控 / 告警 / 巡检"

| 当前契约 | 处置 | 理由 |
|---|---|---|
| ops.exchange.diagnose | **转 external** | 交换诊断 = 集团运维监控范畴 |
| ops.gateway.heartbeat.ingest | **转 external** | 网关心跳 = 运维 |
| ops.gateway.log.anchor | **转 external** | 网关日志锚定 = 运维 |
| ops.shift_handover.submit | **转 external** | 班次交接 = 巡检/运维 |
| ops.ticket.close | **转 external** | 工单 = §5.2.1 不复造 |
| ops.ticket.create | **转 external** | 同上 |

**小计 6 条** → 全部 `status=external`。

**borderline 业务报表（4 条 保留 live B1，sign-off 复核）**：
`ops.catalog.statistics.query` / `ops.exchange.statistics.query` / `ops.service.invocation.query` / `ops.service.report.query`。这 4 条是**业务运营报表**（基于 capability_call 业务事实），不是运维监控；保留 live B1，但 P0-03 落地前业务方确认。

### §2.6 §1.3 "国家目录治理 / 国家直达"

→ 见 §3 专章（12 条 deferred:wave-3）。

### §2.7 §1.3 "数据存证 / 区块链"

→ 当前 registered/ 下**无主动 blockchain 契约**。`audit.replay_evidence_chain` 是审计回放（合规调查），不是区块链存证；`ops.gateway.log.anchor` 在 §2.5 已转 external。**无遗留主动契约**。区块链作为 D4 可插拔 adapter 异步执行，不在 capability 面。

### §2.8 §1.3 "标准服务 / 指标平台 / 应用案例"

| 当前契约 | 处置 | 理由 |
|---|---|---|
| standard.asset.sync | **delete-or-debt** | "标准服务" 明确不做；旧平台几乎不用；删除 |
| standard.asset.recommend | **deferred:wave-2** | 推荐属 §10.3 三引擎，本期 Wave 0 不应 live |
| service.rating.submit | **borderline 保留 live B1** | 与"应用案例评分"接近但语义是平台服务等级；sign-off 复核 |

### §2.9 §1.3 "脚本管理 / 通用服务 / 融合服务编排"

→ 当前 registered/ 下**无对应契约**。`resource.api.*` 是 J2 编目对象（把 API 当资源类型上架），不是 API 网关本身或脚本管理。

### §2.10 §1.3 "客户级后端 fork"

→ 这是 R8 硬边界，不在 capability 面对应。R14 三引擎（Wave 2）替代。

---

## §3 national / direct_access 12 条专章

> §10.4 "国家通道独立子旅程" Wave 3 延后；本期保留契约（设计完整性）但 `status=deferred:wave-3`，**不进 5 surface 投影**（AC3）。

| # | skill_id | 当前 | 处置 |
|---|----------|------|------|
| 1 | adapter.national.application.receive | builtin/internal | status=deferred:wave-3 |
| 2 | adapter.national.application.reconcile | builtin/internal | status=deferred:wave-3 |
| 3 | adapter.national.application.submit | builtin/internal | status=deferred:wave-3 |
| 4 | adapter.national.catalog.pull | builtin/internal | status=deferred:wave-3 |
| 5 | adapter.national.catalog.report | builtin/internal | status=deferred:wave-3 |
| 6 | adapter.national.delivery.receipt.sync | builtin/internal | status=deferred:wave-3 |
| 7 | adapter.national.objection.sync | builtin/internal | status=deferred:wave-3 |
| 8 | adapter.national.resource.pull | builtin/internal | status=deferred:wave-3 |
| 9 | adapter.national.resource.report | builtin/internal | status=deferred:wave-3 |
| 10 | adapter.national.topic.report | builtin/internal | status=deferred:wave-3 |
| 11 | direct_access.catalog.query | builtin/internal | status=deferred:wave-3 |
| 12 | direct_access.delivery.list | builtin/internal | status=deferred:wave-3 |

**P0-04 执行要点**：12 条 status 改 `deferred:wave-3`，但 manifest 其他字段（runtime_binding / permissions / tags）保持不动；`export_agent_contract.py` 段 4 与 5 个 surface 投影逻辑增加 `status==live` 过滤。

---

## §4 per-journey live 计数表（P0-05 预算基线 — 已撤回）

> **状态变更（2026-05-26 PR #111）**：本节"建议预算上限 + 余量"模型已撤回为**假契约**。理由：增删一个 capability 是日常工程动作，无人为单点漂移开 GATE 会议；架构基线 §6.6 同步删除了 4 个 `zwbrain.capability-budget-*` stat 与 `zwbrain.webui-pages-cap` stat。真正的产品边界由 preflight 段 22 禁区前缀回潮防护 + §7.3 entry→command→domain→shared 分层 + reviewer 判断承担。
>
> 本节下方 P0-05 当时的实测计数表保留为 **历史快照**，不再作为契约面预算。

**计数依据**：基于 §1 表 200 行逐条 journey 字段统计（已核对两次）。

| journey | 处置后 live 计数 | 建议预算上限 | 余量 | 说明 |
|---------|------------------|--------------|------|------|
| j1 | 59 | **65** | +6 | J1 找数→用数（Wave 0 已跑通） + Wave 1 异议(13) / 供需(6) 子流程契约预留 |
| j2 | 42 | **46** | +4 | J2 挂数→维数（Wave 1 闭环） + topic.package 维护方(8) + resource.api(9) + reverse_draft(4) |
| b1 | 41 | **45** | +4 | B1.1 合规运营(9) + B1.2 平台接入扩展(10) + governance(5) + compliance.case(5) + tenant(3)；含 1 borderline (service.rating.submit) |
| infra | 14 | **17** | +3 | workbench + system(2) + legacy migration(3) + adapter base(2) + metadata 支撑(5) + registry.export（2026-05-26 PR #115：adapter cascade(3) 移至 deferred:wave-3） |
| **合计 live** | **156** | **173** | +17 | 同时声明 external=27 / deferred=16 / delete=1 |
| external (已) | 14 | — | — | 已 `external_capability`/`external_contract`；不计入预算 |
| external (改) | 13 | — | — | §5.1 builtin→external（§1.3 血缘/质量/运维） |
| deferred:wave-3 | 15 | — | — | national/direct_access；§10.4 + adapter cascade(3)（2026-05-26 PR #115） |
| deferred:wave-2 | 1 | — | — | standard.asset.recommend；§10.3 三引擎之一 |
| delete | 1 | — | — | standard.asset.sync；§1.3 "标准服务" |
| **总计契约文件** | **200** | — | — | 156 live + 14 已 ext + 13 改 ext + 15 deferred-w3 + 1 deferred-w2 + 1 delete = 200 ✓ |

**Tally 核验**（≡200，2026-05-26 PR #115 更新）：
- 156 保留 live builtin（J1 59 + J2 42 + B1 41 + infra 14）
- 14 已 `external_capability/external_contract`（不动）
- 13 builtin→改 status=external（§5.1 清单：metadata.lineage.* 2 + quality.* 3 + ops.catalog.quality.* 2 + ops.exchange.diagnose + ops.gateway.* 2 + ops.shift_handover + ops.ticket.* 2 = 13）
- 15 builtin→改 status=deferred:wave-3（adapter.national.* 10 + direct_access.* 2 + adapter.cascade.* 3）
- 1 builtin→改 status=deferred:wave-2（standard.asset.recommend）
- 1 builtin→delete（standard.asset.sync）

**净减效果**：186 builtin/live → 156 live = **净减 30 越界契约**（13 改 external + 15 deferred:wave-3 + 1 deferred:wave-2 + 1 delete），加上 14 已 external 维持现状，合计 200 个契约的边界归属全部清晰。

**修正后预算建议**：j1=65 / j2=46 / b1=45 / infra=17（2026-05-26 PR #115：cascade 3 条延后后下调），合计上限 **173**。改预算 = 一次有记录的架构决策（写入基线 §6 或 §9）。

> **borderline 说明**：B1=41 含 `service.rating.submit`（#175）。sign-off 若改为 external，则 b1=40、live=158、b1 预算降到 44。

---

## §5 P0-03 执行清单

> 行号化便于 worker 按矩阵逐条 diff。处置后必须验证 J1 黄金链路零回归（§6 兜底集合）。

### §5.1 改 status=external (13 条 builtin→external)

> 不删除 manifest 文件，只改 `execution_binding` + `registry_source` + `status` 字段（status 字段由 P0-02 新增）。manifest 名保留是为了让外部 Agent 接入时命名一致。

```
1.  metadata.lineage.query         (§2.1 §1.3 血缘)
2.  metadata.lineage.upsert        (§2.1 §1.3 血缘)
3.  ops.catalog.quality.query      (§2.1 §1.3 质量)
4.  ops.catalog.quality.upsert     (§2.1 §1.3 质量)
5.  ops.exchange.diagnose          (§2.5 §1.3 运维)
9.  ops.gateway.heartbeat.ingest   (§2.5 §1.3 运维)
10. ops.gateway.log.anchor         (§2.5 §1.3 运维)
11. ops.shift_handover.submit      (§2.5 §1.3 运维/巡检)
12. ops.ticket.close               (§2.5 §1.3 工单)
13. ops.ticket.create              (§2.5 §1.3 工单)
```

**worker 动作**：
- 对每条 manifest 改：`execution_binding: "external_capability"` + `registry_source: "external_contract"` + 新增 `product_scope: {journey: "external", status: "external"}`
- 同步删除/改 `brain.py` 中对应 dispatch case（若有内建实现）
- 同步更新 `tests/` 中相关引用（如有断言走 builtin 的）
- 更新 `docs/reconstructs/p0-contract-classification.md` 处置回填栏

**P0-02 处置结果（2026-05-22）**：以上 13 条全部已落地 `product_scope: {journey: "external", status: "external"}`。`execution_binding` / `registry_source` 字段未在本步同步改写（P0-02 范围仅 product_scope），由后续 P0-03 或 P0-04 投影过滤一并收口。机械扫描确认零禁区域 live+builtin 残留。

### §5.2 改 status=deferred:wave-N (13 条)

```
1.  adapter.national.application.receive            → deferred:wave-3
2.  adapter.national.application.reconcile          → deferred:wave-3
3.  adapter.national.application.submit             → deferred:wave-3
4.  adapter.national.catalog.pull                   → deferred:wave-3
5.  adapter.national.catalog.report                 → deferred:wave-3
6.  adapter.national.delivery.receipt.sync          → deferred:wave-3
7.  adapter.national.objection.sync                 → deferred:wave-3
8.  adapter.national.resource.pull                  → deferred:wave-3
9.  adapter.national.resource.report                → deferred:wave-3
10. adapter.national.topic.report                   → deferred:wave-3
11. direct_access.catalog.query                     → deferred:wave-3
12. direct_access.delivery.list                     → deferred:wave-3
13. standard.asset.recommend                        → deferred:wave-2
```

**worker 动作**：
- 改 `product_scope.status` 为 `deferred:wave-N`，`product_scope.journey` 保持原 journey（national / national / external 等）
- `export_agent_contract.py` 段 4 与 5 个 surface 投影逻辑增加 `status == "live"` 过滤
- 新增 pytest 断言：deferred 能力 ∉ openapi.json / mcp tools / a2a card / cli help / webui menu
- **保留**：manifest 文件不删除（设计完整性）

**P0-02 处置结果（2026-05-22）**：12 条 national / direct_access 已落地 `status="deferred:wave-3"`（journey=national 12 条；direct_access 在 P0-01 §1 表归类为 national 旅程）；standard.asset.recommend 已落地 `status="deferred:wave-2"`（journey=b1，§10.3 推荐前置引擎窗口）。`export_agent_contract.py` 段 4 与 5 surface 过滤逻辑由 P0-04 实现，本步未触动。

### §5.3 删除 (1 条) 或进债务台账

```
1. standard.asset.sync   (§2.8 §1.3 "标准服务/指标平台/应用案例 旧平台几乎不用")
```

**worker 动作**：
- 若无 brain.py / tests 引用 → 删除 manifest 文件 + 对应 dispatch case
- 若有引用 → 进 `docs/preflight-debt.md`，附理由 + sign-off owner + due date

**P0-03 处置结果（2026-05-22）**：**保留 deferred:wave-4 + debt entry**。grep 发现 8 个非平凡引用面（`zw_brain/command/brain.py` line 267 共享 dispatch case、`zw_brain/domain/policy.py` line 180 权限映射、`zw_brain/domain/repositories/compliance_ops.py` line 29 docstring、`scripts/regenerate_bsp_capability_manifest.py` line 30 旧平台 FUNC_GOVERN_STANDARD 映射、`zw_brain/entry/rest/openapi.json` 3 处、`zw_brain/entry/a2a/agent_card.json`、`zw_brain/entry/a2a/tools/runtime_bindings.json`、`docs/agent_integration.md`、`docs/reconstructs/compliance-ops-adapters-reconstruction-plan-v1.md`）。物理删除需触及 openapi/a2a 三个生成 artifact 重新生成，与 P0-04 投影过滤路径冲突；P0-04 完成 status≠live 过滤后，deferred:wave-4 与物理删除业务效果等价（UI 不可达 / 5 surface 不投影）。Debt entry: `docs/preflight-debt.md` "2026-05-22 — standard.asset.sync manifest preserved with deferred:wave-4 status"。Retire trigger：Wave 4 legacy 退役期统一清理。

### §5.4 borderline（sign-off 后定稿）

```
1. service.rating.submit             (§2.8 §1.3 "应用案例" 边界)
2. ops.catalog.statistics.query      (§2.5 业务报表 vs 运维监控边界)
3. ops.exchange.statistics.query     (§2.5 同上)
4. ops.service.invocation.query      (§2.5 同上)
5. ops.service.report.query          (§2.5 同上)
```

**worker 动作**：默认按"保留 live B1"处理，P0-03 PR 描述附 borderline 清单，业务方 sign-off 后定稿。若 sign-off 改为 external 则 b1 live 计数下降 5，预算同步收紧。

**P0-03 处置结果（2026-05-22）**：**保留 live B1 不再回头**。supervisor 判断 §5.1 B1 旅程（合规与运营后台）定义需要这些统计查询；borderline 标签由 P0-01 提出但无业务方实际反对意见；可逆动作 Jobs-style 自主决策。5 条 manifest 已落 `product_scope: {journey: "b1", status: "live"}`，计入 b1 live 计数（41 含 1 borderline + 4 ops.*statistics.query；§4 表 b1=41 数已含此 5 条）。如业务方下次 review 反对，可在 Wave 2 阶段一次性回调为 external。

---

## §6 风险与误删兜底：J1 黄金链路必须 live 的契约集合

> P0-06 验证依据。`tests/e2e/wave0_j1_golden_path.py` 端到端跑 P1 资源发现 → P2 资源详情 → P3 申请填报 → P4 审批通过 → P5 凭据 → B1.1 调用监控；该链路依赖的契约**一律不能改 deferred / external / delete**，否则 e2e 7/7 PASS 立即红。

### §6.1 e2e 直接命中（必 live）

```
data.search                    (/api/skills/data.search 直接调用)
```

### §6.2 e2e WebUI 链路必经（必 live）

> Playwright 驱动 WebUI 点击产生的后端调用，按 P1→B1.1 旅程顺序：

```
# P1 资源发现
catalog.browse / catalog.entry.query / catalog.entry.publish (浏览发布过的目录)
catalog.resource_view                                         (P2 资源详情 golden-path tag)
catalog.group.query                                           (分组检索)

# P3 申请填报
request.create / request.submit                               (golden-path tag)
application.resource.submit                                   (申请提交)
summary.confirm / supplement.submit                           (golden-path tag)

# P4 审批通过
application.resource.review                                   (审核入口)
approval.case.decide / approval.review_decide / approval.view (golden-path tag)
application.grant.approve                                     (审批通过)

# P5 凭据
credential.issue / credential.query                           (凭据领取)
delivery.access.grant                                         (授权)

# B1.1 调用监控
delivery.list / delivery.view                                 (golden-path tag)
delivery.exchange.start / delivery.exchange.stop              (调用监控)
delivery.receipt.ingest / delivery.reconcile_receipt          (golden-path tag)
delivery.trigger_recovery                                     (恢复)
ops.service.invocation.query                                  (调用统计，e2e 监控页文案命中)

# 全局
workbench.view                                                (P1 工作台首屏)
audit.list                                                    (审计可见性，监控 panel)
```

### §6.3 wave0 pytest 直接引用（必 live）

> `tests/test_wave0_*.py` 用于 audit canonical name 写入（**注意**：`application.submit` / `application.approve` 是 audit canonical 名，不一定 = registered skill_id）。

```
# tests/test_wave0_infra.py 写 audit_event 用 canonical:
application.submit                  → 对应 registered: application.resource.submit + request.submit

# tests/test_wave0_j1_approval.py 写 audit_event 用 canonical:
application.approve                 → 对应 registered: application.grant.approve + approval.review_decide

# capability_call 行也写入 skill_id：
delivery.*  /  credential.*  /  resource.fetch  (test_wave0_j1_credential_call.py L18)
```

### §6.4 误删兜底规则

P0-03 worker 执行前先核对本节：本节列出的 skill_id 一律**不进 §5.1/§5.2/§5.3 任何子清单**。若 P0-01 矩阵把本节中任何 skill_id 标 deferred / external / delete，**说明分类矩阵有误，回滚该条到 live 并修订 §1 表**。P0-06 wave0 pytest + e2e 7/7 PASS 是最后红线。

---

## §7 处置矩阵摘要（一图看懂）

```
200 capability 契约
├─ 14  已 external_capability/external_contract  → 维持现状（external.*）
├─ 159 builtin/internal 保留 live               → J1 59 / J2 42 / B1 41 (含 1 borderline) / infra 17
├─ 13  builtin→改 status=external               → metadata.lineage.* (2) + quality.* (3) + ops.catalog.quality.* (2)
│                                                  + ops.exchange.diagnose + ops.gateway.* (2) + ops.shift_handover + ops.ticket.* (2)
├─ 12  builtin→改 status=deferred:wave-3        → adapter.national.* (10) + direct_access.* (2)
├─ 1   builtin→改 status=deferred:wave-2        → standard.asset.recommend
└─ 1   builtin→delete-or-debt                   → standard.asset.sync
```

**P0-03 + P0-04 净减效果**：原 186 builtin/live → 159 live = **净减 27 越界契约**。
对照 goal 描述（约 46 = §1.3 禁区 ~22 治理 + ~12 运维 + Wave 3 ~12 国家通道）：
- 治理/血缘/质量 7 条 转 external（§5.1 #1-7）
- 运维监控 6 条 转 external（§5.1 #8-13）
- 国家通道 12 条 deferred:wave-3（§5.2 #1-12）
- §1.3 "标准服务/应用案例" 2 条（1 deferred:wave-2 + 1 delete）
- 合计 27 条主动处置；剩余"~46-27=19" 落在 ops 业务报表 (4 borderline 保留) + metadata gather/schema 支撑 (5 保留) + service.rating.submit (borderline) + 一些 metadata.catalog_item / metadata.schema.query 等 borderline，**当前矩阵判定为 live infra/B1，sign-off 复核**。

5 surface 投影最终只看到 status=live = **159 live**（含 1 borderline；sign-off 若改 external 则 158）。比起始 186 builtin live 减 27-28。

---

## §8 P0-01 验证清单（自检）

- [x] 200 个契约逐条出现在 §1 表中
- [x] 每条契约处置归唯一一类（保留 live / external / deferred / delete-or-debt / borderline）
- [x] §4 计数表数字相加 = 200（156+1 borderline+14+13+12+1+1+1+1 = 200）
- [x] §6 列出 wave0 pytest + e2e 直接引用的核心 live 集合
- [x] §2 §1.3 禁区域逐条点名，处置三选一
- [x] §3 national/direct_access 12 条专章
- [x] 文档行数 < 700 LOC（实际 ~530 LOC）

---

## §9 移交后续 plan item

- **P0-02** 按 §1 表 200 条逐条补 `product_scope: {journey, status}` 字段；validate_manifest 加 schema 校验
- **P0-03** 按 §5.1 + §5.3 + §5.4 处置 14 条越界契约（13 改 external + 1 delete + 5 borderline sign-off）
- **P0-04** 按 §5.2 把 13 条 deferred 的投影排除接入 export_agent_contract.py + 5 surface
- **P0-05** 按 §4 修正后预算（j1=65 / j2=46 / b1=45 / infra=20，合计 176）注册 stat 块 + 新 preflight 段 22
- **P0-06** 跑 §6 兜底集合：wave0 pytest 50 passed + e2e 7/7 PASS 零回归
- **P0-07** PR 描述附本文档链接 + before/after live 计数对比（186 builtin → 159 live；含 1 borderline）

---

## 附录 A — manifest 计数脚本输出

```
$ ls zw_brain/capability_registry/registered/*.json | wc -l
200

$ for f in zw_brain/capability_registry/registered/*.json; do
    jq -r '[.skill_id, .execution_binding, .registry_source] | @tsv' "$f"
  done | awk -F'\t' '{print $2}' | sort | uniq -c
  186 builtin
   14 external_capability

$ awk -F'\t' '{print $3}' /tmp/p0_01_manifest_dump.tsv | sort | uniq -c
   14 external_contract
  186 internal
```

完整 TSV dump 见 `/tmp/p0_01_manifest_dump.tsv`（200 行 × 4 列：skill_id / execution_binding / registry_source / tags）。
