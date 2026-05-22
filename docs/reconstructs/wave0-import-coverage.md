# Wave 0 Import Coverage Survey — W0-01 摸底

> **目的**：W0-02 灌库之前盘清 `old/10示例数据/` 17 个 mysqldump 与 J1 黄金链路所需上游表的覆盖度，明确灌库顺序、行数下界、修复点。
> **范围**：W0-01 只读分析。不动 `.data/zw_brain.db`、不改 mapper、不改 .feature、不改业务代码。
> **关联**：plan.yaml W0-01 → W0-02；j1-* 6 个 .feature 见 `.testing/waves/wave-0-golden-path/features/`；mapper 总表见 `zw_brain/adapters/legacy/mappers/__init__.py`；既有详细映射见 `docs/reconstructs/legacy-import-mapping-v1.md`（本文不重复，只产 Wave 0 覆盖结论）。
> **运行环境**：parse-stats 必须在 `.venv` 中跑（`source .venv/bin/activate`，sqlalchemy 2.0.49）。

---

## §1. 17 个 dump 的 schema → table → 行数清单

数据来自 `python3 scripts/import_legacy_dumps.py parse-stats --json` 一次性输出。

### 1.1 schema 总览（17 dump，~445 MB，~875K rows）

| # | schema | 模块定位 | parsed rows | parsed tables | skipped tables |
|---|---|---|---:|---:|---:|
| 1 | data_resource | "招标补齐型"资源库（**整体不导入**） | 113 | 7 | 0 |
| 2 | dsp_app_center | 应用中心 | 934 | 12 | 9 |
| 3 | dsp_basesubject | 基础主题库 / 档案 / 统计 | 628 | 44 | 35 |
| 4 | dsp_block | 区块链证据 | 29,358 | 9 | 1 |
| 5 | dsp_bsp | 平台运行时（组织/用户/角色/区域/字典/资源/菜单） | 130,268 | 47 | 46 |
| 6 | dsp_catalog | 数据目录 + 申请 + 审批 + 评分 + 模型属性 | 103,901 | 92 | 70 |
| 7 | dsp_connect | 与上级 / 国家平台同步 receipt | 2,854 | 35 | 20 |
| 8 | dsp_example | 案例 / 应用场景（主题包素材） | 96 | 7 | 4 |
| 9 | dsp_handling | 异议处置 | 605 | 8 | 2 |
| 10 | dsp_message | 站内信 / 业务码 / 消息任务 | 399,248 | 9 | 1 |
| 11 | dsp_metaresource | 数据资源元数据 / 库表 / 字段 | 63,375 | 30 | 29 |
| 12 | dsp_monitor | 监控告警 / 调度 / 工单 | 1,684 | 21 | 28 |
| 13 | dsp_pdf | 文件存储 / 文档库 | 64,075 | 7 | 5 |
| 14 | dsp_perform | 绩效 / KPI / 报表 | 204 | 13 | 3 |
| 15 | dsp_pipelines | 交换通道 / 订阅 / 批处理 | 1,457 | 33 | 28 |
| 16 | dsp_require | 数据需求 / 业务需求 / 任务 | 52,322 | 27 | 5 |
| 17 | dsp_service | API 服务管理 / 调用计数 | 24,052 | 18 | 9 |

### 1.2 J1 直接上游关键表（按 schema 分组）

仅列 J1 黄金链路直接依赖的表；其他细节回退 parse-stats 原始 JSON。

**dsp_bsp（治理 / 组织 / 用户 / 角色）**

| 表 | 行数 |
|---|---:|
| pub_organ | 18,752 |
| pub_organ_tree | 21,123 |
| pub_organ_map | 21,103 |
| pub_organ_type | 4 |
| pub_region | 16,731 |
| pub_role | 73 |
| pub_role_resource | 3,633 |
| pub_user | 710 |
| pub_user_role | 4,187 |
| pub_user_organ_role | 136 |

**dsp_metaresource（资源事实源）**

