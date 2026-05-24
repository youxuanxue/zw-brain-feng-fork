# M0 mapper 覆盖判定表 — 17 dump × 12 mapper

> 架构基线：[`docs/approved/zw-brain-architecture.md`](../approved/zw-brain-architecture.md) §1.3 / §3.4 / §5.6 — 复造 / 不复造的权威源
> mapper 实现：[`zw_brain/adapters/legacy/mappers/`](../../zw_brain/adapters/legacy/mappers/) 12 mapper（basesubject / catalog_metadata / connect / exchange / governance / graph_lineage / objection / pipelines / projections.{Monitor,Perform} / service / topic_package）
> 真实 dump：`old/10示例数据/dump-dsp_*.sql` 17 个；schema 定义：`old/12-datastructure/dsp_*.xml`（本地工件，`.gitignore` 不入仓库；持有者本地 mirror）
> 表数防漂移：本表的 mapper 表数由 preflight 段 29 [`scripts/check_m0_mapper_coverage_doc.py`](../../scripts/check_m0_mapper_coverage_doc.py) 机械校验，与各 mapper `HANDLED_TABLES` 集合保持一致

## §0 用途

业务方与客户运维 sign-off 时回答两个问题：

1. **是否完整？** 老平台 17 个 dump 哪些进了 zw-brain，哪些不进
2. **不进的为什么？** §1.3 forbidden zone（不复造）/ adapter（外链）/ 漏做（应进但目前 mapper 缺）

判定一项 = 给出 verdict + 理由 + （如漏做）补 mapper 建议。本表不写 mapper 代码、不补 fixtures，漏做项各自独立后续 PR。

## §1 总览：17 dump × 4 verdict 矩阵

| dump（schema） | 表数 | verdict | 已覆盖 mapper / forbidden 引用 / 漏做建议 |
|---|---:|---|---|
| `dsp_catalog` | 181 | ✅ 已覆盖（主线） | catalog_metadata（24 表） + exchange（6 表）+ objection（subset）+ topic_package（subset） |
| `dsp_connect` | 56 | ✅ 已覆盖 | connect（44 dc_* 表） |
| `dsp_example` | 11 | ✅ 已覆盖 | topic_package（5 data_example_* 表 → TopicPackage） |
| `dsp_handling` | 10 | ✅ 已覆盖 | objection（8 data_objection_* 表）；data_message_info 复造（§1.3 消息中心） |
| `dsp_bsp` | 96 | ✅ 已覆盖（主体） | governance（23 表：20 pub_*/sys_* + 3 manifest → Org/Actor/Role）；xxl_job_* / webfinal_log_* 复造（§1.3 调度 / 审计日志由集团统一） |
| `dsp_service` | 27 | ✅ 已覆盖（核心摘要） | service（8 api_service_* 表 → ResourceApi/CapabilityPackage 摘要）；api_check_info / fuse / proxy 详细配置 复造（§1.3 API 服务网关 forbidden） |
| `dsp_pipelines` | 62 | ✅ 已覆盖（摘要） | pipelines（3 表 subscribe_job / exchange_executor / exchange_pipelines 摘要）；ETL 任务运行细节 ~59 表 复造（§1.3 数据治理中心 forbidden） |
| `dsp_perform` | 18 | ✅ 已覆盖（摘要） | projections.PerformMapper（kpi_index_info 1 表摘要）；kpi 详情/计算/规则 ~17 表 复造（§1.3 绩效考核 forbidden — D10） |
| `dsp_monitor` | 50 | ✅ 已覆盖（合规摘要） | projections.MonitorMapper（8 表 warning_* / matter_* / interface_result / product_call_result / ip_connection_failure → ComplianceOps）；automonitor_* / monitor_config / scheduling_* 等 ~42 表 复造（§1.3 集团运维监控 forbidden） |
| `dsp_require` | 34 | 🟡 部分已覆盖 + 待澄清 | data_require / data_original_require（exchange.py 已经从 dsp_catalog 拉过一遍）；data_business_* / data_task / data_subtask / data_item_* 待澄清是否进 Application |
| `dsp_basesubject` | 81 | ✅ 已覆盖（主体）+ 复造（统计/治理） | basesubject（11 表 → TopicPackage）F3 turn 2 落地；复造：population_* / corporation_* / archive_* / data_schema_* / basesubject_job_* / bs_subject_statistic 等 ~70 表 → §1.3 统计/治理 forbidden |
| `dsp_metaresource` | 62 | ✅ 已覆盖（含 graph_lineage）+ 复造（etl_meta / es_index） | graph_lineage（5 表 graphdb_node / graphdb_relation / graphdb_*_attr/column → LineageRelationProjectionRecord）F3 turn 3 落地；已覆盖：rc_resource_* / meta_baseinfo* / meta_gather_task / meta_relation / rc_catalog_materialize（catalog_metadata 已含）；复造：etl_meta_* / es_index_* / file_meta_* / database_manage_history → §1.3 数据治理 forbidden |
| `dsp_app_center` | 21 | 🚫 **复造** | §1.3 forbidden — 「不复造应用中心脚本管理」(D-Init 决策) |
| `dsp_message` | 10 | 🚫 **复造** | §1.3 forbidden — 「不复造消息中心」(D-Init 决策) |
| `dsp_pdf` | 12 | 🚫 **复造** | §1.3 forbidden — 「不复造文档管理 / 文件存储」(基线 §3.4 文件由集团对象存储统一) |
| `dsp_block` | 10 | 🚫 **复造**（待业务 sign-off） | 基线 §3.4 — 区块链对接走 adapter 异步锚定，**不在 zw-brain 内复造区块链快照**；block_apply / block_resource / block_org / block_apilog 是上链审计快照，由 audit_bus + adapter 处理 |
| `data_resource` | 7 | 🟡 **待澄清** | catalog_link_info / resource_link_info / resource_database_info — 可能与 catalog_metadata.rc_resource_url / rc_resource_table 重复；建议业务方确认是否需要补 mapper |