| 表 | 行数 |
|---|---:|
| rc_resource | 106 |
| rc_resource_catalog_item_link | 822 |
| rc_resource_table | 71 |
| rc_resource_file | 41 |
| rc_resource_url | 2 |
| meta_baseinfo | 2,683 |
| db_meta_table | 329 |
| db_meta_column | 2,302 |

**dsp_catalog（目录 + 申请 + 审批）**

| 表 | 行数 |
|---|---:|
| data_catalog | 216 |
| data_catalog_column | 1,288 |
| data_catalog_column_extend_field | 693 |
| data_resource | 127 |
| data_resource_api | 29 |
| data_resource_table | 51 |
| data_resource_table_column | 582 |
| data_apply | 92 |
| data_apply_column | 21 |
| data_apply_course | 332 |
| data_apply_review | 112 |
| data_apply_dept_approve | 4 |
| data_apply_authrization | 2 |

**dsp_require（数据需求另一路）**

| 表 | 行数 |
|---|---:|
| data_original_require | 99 |
| data_original_require_approve | 43 |
| data_original_require_column | 248 |
| data_original_require_link | 83 |
| data_require | 67 |
| data_require_approve | 112 |
| data_require_column | 210 |
| data_require_review | 88 |

**dsp_service（API 资源 + 调用计数）**

| 表 | 行数 |
|---|---:|
| api_service_info | 63 |
| api_service_app | 35 |
| api_service_catalog | 63 |
| api_service_data | 5 |
| api_service_proxy | 82 |
| api_service_general | 23 |
| api_service_times | 22,353 |

### 1.3 高基数旁路（**非 J1 必需**）

`dsp_message.dsp_message`（193,557）+ `dsp_site_message`（192,327）+ `dsp_pdf.doc_info`（32,048）+ `dsp_pdf.file_store`（32,010）+ `dsp_block.block_org`（18,753）+ `dsp_block.block_success_log`（9,245）+ `dsp_catalog.data_resource_general_statistics`（50,050）+ `dsp_metaresource.db_meta_table_data_num`（54,607）+ `dsp_require.data_require_org_statistics`（41,835）+ `dsp_bsp.pub_organ_map / pub_organ_tree`（21,103 + 21,123，仅作组织树展开用，可选）。W0-02 全部跳过。

---

## §2. J1 黄金链路 6 个 .feature 期望的种子数据形态

### 2.1 j1-resource-discovery.feature（P2 资源发现）

- 角色：`ROLE_ORGAN_OPERATER`；负向 `ROLE_SECURITY_AUDIT`。
- 实体：catalog × 4（C101–C104）。
- 关键字段：`catalog_id` / `catalog_name` / `owner_org_code` / `owner_org_name` / `shared_type ∈ {1,2,3}` / `materialization ∈ {table, api, file}`。
- 行为：关键词检索；自然语言意图改写；目录树 → 详情 → 申请按钮；shared_type=3 不出检索；DOM 工程术语黑名单；跨消费面（API/CLI）schema 一致。
- 审计：`capability_call=resource.search`，audit_class=read。

### 2.2 j1-application-draft.feature（P3 申请草稿）

- 角色：`ROLE_ORGAN_OPERATER`（org=部门A_公安）。
- 实体：Application；status 状态机 `0 草稿 → 1 待审`。
- 关键字段：`resource_id` / `applicant_org` / `applicant_name` / 数据用途 / 业务系统 / 办事场景 / 堵点场景 / 申请依据 / 使用期限 / 附件。
- 行为：从 P2 跳转自动预填；暂存（必填可空）；提交（必填强校验）；R11 `applicant_org ≠ session.org` 拒绝；下线资源拒绝创建草稿；AI 助手不替提交。
- 审计：`capability_call=application.submit`，audit_class=write-critical。

### 2.3 j1-approval-unconditional.feature（P3 平台直接审批）

- 角色：`ROLE_BUSIAUDIT`（org=省大数据局）；负向 `ROLE_ORGAN_MANAGER`。
- 实体：Application 状态机 `1 待审 → 6 已授权`（单步，跳过 2-5）；ApprovalTask 记录 `decision=通过 / comment / actor_id / decided_at`。
- 行为：列表按"超时 > 临期 > 普通"排序；审批备注 + 回执；非 BUSIAUDIT 不可独立审批；撤回态不可审批；跨部门方向（R11）。
- 审计链：`application.submit → application.approve → credential.issue`。

### 2.4 j1-approval-conditional.feature（P3 部门审 + 平台复核两步）

- 角色：`ROLE_ORGAN_MANAGER`（提供方部门B）+ `ROLE_BUSIAUDIT`。
- 实体：Application 状态机迁移表（基线 §3.3）：`0→1 / 1→3 / 1→4 / 1→6 / 3→1 / 4→3 / 4→6 / 6→已收回`；shared_type=2 触发分支。
- 行为：第一步部门审 `1→4`；第二步平台复核 `4→6` 或 `4→3`；驳回后申请人补件 `3→1`（round +1）；R11 `owner_org_code` 计算"我作为提供方"队列；自审禁止；非法迁移返回 409 + audit reject。
- 审计：`application.dept_approve` / `application.platform_approve`。

### 2.5 j1-credential-issue.feature（P4 凭据领取）

- 角色：`ROLE_ORGAN_OPERATER`（申请人本人）；负向 `U_OTHER` / 撤销态。
- 实体：Credential（`owner=applicant_user_id` / `scope=catalog_id` / `expires_at`）— **legacy dump 不产，运行时签发**。
- 行为：审批通过后异步签发；首次明文 + 后续脱敏；4 件套（授权码 / curl / Python / Java + 配额 + 监控入口）；CLI / WebUI 凭据字段一致；非本人 403；申请撤销凭据立即 revoked；幂等签发（`idempotency_key=application_id`）。
- 审计：`credential.issue` / `credential.view`（read-sensitive）/ `credential.revoke`。

### 2.6 j1-api-call-monitoring.feature（P4 调用监控段）

- 实体：CapabilityCall / quota / rate_limit — **legacy dump 不产，运行时生成**。`dsp_service.api_service_times` 仅旧统计计数器，已映射为 `ServiceInvocationMetricProjectionRecord`，不可替代 per-call 记录。
- 行为：curl 调用 → 200 + 1 条监控；日配额耗尽 429 + retry_after；峰值并发 429 rate_limited；过期 401；scope 不匹配 403；只显示本人记录；DOM 工程术语黑名单。
- 审计：`capability_call=resource.fetch`（runtime 写入）+ 多种 `policy decision=reject` reason。

**最小 J1 种子（legacy 灌库需提供）= 2.1 + 2.2 + 2.3 + 2.4 上游实体**：组织 / 用户 / 角色 / 资源 / 目录 / 申请 / 审批；**2.5 + 2.6 不在灌库范围**，由 W0-05 配套 pytest 触发运行时生成。

---

## §3. 上游 → 目标 → mapper 覆盖度矩阵

落位枚举：`already_covered` / `partial_J1_gap` / `J2_or_B1_defer` / `no_target_needed`。

### 3.1 J1 必需（W0-02 必须灌入）