**统计**：✅ 已覆盖（含部分覆盖+合规摘要）= 11 个（F3 turn 2 dsp_basesubject + turn 3 dsp_metaresource graphdb 段加入）；🔴 漏做（含部分漏做）= 0 个；🚫 复造（§1.3 forbidden）= 4 个（app_center + message + pdf + block）；🟡 待澄清 = 2 个（require + data_resource）。

## §2 已覆盖（含 mapper 路由）

### 2.1 dsp_catalog（181 表）→ catalog 主线

| 老表 | 新模型 | 路由 mapper |
|---|---|---|
| `data_catalog` / `data_catalog_column` / `data_catalog_group` / `data_basic_elem_catalog` / `data_basic_elem_catalog_item` | `CatalogEntry` / `MetaColumn` / `CatalogGroup` | `catalog_metadata.py` |
| `data_resource` / `rc_resource` / `rc_resource_table` / `rc_resource_file` / `rc_resource_url` / `rc_resource_api` | `ResourceAsset` | `catalog_metadata.py` |
| `data_apply` / `data_apply_course` / `data_apply_authrization` / `data_apply_dept_approve` | `Application` / `Approval` / `Delivery` | `exchange.py` |
| `data_objection*` 子集 | `ObjectionCase` / `ObjectionProcess` | `objection.py` |
| `meta_baseinfo*` / `meta_table_column` / `meta_relation` / `meta_gather_task` / `catalog_quality_task` / `catalog_quality_result` | `MetaBaseInfo` / `MetaRelation` / `CatalogQuality` | `catalog_metadata.py` |

**未路由的 dsp_catalog 表**（~140 表）：
- `data_apply_old` / `data_catalog_column_20241126` / 各种 `_copy1` / `_copy2` 后缀 → 历史快照表，**复造**（基线 §1.3 不复造老平台历史快照）
- `analysis_catalog_resource` / `*_statistics*` / `*_report` → 统计/报表表，**复造**（基线 §1.3 不复造统计报表，D10 决策）
- `os_*` (workflow), `flyway_*`, `webfinal_*`, `pub_holiday_view` → 基础设施 / 历史日志，**复造**

### 2.2 dsp_connect（56 表）→ ConnectMapper 全覆盖

`connect.py` HANDLED_TABLES 涵盖 44 个 `dc_*` 表（除 `dc_datasource` / `dc_resource_base_info_copy1` 等历史/数据源连接配置外）。

未路由的 12 表（`batch_*`, `dc_datasource`, `dc_resource_base_info_copy1`, `flyway_schema_history`）→ **复造**（Spring Batch 任务表 + flyway 是集团运行时基础设施，不进 zw-brain）。

### 2.3 dsp_example（11 表）→ TopicPackageMapper