| legacy schema.table | 目标 domain 记录 | mapper | J1 必需 | 覆盖状态 |
|---|---|---|---|---|
| dsp_bsp.pub_organ | OrgProjectionRecord | GovernanceMapper | yes | already_covered |
| dsp_bsp.pub_region | RegionProjectionRecord | GovernanceMapper | yes | already_covered |
| dsp_bsp.pub_user | ActorProjectionRecord | GovernanceMapper | yes | already_covered |
| dsp_bsp.pub_role | RoleProjectionRecord | GovernanceMapper | yes | already_covered |
| dsp_bsp.pub_user_role + pub_user_organ_role | ActorOrgRoleBindingRecord | GovernanceMapper | yes | already_covered |
| dsp_metaresource.rc_resource | ResourceAssetRecord | CatalogMetadataMapper | yes | already_covered |
| dsp_metaresource.rc_resource_table / file / api / catalog_item_link | ResourceChannelBindingRecord / ResourceSchemaSnapshotRecord | CatalogMetadataMapper | yes | already_covered |
| dsp_catalog.data_catalog | CatalogEntryRecord | CatalogMetadataMapper | yes | already_covered |
| dsp_catalog.data_catalog_column | CatalogItemRecord | CatalogMetadataMapper | yes | already_covered |
| dsp_catalog.data_resource | ResourceAssetRecord（合流到 rc_resource） | CatalogMetadataMapper | yes | already_covered |
| dsp_catalog.data_apply | ApplicationRecord | ExchangeMapper | yes | already_covered |
| dsp_catalog.data_apply_course | ApprovalCaseRecord + ApprovalStepRecord + ApprovalDecisionRecord | ExchangeMapper | yes | already_covered |
| dsp_catalog.data_apply_dept_approve | ApprovalStepRecord（dept_approve 独立步骤） | ExchangeMapper | yes（conditional 分支） | partial_J1_gap |
| dsp_catalog.data_apply_authrization | DeliveryTaskRecord(state=granted) | ExchangeMapper | yes（凭据签发触发点） | already_covered |
| dsp_require.data_require / data_original_require | ApplicationRecord | ExchangeMapper | yes（alt 路径） | already_covered |
| dsp_require.data_require_approve / data_original_require_approve | ApprovalCaseRecord + ApprovalDecisionRecord | ExchangeMapper | yes（alt 路径） | already_covered |
| dsp_service.api_service_info | ResourceAssetRecord(resource_kind=api) | ServiceMapper | yes（materialization=api 链路） | already_covered |

**partial_J1_gap 修复清单（限 J1 必需字段，不扩散）**：

- `dsp_catalog.data_apply_dept_approve`（4 行）：现 ExchangeMapper 主走 `data_apply_course` 单一 step 序列。j1-approval-conditional 要求 `1→4→6` 中 `1→4` 与 `4→6` 是两个**独立 step**（actor 角色不同：`ROLE_ORGAN_MANAGER` vs `ROLE_BUSIAUDIT`）。需在 W0-02 灌库后由 W0-04 测试断言 `ApprovalStepRecord` 序列是否包含 `dept_approve` + `platform_approve` 两条；若 mapper 未拆分，**修复 1 行**在 ExchangeMapper 中将 `data_apply_dept_approve` 行追加为独立 step（不重写 mapper 架构）。如修复范围超过单分支，本条改写入 W0-08 deferred。

### 3.2 J2 / B1 / 后续 Wave defer（W0-02 跳过）

| legacy schema.table | 目标 | mapper | 覆盖 |
|---|---|---|---|
| dsp_handling.data_objection 等 8 表 | ObjectionCaseRecord / Process / Evidence / Evaluation | ObjectionMapper | J2_or_B1_defer |
| dsp_pipelines.subscribe_job / exchange_executor / exchange_pipelines | DeliveryTaskRecord / DeliverySubscriptionRecord / DeliveryAttemptRecord | PipelinesMapper | J2_or_B1_defer |
| dsp_connect.dc_* （37 表） | ExternalObjectMappingRecord | ConnectMapper | J2_or_B1_defer（Wave 3 协议） |
| dsp_example.data_example_* | TopicPackageRecord 系列 | TopicPackageMapper | J2_or_B1_defer（共享专区） |
| dsp_basesubject.basesubject_info | TopicPackageRecord 候选 evidence | TopicPackageMapper | J2_or_B1_defer |
| dsp_monitor.warning_* / matter_* / interface_result | ComplianceCaseRecord / RiskEventProjectionRecord / HealthSignalProjectionRecord | MonitorMapper | B1_defer（仅投影；W0-06 infra-contract-projection 若要 contract 一致性可顺手导入） |
| dsp_perform.kpi_* | MetricDefinitionProjectionRecord | PerformMapper | B1_defer |
| dsp_service.api_service_app / api_service_times | ExternalObjectMappingRecord / ServiceInvocationMetricProjectionRecord | ServiceMapper | partial — J1 主路径不依赖；若 W0-06 contract projection 触发跨消费面投影一致性断言，则 W0-02 一起导入；否则跳过 |

### 3.3 no_target_needed（不导入；既无 mapper 也无 J1 价值）

| legacy 范围 | 说明 |
|---|---|
| data_resource.* 全部 7 表 | legacy-import-mapping-v1.md §一.1 整体不导入；目录/元数据由 catalog + metaresource 主路径承接 |
| dsp_message.* | 站内信通道；J1 不依赖；规模 ~ 385K |
| dsp_pdf.* | 文件库；J1 附件流由对象存储 adapter（运行时）承接 |
| dsp_app_center.* | 应用中心；priorities §一.2 默认不重构 |
| dsp_block.* | 上链证据；外部 chain adapter，Wave 3 范围 |
| dsp_metaresource.db_database_node / meta_host / file_server / dc_datasource / pub_db / pub_user.password / pub_user.token | 含连接串 / 内部 IP / 密码 / token；legacy-import-mapping-v1.md §〇 真机密禁入 |
| 各 schema 的 flyway_* / databasechangelog* / webfinal_audit_log / *_history | 元表 / 旧审计 / 历史快照 |
| 各 schema 的 *_statistics / *_statistic_offset / *_statistics_temp | 旁路统计聚合，运行时重生成 |

### 3.4 W0-01 期间未触发 parser 修复

parse-stats 在 `.venv` 激活下一次通过（17/17 schema 全部解析无异常）。**未触发** goal §"parser 报错限 J1 修"路径。`scripts/import_legacy_dumps.py:25` 直接 import `LegacyImportRunner`（链路至 sqlalchemy），强制在 venv 内运行；非 venv 环境会失败 — 已知约束，不在 W0-01 修复范围。

---

## §4. W0-02 灌库建议

### 4.1 导入顺序（依赖优先，6 步）

1. **dsp_bsp**（GovernanceMapper）— 所有后续聚合的 `owner_org_code` / `applicant_org` / `actor_id` 依赖此投影。
2. **dsp_metaresource**（CatalogMetadataMapper 步骤 2：rc_resource → ResourceAssetRecord；衍生 binding/schema 表一并落）。
3. **dsp_catalog**（CatalogMetadataMapper 步骤 3-4：data_catalog → CatalogEntryRecord；data_resource 合流到 ResourceAssetRecord；data_catalog_column → CatalogItemRecord）。
4. **dsp_require**（ExchangeMapper alt 路径：data_require + data_original_require → ApplicationRecord；data_require_approve / data_original_require_approve → ApprovalCase）。
5. **dsp_catalog**（ExchangeMapper 主路径：data_apply → ApplicationRecord；data_apply_course → Approval 三件套；data_apply_dept_approve → 附加 ApprovalStep（partial_J1_gap 修复点）；data_apply_authrization → DeliveryTaskRecord granted）— 与步骤 3 同 schema，跑两次 mapper 即可（CatalogMetadataMapper 与 ExchangeMapper 各自独立 AdapterRunRecord）。
6. **dsp_service**（ServiceMapper：api_service_info → ResourceAssetRecord(kind=api)；其余表选导）。

### 4.2 J1 路径核心表行数下界（灌库后预期）