`topic_package.py` HANDLED_TABLES = `{data_example, data_example_item, data_example_file, data_example_feedback, data_example_contact}` 5 表 → `TopicPackage` 主线。

未路由：`data_example_push_link` / `data_example_comment` / `data_example_resource` / `data_example_user_collection` / `webfinal_browse_log` → 复造（推送配置 / 评论 / 浏览日志，§1.3 forbidden）。

### 2.4 dsp_handling（10 表）→ ObjectionMapper 8 表

`objection.py` HANDLED_TABLES = `{data_objection, data_objection_process, data_objection_evaluate, data_objection_authz, data_objection_catalog, data_objection_content, data_objection_resource, data_objection_use}` → `ObjectionCase` 主线 8 表。

`data_message_info` → **复造**（§1.3 消息中心 forbidden）。

### 2.5 dsp_bsp（96 表）→ GovernanceMapper 主体 + 大量 forbidden 复造

`governance.py` HANDLED_TABLES = 23 表（20 数据表：`pub_organ`/`pub_region`/`pub_user`/`pub_role`/`pub_user_role`/`pub_user_organ`/`pub_user_organ_role`/`pub_resource`/`pub_function`/`pub_role_function`/`pub_role_resource`/`pub_apps`/`sys_department`/`sys_region`/`sys_user`/`sys_role`/`sys_user_role`/`sys_role_permission`/`sys_user_department`/`sys_permission` + 3 manifest：`iaf_binding_manifest` / `role_mapping_manifest` / `capability_mapping_manifest`）→ `Org` / `Actor` / `Role` / `Capability` 主线。

未路由 ~74 表：
- `xxl_job_*` 8 表 → **复造**（集团统一调度，§1.3）
- `pub_app_*` / `pub_apps_copy1` / `pub_user_app` 等 → **复造**（应用中心，§1.3）
- `webfinal_audit_log` / `webfinal_access_log` / `webfinal_monitor_server` → **复造**（集团审计日志，§1.3）
- `pub_holiday` / `pub_user_face` / `pub_user_login` / `pub_user_lock` / `pub_user_history` / `pub_user_token*` → **复造**（IAM 细粒度状态由 IAF IAM 统一）
- `pub_organ_*_copy1` / `pub_user_*_copy*` / `pub_role_*_copy1` → **复造**（历史快照）

### 2.6 dsp_service（27 表）→ ServiceMapper 核心 8 表

`service.py` 已覆盖 `api_service_info` / `api_service_catalog` / `api_service_data` / `api_service_proxy` / `api_service_general` / `api_group` / `api_service_app` / `api_service_times` → `ResourceApi` / `CapabilityPackage` 摘要。

未路由 19 表：`api_access_ip` / `api_black_list` / `api_check_info` / `api_white_list` / `api_monitor_log` / `api_service_counter` / `api_service_errors` / `api_service_filter` / `api_service_fuse` / `api_service_node` / `api_service_org` / `api_service_pool` / `api_service_statistic` / `datasource` / `app_base_info` / `webfinal_*` → **复造**（§1.3 API 服务网关 forbidden — 限流/熔断/IP 黑白名单/监控由集团 API 网关统一）。

### 2.7 dsp_pipelines（62 表）→ PipelinesMapper 3 表摘要

`pipelines.py` 仅覆盖 3 摘要表：`subscribe_job` / `exchange_executor` / `exchange_pipelines` → `Delivery` / `ExchangeAttempt` 衔接。

未路由 59 表 → **复造**（§1.3 数据治理中心 forbidden — ETL 节点 / Nifi 配置 / Probe 任务 / 资源锁均由集团数据治理统一）。

### 2.8 dsp_perform（18 表）→ PerformMapper 1 表摘要

`projections.PerformMapper` HANDLED_TABLES = `{kpi_index_info}` → 仅 `kpi_index_info` 进 zw-brain `OpsServiceReport`。

未路由 17 表 → **复造**（D10 决策：基线 §1.3 「不做绩效考核」，5 低价值功能之一；KPI 详情/计算规则不进）。

### 2.9 dsp_monitor（50 表）→ MonitorMapper 8 表合规摘要

`projections.MonitorMapper` HANDLED_TABLES = 8 表：`warning_message_info` / `warning_handle_process` / `warning_notice_rules` / `matter_handle` / `matter_manage` / `interface_result` / `product_call_result` / `ip_connection_failure` → `ComplianceOps` 摘要。