| 目标 record | 来源（合流） | 行数下界 |
|---|---|---:|
| OrgProjectionRecord | pub_organ | ≥ 18,000 |
| RegionProjectionRecord | pub_region | ≥ 16,000 |
| ActorProjectionRecord | pub_user | ≥ 700 |
| RoleProjectionRecord | pub_role | ≥ 70 |
| ActorOrgRoleBindingRecord | pub_user_role + pub_user_organ_role | ≥ 4,000 |
| ResourceAssetRecord | rc_resource(106) + data_resource(127) + api_service_info(63) | ≥ 290 |
| CatalogEntryRecord | data_catalog(216) | ≥ 200 |
| CatalogItemRecord | data_catalog_column(1,288) | ≥ 1,200 |
| ApplicationRecord | data_apply(92) + data_require(67) + data_original_require(99) | ≥ 250 |
| ApprovalCaseRecord | data_apply_course + data_require_approve + data_original_require_approve | ≥ 200 |
| ApprovalStepRecord（含 dept_approve / platform_approve 两态） | data_apply_course + data_apply_dept_approve(4) | ≥ 300 |
| ApprovalDecisionRecord | 同上 decision 行 | ≥ 300 |
| DeliveryTaskRecord(state=granted) | data_apply_authrization(2) | ≥ 2 |

**AC1 对账**（"catalog_entry / data_request / approval_case / credential / api_call 等核心表行数 > 0"）：

- ✅ `catalog_entry`（=CatalogEntryRecord）/ `data_request`（=ApplicationRecord）/ `approval_case`（=ApprovalCaseRecord）/ `delivery_task`：W0-02 灌库后均 > 0。
- ⚠️ `credential` / `api_call`（=CapabilityCallRecord）：**legacy dump 不产**。必须由 W0-05 配套 pytest 触发运行时 `credential.issue` + 至少 1 次 curl 调用，让 `CapabilityCallRecord` 落库才能 > 0。**W0-02 不构造它们，W0-05 是其唯一来源**；W0-09 PR 描述需在 AC1 证据链中明示这一拆分。

### 4.3 sd-default 单租户 normalize 状态

`zw_brain/adapters/legacy/tenant_normalizer.py`：

- `DEFAULT_TENANT = "sd-default"` ✅
- `LEGACY_SYSTEM_BY_SCHEMA` 覆盖全部 17 schema ✅（含 `data_resource → "data-resource"`、`dsp_block → "dsp-blockchain"` 等）
- 所有 mapper `__init__(*, tenant_id: str = DEFAULT_TENANT)` ✅
- **就绪**，W0-02 不需修。

### 4.4 W0-02 worker 起步指令（单行）

> 先 `source .venv/bin/activate` + `cp .data/zw_brain.db .data/backups/zw_brain.db.bak-$(date +%s)`（无则跳过 cp），然后按 §4.1 顺序逐 schema 跑 `python3 scripts/import_legacy_dumps.py import --schema <name>`（顺序：dsp_bsp → dsp_metaresource → dsp_catalog → dsp_require → dsp_catalog 二次（exchange 主路径）→ dsp_service），最后 `verify` + `sqlite3 .data/zw_brain.db` 按 §4.2 行数表 SELECT COUNT(\*) 逐项核对；遇 ApprovalStep 在 conditional 分支 `dept_approve` 行数为 0，**仅限**确认 ExchangeMapper 是否拆分 `data_apply_dept_approve` 为独立 step（单分支修复）；其他 mapper 报错 / 非 J1 范围 bug **全部归档到 W0-08**，不扩散修复。停在 J1 核心表行数 > 0 等 review。

---

W0-01 done: docs/reconstructs/wave0-import-coverage.md 完成，§1 共 17 个 dump（~445 MB，~875K parsed rows，含 J1 关键 5 schema 行数表）/ §2 列 6 features（最小种子 = 组织+用户+角色+资源+目录+申请+审批；凭据/调用由 runtime 生成不在导入范围）/ §3 覆盖度 17 already_covered / 1 partial_J1_gap（data_apply_dept_approve）/ 7 J2_or_B1_defer / 7 类 no_target_needed / §4 推荐先导 6 步（dsp_bsp → dsp_metaresource → dsp_catalog(catalog) → dsp_require → dsp_catalog(exchange) → dsp_service），详见文件。Ready for review.