未路由 42 表 → **复造**（§1.3 集团运维监控 forbidden — automonitor_* / monitor_config / scheduling_* / mail_send_history / phone_message_send_history 等由集团运维监控统一，AC7 通过 monitor adapter 异步接入）。

## §3 复造判定（§1.3 forbidden zone 明示）

基线 §1.3 forbidden zones（不复造）：

> 不复造数据治理 / 数据安全 / 消息中心 / API 服务网关 / 应用中心脚本管理 / 集团运维监控 / 绩效考核（D10）/ 大屏指挥中心（D15 二次反转）

四个 dump 整库判定 **复造**，理由直引 §1.3 / 历史决策：

| dump | 复造理由（§1.3 / D-编号） | 替代路径 |
|---|---|---|
| `dsp_app_center`（21 表） | 「不复造应用中心脚本管理」(§1.3 D-Init) | 应用配置由集团应用中心独立产品承载；zw-brain 通过 `pub_apps` 仅记录应用元信息（governance.py） |
| `dsp_message`（10 表） | 「不复造消息中心」(§1.3 D-Init) | 站内消息/邮件/短信由集团消息中心统一，zw-brain audit_bus 是审计链路非业务通知 |
| `dsp_pdf`（12 表） | 文档管理 / 文件存储（§3.4：「文件存储由集团对象存储统一」） | 文件元数据已通过 `catalog_metadata.rc_resource_file` 摘要进入 `ResourceAsset`；具体文件存储不在 zw-brain |
| `dsp_block`（10 表） | 区块链锚定走 adapter（§3.4 D4） | `audit_bus` 同步落库 + 区块链 adapter 异步锚定；block_apply / block_resource 不进 canonical 模型 |

## §4 漏做（需补 mapper / 业务方 sign-off）

### 4.1 dsp_basesubject — 主题库 + 统计混合 ✅ F3 turn 2 已落地

**81 表分两类**：

| 类别 | 表示例 | 是否进 zw-brain | 状态 |
|---|---|---|---|
| 主题库实体 | `basesubject_info` / `basesubject_object_info` / `basesubject_object_resource_link` / `basesubject_schema` / `basesubject_schema_item_link` / `basesubject_service_info` / `bs_resource` / `bs_resource_column` / `bs_catalog_info` / `schema_info` / `schema_resource` | ✅ **已覆盖** | `basesubject.py` 11 表 → `TopicPackageRecord` 主线，子结构 join 进 `display_snapshot_json`，`bs_resource` 同时进 `TopicPackageItemRecord`（按资源粒度授权）；F3 turn 2 落地 |
| 统计 / 归档 | `population_*` / `corporation_*` / `archive_*` / `basesubject_job_*` / `bs_subject_statistic` / `data_schema_export` / `data_schema_import` / `webfinal_*_log` | 🚫 **复造** | §1.3 不复造统计报表（D10）；archive_* / basesubject_job_* 由集团数据治理统一 |

**已落地**：`zw_brain/adapters/legacy/mappers/basesubject.py` + `tests/test_legacy_basesubject_mapper.py`（3 用例覆盖 happy / legacy mapping / error path）。dump `old/10示例数据/dump-dsp_basesubject-202604271138.sql` 中 11 表 INSERT 行为空（行业 basesubject 尚未启动），mapper 已就位、增量同步即可接入。

### 4.2 dsp_metaresource graphdb — 图数据库 lineage ✅ F3 turn 3 已落地

**62 表分三类**：

| 类别 | 表示例 | 状态 |
|---|---|---|
| 元数据 baseinfo | `meta_baseinfo` / `meta_baseinfo_history` / `meta_relation` / `meta_gather_task` / `rc_catalog_materialize` / `rc_resource*` / `db_meta_table` / `db_meta_column` / `resource_flow_log` | ✅ **已覆盖** — `catalog_metadata.py` HANDLED_TABLES 已含 |
| **图数据库 lineage** | `graphdb_node` / `graphdb_node_column` / `graphdb_relation` / `graphdb_relation_attr` / `graphdb_relation_column` | ✅ **已覆盖** — `graph_lineage.py` 5 表 → `LineageRelationProjectionRecord`（relation_scope="graphdb"）；start/end node + columns + attrs + rel-columns 嵌入 `relation_rule_json`；F3 turn 3 落地 |
| ETL meta / es_index / file_meta / database_manage_history | `etl_meta_*` 8 表 / `es_index_column` / `file_meta*` / `database_manage_history` 等 | 🚫 **复造** — §1.3 数据治理 forbidden（集团数据治理统一） |

**已落地**：`zw_brain/adapters/legacy/mappers/graph_lineage.py` + `tests/test_legacy_graph_lineage_mapper.py`（3 用例覆盖 happy / legacy mapping / NULL fail-closed）。dump `old/10示例数据/dump-dsp_metaresource-202604271411.sql` 中 graphdb_* 5 表 INSERT 行为空（图血缘尚未启用），mapper 已就位、增量同步即可接入。

## §5 待澄清（业务方 sign-off）

### 5.1 dsp_require — 与 dsp_catalog 部分重叠

dsp_require（34 表）和 dsp_catalog（181 表）都含 `data_require` / `data_original_require` / `data_apply` 等表，但 dsp_require 多了 `data_business_*` / `data_task` / `data_subtask` / `data_item_*` / `data_taskitem_link`。

**问题**：
1. dsp_require 是否是 dsp_catalog 的独立副本（schema-per-org），还是有独立业务语义？
2. `data_business_*` / `data_task` / `data_subtask` 是否需进 zw-brain `Application` / 新增 `BusinessTask` 实体？

**当前状态**：`exchange.py` 已覆盖 `data_require` / `data_original_require` / `data_apply` 等核心 6 表。dsp_require 内同名表与 dsp_catalog 内同名表的关系（覆盖 / 副本 / 独立）需业务方明示。

**建议**：业务方 sign-off 后决定：① dsp_require 整库判 `复造`（dsp_catalog 为唯一权威源）；② 或独立 mapper PR 补 `data_business_*` / `data_task` 等到新增实体。

### 5.2 data_resource — link/database/file_info 是否冗余

`dump-data_resource-*.sql`（7 表，含 `resource_database_info` / `resource_link_info` / `resource_logo` / `resource_task_info` / `catalog_link_info`）。

**问题**：
- `resource_database_info` vs `catalog_metadata.rc_resource_*`：是否冗余？
- `resource_logo` 是 ResourceAsset 的 logo 字段还是独立资源？

**建议**：业务方 sign-off 是否需要补 `data_resource` mapper（建议 mapper `data_resource.py` HANDLED_TABLES = `{resource_database_info, resource_link_info, resource_logo, resource_task_info, catalog_link_info}`）。如确认冗余则判 `复造`，否则补 PR。

## §6 总览统计

| Verdict | dump 数 | 备注 |
|---|---:|---|
| ✅ 已覆盖（主线或核心摘要） | 11 | dsp_catalog / dsp_connect / dsp_example / dsp_handling / dsp_bsp / dsp_service / dsp_pipelines / dsp_perform / dsp_monitor / dsp_basesubject（F3 turn 2 补） / dsp_metaresource（含 F3 turn 3 graphdb_* graph_lineage） |
| 🔴 漏做（含 sub-set 漏） | 0 | — |
| 🚫 复造（§1.3 forbidden zone 明示） | 4 | dsp_app_center / dsp_message / dsp_pdf / dsp_block |
| 🟡 待澄清（业务方 sign-off） | 2 | dsp_require（vs dsp_catalog 重叠）/ data_resource（vs rc_resource_* 重叠） |
| **合计** | **17** | — |

**漏做项后续 PR 候选** — 全部已落地：

1. ✅ `mapper/basesubject.py` — F3 turn 2 已落地（11 表 → TopicPackageRecord 主线 + 子结构）
2. ✅ `mapper/graph_lineage.py` — F3 turn 3 已落地（5 表 → LineageRelationProjectionRecord，独立 mapper 而非扩 catalog_metadata，便于图血缘按 relation_scope="graphdb" 独立查询）

剩余两项 🟡 待澄清（§5）需业务方 sign-off 推进。

## §7 评审签收

- [ ] 业务方（红军 / 产品负责人）已 sign-off §5 待澄清 2 项
- [ ] 业务方已 sign-off §4 漏做 2 项的优先级（M0 必接 / M0 后置 / 长期不接）
- [ ] §3 复造 4 项（§1.3 forbidden）业务方无异议
- [ ] preflight 段 16（mapper 完整性）保持通过 — 本表的判定不要求改动现有 mapper
