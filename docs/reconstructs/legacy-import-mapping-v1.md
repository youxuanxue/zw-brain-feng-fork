# 旧平台样例数据 → zw-brain 数据模型一键导入映射 v1

> **日期 / 状态**：2026-05-06 / draft（待评审；review 通过后进入阶段 1）
> **范围**：`old/10示例数据/*.sql`（<!-- stat:legacy.import.schemas -->17<!-- /stat --> 个 mysqldump，<!-- stat:legacy.import.tables-total -->740<!-- /stat --> 张旧表，~445 MB）→ `zw_brain/domain/models.py`（<!-- stat:legacy.import.record-classes -->58<!-- /stat --> 个 Record 类）。
> **单一事实源**：本文是"哪张旧表去哪、哪些字段缺位、哪些不导入、跨 schema 桥接顺序"的单一事实源。专题方案 `dsp-*-reconstruction-plan-v1.md` 是设计依据，本文是执行结论。
> **不在本文范围**：旧 URL/旧 controller/旧菜单兼容（按 GATE-1 D-全新项目口径明确不兼容）。

## 如何使用本文档

- **要写 mapper** → 找你那个 schema 在 §一 的小节 + 读 §四桥接顺序，就能动工。
- **要审 mapper PR** → §〇 关键政策 + §六 准入清单 是 review 检查项。
- **要补 record** → §二 缺位清单 <!-- stat:legacy.import.missing-records -->12<!-- /stat --> 项；M1–M6（<!-- stat:legacy.import.missing-resolved -->6<!-- /stat -->/6 已落地）。
- **要决定导入边界** → §三 不导入清单 + §五 加速上线素材。
- **不要**把本文当设计文档读：设计在 `docs/approved/*` 与 `docs/reconstructs/dsp-*-plan-v1.md`，本文只产出执行结论。

## 〇、关键政策（导入器必须遵守）

1. **租户口径** — 所有 canonical record 统一注入 `tenant_id="sd-default"`（[2026-05-06] 单租户单省山东省决策）。旧组织码（`11370000MB284651XL` 省大数据局、`11370000004504927A` 省公安厅、`370000000000` 山东省）按真值灌入 `OrgProjectionRecord` / `RegionProjectionRecord`，不参与 tenant_id 派生。
2. **敏感字段策略**（[2026-05-06] 覆盖 CLAUDE.md §1.3.6 的局部口径）：
   - **业务可见敏感字段**（个人/组织联系信息：姓名、手机号、邮箱、单位联系人、地址）— **允许原值入库**到 `LegacyObjectMappingRecord` / canonical 聚合 / 投影。读出口（Skill 出参 / WebUI / dashboard / 日志 / 审计 receipt / 导出文件）必须按角色掩码（手机号前 3 后 4、姓名姓+⼈），由 domain repository 出口或 Skill 响应序列化层统一封装。
   - **真正机密**（密码、Token、密钥、证书、内部 IP/端口、DB 连接串、文件服务器路径）— **仍按 §1.3.6 禁止入库**。`db_database_node` / `meta_host` / `db_meta_database.password` / `pub_user.password` / `dc_datasource` / `pub_db` 等表/字段不得明文进入新库；如需保留迁移证据，仅落 `AdapterRunRecord.source_ref`（哈希引用）或脱敏摘要。
3. **数据量** — 全量解析、按 mapper 过滤；不导入清单见 §三。
4. **PR 形态** — 与 WebUI 文案/demo seed/真组织 projection 注入并入第一个 PR（"导入 + 真业务气味"单一意图）。
5. **审计纪律** — 每条 mapper 写入必须留 `LegacyObjectMappingRecord`（旧 ID 桥接）+ `AdapterRunRecord`（导入批次）+ `audit_event`（同步落库，按 D4）。冲突 `mapping_status='conflicted'`，不自动覆盖。

---

## 一、按 schema 分段的逐表映射表

落位 5 选 1：
- `→canonical` — 写入 zw_brain.domain canonical 聚合
- `→projection` — 只读投影、运营摘要
- `→external_mapping` — 仅落 `ExternalObjectMappingRecord` receipt，不入聚合
- `→legacy_mapping` — 仅旧 ID 桥接，落 `LegacyObjectMappingRecord`，不全字段迁
- `不导入` — 按 `legacy-repository-reconstruction-priorities-v1.md` §1.2 / D10 / N1 默认外化

行数估计三档：`<10` / `10-100` / `100+`。`MISSING:Xxx` 表示当前 `models.py` 无该 record，需先在阶段 1 之前补建（见 §二）。

### 1. `data_resource`（旧"数据资源库"招标补齐型）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `catalog_link_info` | 100+ | 不导入 | — | priorities §六 默认不重构；功能已收敛到 `CatalogEntryRecord` |
| `databasechangelog` / `databasechangeloglock` | <10 | 不导入 | — | liquibase 元表 |
| `resource_database_info` | 100+ | 不导入 | — | 与 `dsp_metaresource.db_meta_database` 重复，且含连接信息（机密） |
| `resource_link_info` | 100+ | 不导入 | — | 资源关联表，方案未涉及，按默认外化 |
| `resource_logo` | 100+ | 不导入 | — | logo 字节流；附件走对象存储 adapter |

### 2. `dsp_app_center`（应用中心）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `app_access` | 100+ | →projection | `ServiceInvocationMetricProjectionRecord` | 仅 app→service 调用样本作运营投影候选 |
| `app_audit_info` / `app_base_info` / `app_comments` / `app_config` / `app_details` / `app_label_info` | 0 ~ 10-100 | 不导入 | — | 应用中心 priorities §六 默认不重构 |
| `app_info` | 10-100 | →external_mapping (可选) | `ExternalObjectMappingRecord(local_aggregate_type='application_external')` | 仅当后续做应用→Capability 注册映射 |
| `applet_audit_info` / `applet_info` / `attachment_info` / `field_info` / `label_info` / `product_doc` / `unit_info` / `user_collections_info` / `shopping_cart` | 0 ~ 100+ | 不导入 | — | 全部 §priorities §六 |
| `resource_application_info` | 100+ | 不导入 | — | 与 `dsp_catalog.data_apply` 重复 |
| `databasechangelog*` / `flyway_schema_history` | <10 | 不导入 | — | 元表 |

### 3. `dsp_basesubject`（基础主题库 / 档案 / 标准 / 统计）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `archive_column` | 100+ | →projection | `MISSING:ArchiveTemplateProjectionRecord`（或归 `TopicPackageEvidenceRecord.payload_json`） | sharezone plan §2.4 案档归外部 adapter |
| `archive_data_syn_task` / `archive_data_syn_task_log` | <10 / 10-100 | →external_mapping | `AdapterRunRecord` | 同步任务摘要 |
| `archive_customize*` / `archive_data_field_link` / `archive_data_link` / `archive_filter_customize` / `archive_group*` / `archive_template` / `archive_type` | 0 ~ 100+ | 不导入 | — | 档案模板按 §1.2 |
| `basesubject_info` | <10 | →legacy_mapping | `LegacyObjectMappingRecord(canonical_type='topic_package')` | sharezone plan §2.4 主题素材作 `TopicPackageRecord` 候选 |
| `basesubject_*` 其余 | 0 | 不导入 | — | 基础库作业 |
| `bs_database` | <10 | 不导入 | — | 含连接信息（机密） |
| `bs_*` 其余 / `bzk_*` / `corporation_*_statistic` / `corporation_super_enterprise*` / `corporation_*_prediction` / `population_*_statistic` / `data_schema_*` / `page_*` / `schema_*` / `service_statistics_*` / `webfinal_*` | 0 ~ 100+ | 不导入 | — | sharezone plan §2.4 明示不迁；指标投影另由 compliance plan 承接 |
| `flyway_schema_history` | 10-100 | 不导入 | — | 元表 |

### 4. `dsp_block`（区块链上链日志）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `block_apilog` | 10-100 | →projection | `AnchorOutboxRecord` + `AuditReceiptRecord`（已存在） | dataservice plan §3.7 |
| `block_app` | 10-100 | →external_mapping | `ExternalObjectMappingRecord(external_system='blockchain')` | 应用上链注册映射 |
| `block_apply` / `block_catalog` / `block_resource` | 100+ | →external_mapping | `ExternalObjectMappingRecord` | 申请/目录/资源上链记录 |
| `block_success_log` | 100+ (9245) | →projection | `AuditReceiptRecord`（取摘要） | 成功日志摘要进 receipt |
| `block_org` | 100+ (18753) | 不导入 | — | 与 `pub_organ` 重复，由 `OrgProjectionRecord` 承接 |
| `block_user` | 100+ | 不导入 | — | 与 IAM 重复 |
| `block_err_log` / `flyway_schema_history` | 0 ~ <10 | 不导入 | — | 错误日志按 §1.2 |

### 5. `dsp_bsp`（基础支撑后台 — IAM/菜单/字典/组织）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `pub_user` | 100+ (710) | →projection | `ActorProjectionRecord` | bsp plan §3.2；密码/Token 字段**不迁**（机密） |
| `pub_organ` | 100+ (18752) | →projection | `OrgProjectionRecord` | bsp plan §3.2；A3 真组织 projection 入口 |
| `pub_organ_tree` / `pub_organ_map` / `pub_organ_of_view` / `pub_organ_view` / `pub_organ_window` / `pub_organ_history` / `pub_organ_type` | <10 ~ 100+ | →projection | `OrgProjectionRecord`（合并展开） | 树/快照入投影 |
| `pub_region` | 100+ (16731) | →projection | `RegionProjectionRecord` | bsp plan §3.2 |
| `pub_region_map` / `pub_region_of_type` | 0 | →projection | `RegionProjectionRecord`（关系合并） | — |
| `pub_role` | 10-100 | →projection | `RoleProjectionRecord` | — |
| `pub_user_role` / `pub_user_organ_role` / `pub_user_data_auth_org` / `pub_user_data_auth_region` / `pub_role_function` / `pub_role_resource*` / `pub_app_role*` | 10-100 ~ 100+ | →legacy_mapping | `LegacyPolicyMappingCandidateRecord` | bsp plan §五，需人工审核后才能进策略 |
| `pub_role_copy1` / `pub_user_role_copy1` / `pub_user_copy` / `pub_resource_copy1` | 10-100 | 不导入 | — | 影子副本 |
| `pub_user_login` / `pub_user_token*` / `pub_user_pwd_expire` / `pub_user_lock` / `pub_user_face` / `pub_user_token_refresh` / `pub_ca_company` | 0 ~ 100+ | 不导入 | — | 登录态/密码/锁/CA — **机密** |
| `pub_user_follow` / `pub_user_history` / `pub_user_msg` / `pub_user_opinion` / `pub_user_post` / `pub_user_collect*` / `pub_user_operation_log` / `pub_user_organ` / `pub_user_check` / `pub_user_cascade` / `pub_user_data` / `pub_user_app` / `pub_user_auth` / `pub_user_map` / `pub_user_style` / `pub_user_policy` | 10-100 ~ 100+ | 不导入 | — | priorities §六 |
| `pub_resource` / `pub_resource_hlj` / `pub_resource_audit` / `pub_resource_national` | 100+ | 不导入 | — | bsp plan §1.2 — BSP 内部菜单/接口权限"resource"，不是业务 resource |
| `pub_apps*` / `pub_app_*` / `pub_apps_icon` | <10 ~ 100+ | 不导入 | — | 应用注册 §priorities §六 |
| `pub_dict` | 100+ (826) | 不导入 | — | 通用字典中心 bsp plan §1.2 不迁 |
| `pub_config` / `pub_function*` / `pub_holiday` / `pub_icon` / `pub_country` / `pub_contact_*` / `pub_data_resource` / `pub_db` / `pub_flow*` / `pub_review_log` / `pub_shop` / `pub_post` | <10 ~ 100+ | 不导入 | — | bsp plan §1.2 |
| `webfinal_*` / `xxl_job_*` / `base_dict` / `base_system_config` | 0 ~ 100+ | 不导入 | — | 监控日志/调度 §priorities §六 |

### 6. `dsp_catalog`（目录 + 申请审批 P0 主旅程）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `data_catalog` | 100+ (216) | →canonical | `CatalogEntryRecord` + `LegacyObjectMappingRecord` | catalog plan §6.3 |
| `data_catalog_version` | 100+ | →canonical | `CatalogEntryVersionRecord` | — |
| `data_catalog_column` | 100+ (1288) | →canonical | `CatalogItemRecord` + `CatalogModelFieldRecord` | catalog plan §6.3 字段口径 |
| `data_catalog_column_extend_field` | 100+ | →canonical | `CatalogModelFieldRecord.field_policy_json.extension` | — |
| `data_catalog_column_version` | 100+ | →canonical | `CatalogModelFieldRecord`（version 快照） | — |
| `data_catalog_category` | 100+ (773) | →canonical | `CatalogModelRecord`（按分类语义聚合） | catalog plan §4.2 分组语义 |
| `data_catalog_extend_field` / `data_catalog_open_extend` | 0 ~ <10 | →canonical | `CatalogEntryRecord.summary_json.extension` | — |
| `data_catalog_tag` / `base_taginfo*` / `base_tag_relaction_type` | 0 ~ 10-100 | →canonical | `CatalogEntryRecord.summary_json.tags`（合并） | catalog plan §6.3 |
| `data_catalog_approve` | 100+ (607) | →canonical | `ApprovalCaseRecord` + `ApprovalStepRecord` + `ApprovalDecisionRecord` | catalog plan §6.3 |
| `data_catalog_duty_link` / `data_catalog_dutylist` | <10 | →canonical | `ApprovalCaseRecord.decision_payload_json.routing` | 责任人/部门 |
| `data_catalog_relation_statistics` / `_copy1` | 100+ (21105/6835) | →projection | `LineageRelationProjectionRecord` | catalog plan §6.2.3 |
| `data_apply` | 100+ (92) | →canonical | `ApplicationRecord` + `LegacyObjectMappingRecord` | exchange plan §五 |
| `data_apply_authrization` / `data_apply_authrization_approve` | <10 | →canonical | `DeliveryTaskRecord.payload_json.access_grant` + `ApprovalCaseRecord` | exchange plan §五 |
| `data_apply_change` | <10 | →canonical | `ApplicationRecord` + `payload_json.kind='change'` | — |
| `data_apply_column` / `data_apply_item` / `data_apply_pdf` | 0 ~ 10-100 | →canonical | `ApplicationRecord.payload_json.requested_items` | — |
| `data_apply_course` | 100+ (332) | →canonical | `ApprovalStepRecord` + `ApprovalDecisionRecord` | exchange plan §六 |
| `data_apply_course_opiniontype` | 0 | →canonical | 字典进 `CapabilityManifestRecord.manifest_json` 或参 §二 M13 | — |
| `data_apply_dept_approve` / `data_apply_review` | <10 ~ 100+ | →canonical | `ApprovalDecisionRecord` | — |
| `data_apply_renewal` / `data_apply_renewal_course` | 0 | →canonical | `ApplicationRecord` + `payload_json.kind='grant_renewal'` + `DeliverySubscriptionRecord` | — |
| `data_apply_statistics` / `data_apply_task` | 100+ / <10 | →projection | `ExchangeMetricProjectionRecord` | — |
| `data_resource` (catalog 内) | 100+ (127) | →canonical | `ResourceAssetRecord` + `LegacyObjectMappingRecord` | catalog plan §6.1 — 与 metaresource.rc_resource 合流 |
| `data_resource_api` | 10-100 | →canonical | `ResourceAssetRecord(resource_kind='api')` + `ResourceChannelBindingRecord` | dataservice plan §3.1 |
| `data_resource_approve` | 0 | →canonical | `ApprovalCaseRecord` | — |
| `data_resource_file` | 10-100 | →canonical | `ResourceAssetRecord(resource_kind='file')` + `ResourceChannelBindingRecord` | — |
| `data_resource_general_statistics` / `data_resource_review_statistics` / `data_resource_statistics*` | 100+ (50050/2244/3730) | →projection | `ExchangeMetricProjectionRecord` | exchange plan §5.2.3 |
| `data_resource_table` / `data_resource_table_column` | 10-100 / 100+ | →canonical | `ResourceSchemaSnapshotRecord` + `ResourceSchemaMappingRecord` | catalog plan §6.2.1 |
| `data_resrevoke_course` | 0 | →canonical | `ApprovalCaseRecord` + `decision_payload_json.kind='resource_revoke'` | — |
| `data_basic_elem_catalog*` / `data_ext_elem_catalog_compile_task*` / `data_standard_catalog*` / `standard_catalog_*` / `data_recommend*` | 0 ~ 100+ | →external_mapping + projection | `MISSING:StandardAssetProjectionRecord` + `ExternalObjectMappingRecord` | compliance plan §3.1 标准资产候选；§二 M5 |
| `data_ext_elem_catalog_compile_task_objection` | <10 | →canonical | `ObjectionCaseRecord` | 编制异议 |
| `data_cascade_catalog_topic` / `data_cascade_interface_log` / `data_cascade_plat_info` / `data_cascade_record_log` | 0 | →external_mapping | `ExternalObjectMappingRecord` + `AdapterRunRecord` | data-connect plan §2.5 |
| `data_history_catalog_deal` / `data_history_catalog_deal_approve` | <10 | →canonical | `CatalogEntryVersionRecord` + `ApprovalCaseRecord` | — |
| `data_advise_info` / `data_alert_history` / `data_feedback_info` / `data_comment_info` / `data_interact_feedback` | 0 ~ 10-100 | 不导入/→canonical(部分) | `ObjectionCaseRecord` 或 `MISSING:OpsIssuePatternProjectionRecord` | objection plan §五 — 反馈如属内容质量异议入 objection |
| `data_organization_statistics*` / `data_org_statistics_report` / `data_org_review_statistics` / `data_organ_system_statistics` / `data_duty_org_statistics_report` | 100+ (4250) | →projection | `ExchangeMetricProjectionRecord`（按组织维度） | — |
| `data_source_catalog_lk` / `data_source_column_lk` | <10 / 100+ | →canonical | `ResourceSchemaMappingRecord` | metadata 映射 |
| `model_catalog_*` / `model_dimension` / `model_properties` / `model_property_group` | <10 ~ 100+ | →canonical | `CatalogModelRecord` + `CatalogModelFieldRecord` | catalog plan §6 |
| `open_catalog_*` / `push_open_catalog` | <10 ~ 10-100 | →canonical | `CatalogEntryRecord` + `summary_json.visibility='open'`（合并） | — |
| `up_task_directory` / `up_task_general_*` | 10-100 ~ 100+ | →canonical | `ApprovalCaseRecord` + `decision_payload_json.kind='upload_task'` + `ApprovalStepRecord` | "上报任务"属审批/应用 |
| `share_group_permission` / `catalog_share_group` | 0 | →legacy_mapping | `LegacyPolicyMappingCandidateRecord` | sharezone plan §2.2 |
| `data_catalog_group*` / `data_catalog_dept_group_statistics_temp` / `data_catalog_theme_group_statistics_temp` / `data_catalog_trans_group` | 10-100 ~ 100+ | →projection | `MISSING:CatalogGroupProjectionRecord`（或 `TopicPackageItemRecord(ref_type='catalog_group')`） | catalog plan §4.2；§二 M7 |
| `catalog_quality_*` (7 张) | 10-100 ~ 100+ | →projection | `QualityEvidenceProjectionRecord` | catalog plan §4.1 |
| `os_*`（OSWorkflow 引擎旧表 7 张） | <10 ~ 10-100 | →legacy_mapping | `LegacyObjectMappingRecord` | catalog plan §7.3 drop |
| `statistic_catalog_compile` / `basic_catalog_complie_statistic` / `table_exchange_detail_num` | 100+ | →projection | `ExchangeMetricProjectionRecord` | — |
| `data_group_permission` | 100+ | →legacy_mapping | `LegacyPolicyMappingCandidateRecord` | — |
| `datasource_trans_orgcode` | 0 | →projection | `OrgProjectionRecord`（编码转换快照） | — |
| `data_catalog_copy1/copy2` / `data_catalog_column_copy1` / `data_catalog_column_20241126` / `data_catalog_category_copy1` | 100+ | 不导入 | — | 影子副本 |
| `data_catalog_export` / `data_catalog_import` / `data_import_template` | 10-100 | 不导入 | — | catalog plan §7.3 drop |
| `data_score` / `data_score_record` / `data_catalog_score` / `data_interact_user_collection` | 0 ~ 10-100 | 不导入 | — | catalog plan §7.3 drop（评分/收藏） |
| `data_apply_old` / `data_apply_report` / `data_resource_export` / `data_resource_statistics_temp` / `data_refund_theme*` / `dockapply*` / `news_*` / `resource_backup` / `task_catalog_job` / `data_layout` / `data_search_records` / `data_item_info` / `data_item_material` / `jingan_kbjbxx` / `jingan_kbxxxx` / `data_basic_elem_catalog_history` / `base_message_info` / `base_new_organ` / `base_system_info` / `base_system_statistics` / `certification_info` / `critical_business_info` / `access_audit_ja` / `webfinal_audit_log` / `webfinal_browse_log` / `user_operation_log` / `flyway_*` | 0 ~ 100+ | 不导入 | — | 见 §三 不导入分类 |

### 7. `dsp_connect`（数据直达 / 国家平台对接）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `batch_job_*`（10 张 Spring Batch 表） | <10 ~ 100+ | →external_mapping | `AdapterRunRecord` | data-connect plan §2.3 — Spring Batch 历史作 adapter run |
| `dc_area_mapping` / `dc_organ_mapping` | 0 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='org'/'region')` | data-connect plan §2.3 |
| `dc_catalog` / `dc_catalog_group` / `dc_catalog_item` | 10-100 ~ 100+ | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='catalog')` | data-connect plan §3.3 |
| `dc_example_*` | 0 ~ 10-100 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='topic_package')` | — |
| `dc_objection_*` (7 张) | <10 ~ 10-100 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='objection')` | data-connect plan §2.3；本地 canonical 由 `dsp_handling` 承接 |
| `dc_require*` | <10 ~ 10-100 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='application')` | — |
| `dc_resource_*` (≥10 张) | <10 ~ 100+ | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='resource'/'application')` | — |
| `dc_subscribe*` / `dc_to_subscribe` | <10 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='delivery_subscription')` | — |
| `dc_supply_baseinfo` | 0 | →external_mapping | `ExternalObjectMappingRecord` | — |
| `dc_opt_log` / `dc_sync_job` | 10-100 | →projection | `AdapterRunRecord` | — |
| `dc_organ` | 0 | →projection | `OrgProjectionRecord`（合并） | — |
| `dc_system` | 10-100 | →projection | `MISSING:ExternalSystemRegistryProjectionRecord`（外部平台清单）；或塞 `CapabilityPackageRecord.manifest_json` | §二 M9 |
| `dc_datasource` | <10 | 不导入 | — | 含连接信息明文（机密） |
| `flyway_schema_history` | <10 | 不导入 | — | 元表 |

### 8. `dsp_example`（应用案例）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `data_example` | 10-100 | →canonical | `TopicPackageRecord` + `LegacyObjectMappingRecord` | sharezone plan §2.3 — A1 真业务案例的核心来源（10 个真实政务案例） |
| `data_example_contact` | <10 | →canonical | `TopicPackageRecord.display_snapshot_json.contacts`（**原值入库 + 读出口掩码**） | [2026-05-06] 敏感字段策略：手机号/姓名入库，读出按掩码 |
| `data_example_feedback` | <10 | →canonical | `ObjectionCaseRecord` 或 `TopicPackageEvidenceRecord(evidence_type='feedback')` | sharezone plan §2.3 |
| `data_example_file` | 10-100 | →canonical | `TopicPackageEvidenceRecord(evidence_type='file')` | — |
| `data_example_item` | 10-100 | →canonical | `TopicPackageItemRecord` | — |
| `data_example_push_link` | 10-100 | →external_mapping | `ExternalObjectMappingRecord(local_aggregate_type='topic_package',direction='outbound_report')` | sharezone + data-connect plan |
| `data_example_resource` | 0 | →canonical | `TopicPackageItemRecord(ref_type='resource')` | — |
| `data_example_comment` / `data_example_user_collection` | 0 | 不导入 | — | sharezone plan §2.3 |
| `flyway_schema_history` / `webfinal_browse_log` | 0 ~ <10 | 不导入 | — | — |

### 9. `dsp_handling`（异议 P0）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `data_objection` | 10-100 (43) | →canonical | `ObjectionCaseRecord` + `LegacyObjectMappingRecord` | objection plan §五 |
| `data_objection_authz` | 10-100 | →canonical | `ObjectionEvidenceRecord(evidence_type='authorization')` | objection plan §3.2 |
| `data_objection_catalog` | 10-100 | →canonical | `ObjectionEvidenceRecord(evidence_type='catalog')` | — |
| `data_objection_content` | 0 | →canonical | `ObjectionEvidenceRecord(evidence_type='quality')` | — |
| `data_objection_evaluate` | <10 | →canonical | `ObjectionEvaluationRecord` | — |
| `data_objection_process` | 100+ (251) | →canonical | `ObjectionProcessRecord` | — |
| `data_objection_resource` | 0 | →canonical | `ObjectionEvidenceRecord(evidence_type='resource')` | — |
| `data_objection_use` | 10-100 | →canonical | `ObjectionEvidenceRecord(evidence_type='usage')` | — |
| `data_message_info` | 100+ (186) | 不导入 | — | objection plan §1.2：通知 adapter，不进核心 |
| `flyway_schema_history` | 10-100 | 不导入 | — | — |

### 10. `dsp_message`（消息中心）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| 全部 8 张表（`dsp_business_code` / `dsp_inside_message_type` / `dsp_message` (193557 行) / `dsp_message_err` / `dsp_message_retry` / `dsp_message_task` / `dsp_relation` / `dsp_site_message` (192327 行) / `dsp_template` / `flyway_schema_history_apply`） | 0 ~ 100+ | 不导入 | — | priorities §六 message-center 默认外部化；286 MB 不进核心 |

### 11. `dsp_metaresource`（元数据 + 资源 P0）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `audit_todo_task` | 100+ (586) | →canonical | `ApprovalStepRecord`（待办）+ `ApprovalDecisionRecord` | catalog plan §6.3 |
| `database_manage_history` | 10-100 | →external_mapping | `AdapterRunRecord(operation='database_manage')` | catalog plan §6.3 — 仅脱敏证据 |
| `db_meta_column` / `db_meta_column_history` | 100+ (2302) | →canonical | `ResourceSchemaSnapshotRecord` + history 进 evidence | catalog plan §5.2 |
| `db_meta_foreignkey*` / `db_meta_index*` | <10 ~ 10-100 | →canonical | `ResourceSchemaSnapshotRecord.schema_json`（合并） | — |
| `db_meta_table` / `db_meta_table_history` / `db_meta_table_data_num` | 100+ (329/38/54607) | →canonical/projection | `ResourceSchemaSnapshotRecord`（结构）+ `ExchangeMetricProjectionRecord`（行数） | — |
| `meta_baseinfo` / `meta_baseinfo_history` | 100+ (2683/278) | →canonical | `ResourceSchemaSnapshotRecord` | — |
| `meta_data_center_area` | 10-100 | →projection | `RegionProjectionRecord` | — |
| `meta_gather_task` / `meta_gather_task_log` | 10-100 | →projection | `MetadataGatherEvidenceProjectionRecord` | catalog plan §6.2.2 |
| `meta_log` | 0 | →projection | `AuditEventRecord`（仅写动作） | — |
| `meta_model_info` | 10-100 | →canonical | `CatalogModelRecord` | — |
| `meta_relation` / `meta_relation_column` | 0 | →projection | `LineageRelationProjectionRecord` + 列级见 §二 M10 | catalog plan §6.2.3 |
| `rc_catalog_materialize` | 10-100 | →external_mapping | `ResourceSchemaMappingRecord` evidence + `AdapterRunRecord(operation='materialize')` | catalog plan §6.3 |
| `rc_resource` | 100+ (106) | →canonical | `ResourceAssetRecord` | catalog plan §6.3 |
| `rc_resource_catalog_item_link` | 100+ (822) | →canonical | `ResourceSchemaMappingRecord` | catalog plan §6.3 — **核心绑定**（解决"挂接后不显示列"工单的关键证据） |
| `rc_resource_export` / `rc_resource_table` / `rc_resource_url` / `rc_resource_file` | <10 ~ 10-100 | →canonical | `ResourceChannelBindingRecord` | — |
| `rc_generate_file_conf` / `rc_generate_file_log` | 0 ~ 10-100 | →external_mapping | `AdapterRunRecord` | — |
| `rc_map_conf` | 0 | →canonical | `ResourceSchemaMappingRecord.config_json` | — |
| `resource_flow_log` | 100+ (1054) | →canonical | `ApprovalDecisionRecord` | catalog plan §6.3 |
| `resource_standard_changes` | <10 | →external_mapping | `MISSING:StandardAssetProjectionRecord`（变更通知） | §二 M5 |
| `system_push_data_log` | 10-100 | →projection | `AdapterRunRecord` | — |
| `graphdb_node` / `graphdb_node_column` / `graphdb_relation` / `graphdb_relation_attr` / `graphdb_relation_column` | 0 | →projection | `LineageRelationProjectionRecord`（仅 evidence） | catalog plan §6.3 |
| `db_database_node` / `db_meta_database*` (5 张) / `file_meta` / `file_meta_history` / `file_server*` | 0 ~ 10-100 | 不导入 | — | 含连接串/IP/路径（**机密**）；catalog plan §7.3 drop |
| `data_organization_statistics` / `etl_meta*` / `es_index_*` / `webfinal_browse_log` / `flyway_schema_history` | 0 ~ 10-100 | 不导入/→projection（仅 data_organization_statistics） | `ExchangeMetricProjectionRecord` | — |

### 12. `dsp_monitor`（监控告警 P2）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `automonitor_*` (7 张) / `cg_critical_business_info` / `cgservice_warning_rules` / `service_warning_rule` / `system_warning_rule` / `service_config` / `monitor_config` / `monitor_item` / `monitor_rule` | 0 ~ 10-100 | 不导入 | — | compliance plan §2.5 — 监控规则后台不迁，规则改走 `compliance.rule.configure` 重建（§二 M2） |
| `information_detail` / `interface_result` / `interface_task_config` / `interface_warning_rule` / `ip_connection_failure` / `product_call_result` / `product_service_config` / `product_service_warning_rule` / `product_task_config` | 0 ~ 100+ | →projection | `MISSING:HealthSignalProjectionRecord` | §二 M4 |
| `matter_classify_manage` / `matter_handle` / `matter_manage` / `manual_inspection_plan` / `warning_handle_process` | <10 ~ 10-100 | →canonical | `MISSING:ComplianceCaseRecord` | compliance plan §3.3；§二 M1 |
| `monitor_filled_result` / `monitor_planing` / `monitor_result_warning` / `monitor_results` / `monitor_warning` / `warning_message_info` (1134) / `warning_result` | <10 ~ 100+ | →projection | `MISSING:RiskEventProjectionRecord` | §二 M3 |
| `warning_notice_rules` / `warning_work_order_rules` | <10 | →canonical | `MISSING:ComplianceRuleRecord` | §二 M2 |
| `scheduling_audit` / `scheduling_detail` | <10 / 100+ | →projection | `AdapterRunRecord` | — |
| `knowledge_audit` / `knowledge_manage` / `log_warning_list` / `log_warning_rule` / `mail_send_history` / `phone_message_send_history` / `webfinal_audit_log_shanxi` / `flyway_schema_history` | 0 ~ 10-100 | 不导入 | — | priorities §六 |

### 13. `dsp_pdf`（文件 / PDF）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| 全部 12 张表（`app_auth` / `download_dic` / `doc_folder` / `doc_info` / `file_store` / `file_storearea` / `file_upload_breakpoint` / `file_upload_temp` / `sequence_number` / `student` / `token_info` / `flyway_schema_history`） | <10 ~ 100+ (file_store / doc_info 32k+) | 不导入 | — | priorities §六 `dsp-pdf` 默认外部化（对象存储 adapter）；附件本体走 blob_object 引用 |

### 14. `dsp_perform`（绩效考核 P3）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| 全部 16 张（`analysis_catalog_resource` / `flyway_perform_history` / `kpi_*` (11 张) / `organ_base_statistics_data` / `sys_plan` / `sys_plan_monitor`） | <10 ~ 100+ | 不导入 | — | D10 第 2 项"绩效考核"明示不重构；如需指标投影候选，由 compliance plan `MISSING:MetricDefinitionProjectionRecord` 承接（§二 M6） |

### 15. `dsp_pipelines`（交换管道 / NiFi / Kettle 执行器）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `account_statistics` / `acct_folder_job` / `acct_table_job` / `statisc_exchange_*` / `statisc_subscribe_*` / `stats_exchange` / `stats_resource` | 0 ~ 100+ | →projection | `ExchangeMetricProjectionRecord` | — |
| `exchange_etl_type` / `exchange_node` / `exchange_node_mapping` / `exchange_node_usages` / `exchange_rule` / `exchange_pipelines` / `exchange_pipelines_database` / `exchange_pipelines_subscribe` | <10 ~ 10-100 | →canonical | `DeliveryTaskRecord.payload_json.execution_plan` + `DeliverySubscriptionRecord` | exchange plan §六 |
| `exchange_executor` / `exchange_executor_step` | 10-100 | →canonical | `DeliveryAttemptRecord` | — |
| `exchange_file_log` / `exchange_table_log` / `exchange_task_log` / `file_task_log` / `table_task_log` | 10-100 ~ 100+ | →projection | `DeliveryExecutionEvidenceRecord` | exchange plan §5.2.2 |
| `exception_messages` | 10-100 | →projection | `AdapterRunRecord.error_summary` | — |
| `job_warning_info` / `nifi_job_alarm_info` / `nifi_job_history` / `nifi_processor_record` | 10-100 | →projection | `DeliveryExecutionEvidenceRecord` + `MISSING:RiskEventProjectionRecord` | exchange plan §六 — 仅 evidence；§二 M3 |
| `probe_task` / `probe_task_column_rule` / `probe_task_column_rule_result` / `probe_task_result` | 10-100 ~ 100+ | →projection | `QualityEvidenceProjectionRecord` | — |
| `resource_applied` / `resource_applied_cancelled` | 10-100 | →canonical | `ApplicationRecord` + `LegacyObjectMappingRecord` | exchange plan §六 |
| `resource_change_log` | 100+ | →canonical | `ApprovalDecisionRecord` 或 `AuditEventRecord` | — |
| `resource_data` / `resource_file_download_log` | 0 ~ 10-100 | →projection | `DeliveryExecutionEvidenceRecord` + `DeliveryReceiptRecord` | — |
| `resource_status` | 100+ | →canonical | `ResourceAssetRecord.lifecycle_status` | — |
| `resource_lock` | <10 | 不导入 | — | 运行时锁，新系统 advisory lock 重建 |
| `subscribe_detail` / `subscribe_detail_file` / `subscribe_job` / `subscribe_job_child` | <10 ~ 10-100 | →canonical | `DeliverySubscriptionRecord` + `DeliveryAttemptRecord` | exchange plan §六 |
| `components_install*` / `components_list` / `components_version` / `convert_db_type*` / `db_js_text` / `warning_dictionary` / `gxpt_source_data_rct` / `webfinal_*` / `flyway_schema_history` | 0 ~ 100+ | 不导入 | — | dataservice plan §4.5 drop / 项目化扩展 |
| `meta_database` / `meta_database_feature` / `meta_host` | <10 ~ 10-100 | 不导入 | — | host_ip / db_passwd 明文（**机密**） |
| `exchange_pipelines_database_copy1` | 100+ | 不导入 | — | 影子副本 |

### 16. `dsp_require`（需求 / 申请 P0）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `business_requirements` | 0 | →canonical | `ApplicationRecord` + `payload_json.kind='business_requirement'` | — |
| `data_business` / `data_business_approve` / `data_business_performance` | 10-100 | →canonical | `ApplicationRecord` + `payload_json.kind='business'` + `ApprovalCaseRecord` | — |
| `data_connect_original_require` / `data_connect_original_require_link` / `data_connect_original_require_process` | <10 ~ 10-100 | →canonical | `ApplicationRecord` + `payload_json.kind='connect_require'` + `LegacyObjectMappingRecord`（与 dsp_connect 桥接） | exchange plan §六 |
| `data_item` | 10-100 | →canonical | `ApplicationRecord.payload_json.requested_items` | — |
| `data_item_material` | 0 | →canonical | `ApplicationRecord.payload_json.requested_items` | — |
| `data_original_require` | 10-100 (99) | →canonical | `ApplicationRecord` + `payload_json.kind='original_require'` + `LegacyObjectMappingRecord` | exchange plan §六 |
| `data_original_require_approve` | 10-100 | →canonical | `ApprovalCaseRecord` + `ApprovalDecisionRecord` | — |
| `data_original_require_column` | 100+ (248) | →canonical | `ApplicationRecord.payload_json.requested_items` | — |
| `data_original_require_link` / `data_original_require_resource` | 10-100 | →canonical | `ApplicationRecord.payload_json.intent.candidate_resources` | — |
| `data_require` | 10-100 (67) | →canonical | `ApplicationRecord` + `payload_json.kind='require'` + `LegacyObjectMappingRecord` | — |
| `data_require_approve` | 100+ (112) | →canonical | `ApprovalCaseRecord` + `ApprovalDecisionRecord` | — |
| `data_require_column` | 100+ (210) | →canonical | `ApplicationRecord.payload_json.requested_items` | — |
| `data_require_resolve_link` / `data_require_resource` | 10-100 | →canonical | `ApplicationRecord.payload_json.intent` | exchange plan §六 |
| `data_require_review` | 10-100 | →canonical | `ApprovalDecisionRecord` | — |
| `data_require_task_link` | 10-100 | →canonical | `ApprovalCaseRecord.decision_payload_json.routing` | — |
| `data_subtask` / `data_task` / `data_task_process` / `data_taskitem_link` | 10-100 ~ 100+ | →canonical | `ApprovalCaseRecord.decision_payload_json.routing` + `ApprovalStepRecord` | exchange plan §六 — 任务分解归并入审批轨迹 |
| `data_org_review_statistics` / `data_require_org_statistics` / `data_resource_review_statistics` | 100+ (2124/41835/6827) | →projection | `ExchangeMetricProjectionRecord` | — |
| `data_message` | 100+ | 不导入 | — | 通知 adapter |
| `flyway_schema_history` / `webfinal_*` | 0 ~ 10-100 | 不导入 | — | — |

### 17. `dsp_service`（数据服务 / API 网关）

| 旧表 | 行数估计 | 落位 | 新模型 / Skill / Adapter | 备注 |
|---|---|---|---|---|
| `api_service_info` | 10-100 (63) | →canonical | `ResourceAssetRecord(resource_kind='api')` + `LegacyObjectMappingRecord` | dataservice plan §3.1 |
| `api_service_data` / `api_service_general` / `api_service_proxy` | <10 ~ 10-100 | →canonical | `ResourceChannelBindingRecord` | dataservice plan §3.2 |
| `api_service_catalog` | 10-100 | →canonical | `CatalogEntryRecord`（API 分组目录） | — |
| `api_service_org` | 0 | →canonical | `ResourceAssetRecord.owner_org_snapshot` | — |
| `api_service_app` | 10-100 | →canonical | `ApplicationRecord` + `DeliveryTaskRecord.payload_json.access_grant` | dataservice plan §3.6 — **app_secret/access_token 字段不入明文**，必须密钥引用 |
| `api_access_ip` / `api_black_list` / `api_white_list` / `api_service_filter` / `api_service_fuse` / `api_service_pool` | <10 | →canonical | `ResourceChannelBindingRecord.gateway_policy_json` | dataservice plan §3.6 |
| `api_check_info` | 100+ (251) | →projection | `ResourceApiTestProjectionRecord` | — |
| `api_group` / `api_group_lk` | 100+ (996) | →canonical | `CatalogEntryRecord`（API 分组）+ `CatalogItemRecord` | dataservice plan §3.6 |
| `api_monitor_log` / `api_service_counter` / `api_service_statistic` / `api_service_times` (22353) | 0 ~ 100+ | →projection | `ServiceInvocationMetricProjectionRecord` | dataservice plan §3.4 |
| `api_service_errors` | 10-100 | →projection | `ServiceInvocationMetricProjectionRecord` + `MISSING:RiskEventProjectionRecord` | §二 M3 |
| `api_service_node` | 0 | →projection | `GatewayRuntimeStatusProjectionRecord` | — |
| `app_base_info` | 10-100 | →external_mapping | `ExternalObjectMappingRecord`（消费应用） | — |
| `datasource` | 0 | 不导入 | — | 含连接信息（**机密**） |
| `flyway_schema_history` / `webfinal_*` | 0 ~ 10-100 | 不导入 | — | — |

---

## 二、缺位清单（决定导入器能否跑通）

按"业务语义 → 旧来源 → 当前缺位 → 建议"列出。每条都对应方案明确提到、但 `models.py` 里**没有承接 record** 的对象。

| # | 业务语义 | 旧来源 | 当前缺位 | 建议 |
|---|---|---|---|---|
| **M1** | **合规 case 主单** | `dsp_monitor.matter_handle` / `warning_handle_process` | 无 record；compliance plan §3.3 明确状态机 detected→…→closed | **新增** `ComplianceCaseRecord`（status: detected/acknowledged/assigned/remediating/resolved/closed/dismissed），关联 target_type/target_id |
| **M2** | **合规规则定义** | `dsp_monitor.warning_notice_rules` / `cgservice_warning_rules` | 无 record；当前只有 skill `compliance.rule.configure` 但落库无承接 | **新增** `ComplianceRuleRecord`（rule_kind, target_scope, threshold_json, source_ref） |
| **M3** | **风险事件投影** | `dsp_monitor.warning_message_info` / `monitor_warning` / `dsp_pipelines.nifi_job_alarm_info` / `api_service_errors` / `dsp_block.block_err_log` | 无 record；compliance plan §3.1 明确为只读投影 | **新增** `RiskEventProjectionRecord`（event_kind, severity, source_ref, target_ref, generated_at） |
| **M4** | **健康信号投影** | `dsp_monitor.product_call_result` / `interface_result` / `ip_connection_failure` / `dsp_pipelines.nifi_processor_record` | 无 record；compliance plan §3.1 明确为只读投影 | **新增** `HealthSignalProjectionRecord`（subject_kind=service/adapter/channel/task, status, metric_json） |
| **M5** | **标准资产候选投影** | `dsp_catalog.data_basic_elem_catalog*` / `data_standard_catalog*` / `data_recommend*` / `dsp_metaresource.resource_standard_changes` / `old/08标准服务系统标准数据` | 无 record；compliance plan §3.1 + D6 明确"未确认数据元只能候选" | **新增** `StandardAssetProjectionRecord`（asset_kind=element/dict/rule/doc, status=candidate/authoritative, source_ref） |
| **M6** | **指标定义投影** | `dsp_perform.kpi_index_*` | 无 record；compliance plan §3.1 | **新增** `MetricDefinitionProjectionRecord`（metric_kind, dimension_json, formula_ref, owner_org） |
| **M7** | **目录分组投影** | `dsp_catalog.data_catalog_group*` / `catalog_share_group` / `share_group_permission` / `dsp_basesubject.archive_group*` | catalog plan §4.2 明确"目录分组只服务发现"，但 `models.py` 无独立 group projection | **建议归并**到 `TopicPackageItemRecord(ref_type='catalog_group')`；或新增 `CatalogGroupProjectionRecord` |
| **M8** | **运营反馈/工单 evidence** | `dsp_catalog.data_feedback_info` / `data_advise_info` / `data_comment_info` / `dsp_example.data_example_feedback` | catalog plan §6.3 提到 `ops_issue_pattern_projection`（可选） | **可选新增** `OpsIssuePatternProjectionRecord`；或归并到 `ObjectionEvidenceRecord(evidence_type='feedback')` |
| **M9** | **外部系统注册清单** | `dsp_connect.dc_system` / `data_cascade_plat_info` | 无承接外部平台清单的表 | **新增** `ExternalSystemRegistryProjectionRecord`（system_code, protocol_version, region, status）；或塞 `CapabilityPackageRecord.manifest_json` |
| **M10** | **lineage column-level projection** | `dsp_metaresource.meta_relation_column` / `graphdb_relation_column` | catalog plan §6.2.3 提"lineage_column_projection"，但 `models.py` 仅 `LineageRelationProjectionRecord`（表/库级） | **建议**：`LineageRelationProjectionRecord` 加 `column_lineage_json`；或新增 `LineageColumnProjectionRecord` |
| **M11** | **archive template / case archive evidence** | `dsp_basesubject.archive_template` / `archive_column` | sharezone plan §2.4 归外部档案 adapter | **可选**：在 `TopicPackageEvidenceRecord.payload_json` 内承载；或新增 `ArchiveTemplateProjectionRecord` |
| **M13** | **审批 opinion type 字典** | `dsp_catalog.data_apply_course_opiniontype` | 当前 `ApprovalDecisionRecord` 无字典关联 | **建议**：领域字典进 `CapabilityManifestRecord.manifest_json`，不单独建表 |

> **阻塞结论**：M1–M6 是 compliance plan 反复提到但未在 models.py 承接的核心类型，**P2 mapper（dsp_monitor / dsp_pipelines / dsp_perform / dsp_block）阻塞依赖这 6 个 record**。**已于阶段 1.5 通过 alembic 0007_compliance_projection.py 一并落地**（<!-- stat:legacy.import.missing-resolved -->6<!-- /stat -->/6 解除）；P2 mapper 已在 PR #12 落库。M7–M11 / M13 是 nice-to-have，可在阶段 2 末期视情况增补。

---

## 三、不导入清单（明示）

按"为什么不导入"分组：

### 3.1 priorities §六 默认外部化

- 全部 `dsp_message`（消息中心；286 MB / 193k+ 条消息历史）
- 全部 `dsp_pdf`（对象存储 + 文档服务 adapter）
- 全部 `dsp_app_center`（应用管理不是政务数据主旅程）
- 全部 `data_resource`（招标补齐型建库向导）
- `dsp_basesubject` 中 page_*（页面引擎）/ archive_customize / 专项扩展（`bzk_*`、`jingan_*`、`pub_resource_hlj`）
- `dsp_perform` 全部 `kpi_*` 表（D10 第 2 项"绩效考核"）

### 3.2 §1.2 / D10 / N1 — IAM/底座/低价值

- `dsp_bsp` 中 登录态 / 密码 / Token / 密钥 / CA / 短信 / 菜单 / 字典 / 通用流程 / xxl-job / webfinal（bsp plan §1.3）
- `dsp_bsp.pub_resource*` / `pub_role_resource*` / `pub_function*`（菜单/按钮/接口权限树）
- `dsp_monitor.automonitor_*` / `service_config` / `monitor_config` / `monitor_rule` / `mail_send_history` / `phone_message_send_history`（监控配置/通知历史）

### 3.3 含真正机密（仍按 §1.3.6 禁止入库）

> 与 §〇.2 区分：以下是**密码/Token/连接串/内部 IP/路径**等机密，与"姓名/手机号"等业务可见敏感字段不同口径。

- `dsp_metaresource.db_database_node` / `db_meta_database*` (5 张) / `file_meta` / `file_meta_history` / `file_server*`（连接串、IP、文件路径）
- `dsp_pipelines.meta_host` / `meta_database` / `meta_database_feature`（host_ip / db_passwd）
- `dsp_connect.dc_datasource`、`dsp_service.datasource`、`dsp_basesubject.bs_database`（连接信息）
- `dsp_bsp.pub_data_resource` / `pub_db` / `pub_ca_company` / `pub_user_login` / `pub_user_token*` / `pub_user_pwd_expire` / `pub_user_lock` / `pub_user_face` / `pub_user_token_refresh`
- `dsp_handling.data_message_info`（消息正文 + 通知细节，按 objection plan §1.2 通知 adapter）
- `dsp_service.api_service_app` 中的 `app_secret` / `access_token` 字段（**只迁 app_id 不迁密钥**，其余字段入 canonical）

### 3.4 元表 / 影子表

- 全部 schema 的 `flyway_schema_history*` / `databasechangelog*` / `databasechangeloglock`
- 全部 `*_copy1` / `*_copy2` / `*_20241126` 等命名带版本/copy 后缀的影子表
- `dsp_pipelines.exchange_pipelines_database_copy1`、`dsp_catalog.data_catalog_copy1/copy2` / `data_catalog_column_copy1` / `data_catalog_column_20241126` / `data_catalog_category_copy1`
- `os_*`（OSWorkflow 引擎旧表，仅作 legacy_mapping 证据，不入 canonical）

### 3.5 评论/收藏/评分（catalog plan §7.3 / dataservice plan §4.5 drop）

- `dsp_app_center.app_comments` / `user_collections_info` / `shopping_cart`
- `dsp_catalog.data_comment_info` / `data_score` / `data_score_record` / `data_interact_user_collection`
- `dsp_example.data_example_comment` / `data_example_user_collection`
- `dsp_bsp.pub_user_follow` / `pub_user_collect*`

### 3.6 项目化/地区扩展

- `dsp_pipelines.gxpt_source_data_rct`（广西项目化）
- `dsp_monitor.webfinal_audit_log_shanxi`（山西项目化）
- `dsp_basesubject.bzk_*` / `jingan_*`（专项扩展）
- `dsp_bsp.pub_resource_hlj`（黑龙江项目化）

---

## 四、跨 schema 关键 ID 桥接

> 导入顺序与 `LegacyObjectMappingRecord.legacy_key` 设计依赖这些外键关系。**导入顺序应严格按下表的 1→8 依赖链**，否则下游引用会落入 `mapping_status='unresolved'`。

### 4.1 主依赖链（按导入次序）

| 顺序 | 旧表 | 关键字段 | 被引用方 | canonical 依赖 |
|---|---|---|---|---|
| 1 | `dsp_bsp.pub_organ` / `pub_region` / `pub_user` / `pub_role` | `organ_id` / `region_code` / `user_id` / `role_code` | 几乎所有 schema 的 `org_id` / `creator_id` / `apply_org_id` 字段 | `OrgProjectionRecord` / `RegionProjectionRecord` / `ActorProjectionRecord` / `RoleProjectionRecord` 必须**最先导入** |
| 2 | `dsp_metaresource.rc_resource` + `db_meta_table` + `meta_baseinfo` | `rc_resource.id` / `meta_id` | `dsp_catalog.data_resource_table.resource_id`、`rc_resource_catalog_item_link.resource_id`、`api_service_info.resource_id` | `ResourceAssetRecord` 必须先于 catalog/service/exchange |
| 3 | `dsp_catalog.data_catalog` + `data_catalog_column` | `cata_id` / `column_id` | `data_apply.cata_id`、`data_resource.cata_id`、`rc_resource_catalog_item_link.catalog_item_id`、`dc_catalog`、`block_catalog`、`api_service_catalog`、`exchange_pipelines.cata_id` | `CatalogEntryRecord` / `CatalogItemRecord` 第三批 |
| 4 | `dsp_catalog.data_resource` + `dsp_metaresource.rc_resource` | `data_resource.id` / `resource_id` | `data_apply.resource_id`、`data_objection_resource`、`dc_resource_*`、`block_resource`、`exchange_pipelines.resource_id`、`subscribe_*.resource_id`、`api_service_info.resource_id` | `ResourceAssetRecord`（合并 catalog+meta 两侧） |
| 5 | `dsp_require.data_original_require` + `data_require` | `original_require_id` / `require_id` | `data_pipelines.requirement_id`、`data_handling.objection.requirement_id`、`data_example.push_link.require_id`、`dc_require.local_require_id`、`data_apply.require_id` | `ApplicationRecord` 第五批 |
| 6 | `dsp_catalog.data_apply` + `dsp_pipelines.resource_applied` | `apply_id` | `data_apply_authrization.apply_id`、`data_apply_course.apply_id`、`subscribe_job.apply_id`、`exchange_pipelines.apply_id`、`block_apply.apply_id`、`dc_resource_apply_info.local_apply_id`、`data_objection_authz.apply_id`、`data_example_push_link.apply_id` | `ApplicationRecord` 第六批 |
| 7 | `dsp_catalog.data_apply_authrization` + `dsp_pipelines.subscribe_job` | `auth_id` / `job_id` | `delivery_attempt`、`exchange_executor`、`api_service_app.auth_id`、`dc_subscribe.local_sub_id`、`block_success_log.auth_id` | `DeliveryTaskRecord` / `DeliverySubscriptionRecord` 第七批 |
| 8 | `dsp_handling.data_objection` | `objection_id` | `data_objection_process.objection_id`、`data_objection_evaluate.objection_id`、`data_objection_*.objection_id`、`dc_objection_*.local_objection_id`、`data_message_info.objection_id` | `ObjectionCaseRecord` 第八批（依赖 1+3+4+6） |

### 4.2 跨 schema 强外键（adapter 必须先解析）

| 旧侧外键 | 跨 schema 引用 | 说明 |
|---|---|---|
| `dsp_pipelines.exchange_pipelines.requirement_id` | → `dsp_require.data_require.require_id` | exchange plan §六：交付任务必须能回溯需求 |
| `dsp_pipelines.exchange_pipelines.apply_id` / `resource_id` / `cata_id` | → `dsp_catalog.data_apply` / `data_resource` / `data_catalog` | 交付计划三向引用 |
| `dsp_pipelines.subscribe_job.apply_id` / `resource_id` | → `dsp_catalog.data_apply` / `data_resource` | 订阅持续关系 |
| `dsp_handling.data_objection.objection_data_id` + `objection_type` | → `data_catalog`(type=1) / `data_resource`(type=2) / `data_apply_authrization`(type=3) / `delivery_task`(type=4) | objection plan §3.2：target_id + target_type 解析 |
| `dsp_handling.data_objection_authz.apply_id` | → `dsp_catalog.data_apply.apply_id` | 授权异议关联申请 |
| `dsp_example.data_example_push_link.require_id` / `apply_id` / `resource_id` | → `dsp_require` / `dsp_catalog` | 案例上报关联多对象 |
| `dsp_connect.dc_resource_apply_info.local_apply_id` | → `dsp_catalog.data_apply.apply_id` | external_mapping 必须能解析回 canonical apply |
| `dsp_connect.dc_objection_*.local_objection_id` | → `dsp_handling.data_objection.id` | 国家平台异议同步对应本地 objection |
| `dsp_connect.dc_subscribe.local_sub_id` | → `dsp_pipelines.subscribe_job.id` | 国家订阅对应本地 subscription |
| `dsp_service.api_service_app.app_id` | → `dsp_app_center.app_info` 或 `dsp_bsp.pub_apps` | dataservice plan §3.6 — 仅 external_mapping，不入 canonical |
| `dsp_block.block_apply.apply_id` / `block_catalog.cata_id` / `block_resource.resource_id` | → 各对应主表 | external_mapping 锚定回执 |

### 4.3 LegacyObjectMappingRecord key 设计建议

`LegacyObjectMappingRecord` 实际 schema：`(id, tenant_id, legacy_system, legacy_object_type, legacy_object_ref, canonical_type, canonical_ref, source_ref, mapping_status, evidence_json, mapped_at)`，UNIQUE 由 `(tenant_id, legacy_system, legacy_object_type, legacy_object_ref, canonical_type, canonical_ref)` 六元组锚定（一条旧对象可映射到多个 canonical 类型，但同一 6 元组组合唯一）。导入时按以下规则填字段：

- `legacy_object_type`：旧表名（如 `data_catalog` / `data_apply` / `rc_resource`）
- `legacy_object_ref`：旧主键值（如 `cata_id` / `apply_id` / `resource_id`）
- `canonical_type`：新 record 类名（如 `CatalogEntryRecord`）
- `canonical_ref`：新 record 的业务编码（如 `catalog_code` / `application_code`）
- `legacy_system`：按以下分组归并：

- `legacy_system = 'dsp-catalog3'`：`dsp_catalog`、`dsp_metaresource` 两库（catalog plan §1.3 合流）
- `legacy_system = 'dsp-exchange'`：`dsp_require`、`dsp_pipelines`（exchange plan §1.3 合流）
- `legacy_system = 'dsp-objection'`：`dsp_handling`
- `legacy_system = 'dsp-dataservice'`：`dsp_service`
- `legacy_system = 'dsp-sharezone'`：`dsp_example`、`dsp_basesubject`
- `legacy_system = 'dsp-bsp'`：`dsp_bsp`
- `legacy_system = 'dsp-data-connect'`：`dsp_connect`（外部映射用 `ExternalObjectMappingRecord`，不用 `LegacyObjectMappingRecord`）
- `legacy_system = 'dsp-blockchain'`：`dsp_block`（外部映射用 `ExternalObjectMappingRecord`）
- `legacy_system = 'compliance-ops'`：`dsp_monitor`、`dsp_perform`（仅运营 case 候选条目时使用）

---

## 五、加速上线试用｜可立即落地的真业务素材

样例数据除了"导进库"之外，更大的价值是给 WebUI / NL 加速器 / Skill 演示注入真业务气味。下列素材**必须与导入器同 PR 落地**，否则导入完客户也看不见区别。

### 5.1 真政务案例（A1 — WebUI 文案换真案例）

`dsp_example.data_example` 中 10 个真实政务案例直接灌进 WebUI demo seed：

| 业务标题（保留原文） | 主题分类（旧字段） | 责任单位 |
|---|---|---|
| 公司变更登记 | 01 | 省大数据局（11370000MB284651XL） |
| 不动产交易登记一体化平台 | 04 | 省大数据局 |
| 出生一件事 | 11,16 | 省大数据局 |
| 小微企业一次性创业岗位开发补贴申领 | 05 | 省大数据局 |
| 数据查询创新应用 | 03,11,15,16 | 省大数据局 |
| 停车场信息统一查询应用推广案例 | 05 | 省大数据局（已通过） |
| 中小学新生入学"一件事一次办" | 05 | 省大数据局 |
| 婚姻登记"全省通办" | 11 | 省大数据局 |
| 行政审批服务帮办代办 | 01 | 省大数据局（同意） |
| 测试案例 | 17 | 省大数据局 |

→ `TopicPackageRecord` 标题、摘要、负责单位直接用真值；WebUI 即刻看起来像在跑山东省真业务而不是空壳。

### 5.2 真目录召回字典（A2 — NL 加速器）

- `dsp_basesubject.basesubject_info` 主题分类
- `dsp_catalog.data_catalog_category` 773 个目录分类
- `dsp_metaresource.meta_baseinfo` 2683 个元数据资源标题（全省规模以上工业经济效益主要指标 / 房地产开发项目信息 / 学前教育幼儿基本信息 / 停车场信息 / 人口基本信息 / 中小学成绩分析 / 企业基本信息 / …）

→ 灌入 NL skill 召回字典；用户搜"人口"/"不动产"/"停车场"召回真目录。

### 5.3 真组织/区划 projection（A3）

- `dsp_bsp.pub_organ` 18752 行 → `OrgProjectionRecord`（"省大数据局 / 省公安厅 / 省人力资源社会保障厅 / …"）
- `dsp_bsp.pub_region` 16731 行 → `RegionProjectionRecord`（"山东省 / 济南市 / 青岛市 / 各区县"）
- `dsp_bsp.pub_user` 710 行 → `ActorProjectionRecord`（**应用 §〇.2 敏感字段策略**：原值入库，读出口掩码）

→ 5 消费面（WebUI/REST/CLI/MCP/A2A）的鉴权与审计上下文可见真组织名。

### 5.4 R1/R3/R5 端到端 demo seed（A4）

利用真实业务流转链：

```
dsp_require.data_require (67 条)
  → dsp_catalog.data_apply (92 条)
    → dsp_catalog.data_apply_course (332 条审批步骤)
      → dsp_catalog.data_apply_authrization
        → dsp_pipelines.subscribe_job + exchange_pipelines
          → dsp_pipelines.exchange_executor
            → dsp_handling.data_objection (43 条 + 251 条流程) 任意时点回环
              → dsp_example.data_example_push_link 上报回流
```

→ 选 3 条端到端 happy path + 1 条异议路径作为 demo seed，跑通 R1/R3/R5 黄金链路。

---

## 六、阶段 1 准入清单（已闭环，2026-05-06）

阶段 0 关闭、阶段 1 + 阶段 1.5 落地状态：

- [ ] **本文档评审通过**（用户 / 产品负责人签字确认 §一映射 + §三不导入边界） — pending review，进入阶段 2 前补
- [x] **新增 6 个 compliance/ops record**（M1–M6） — alembic `0007_compliance_projection.py` @ PR #11
- [x] **敏感字段掩码层就位** — `zw_brain/shared/sensitive_mask.py` @ PR #11，BrainService 读侧注入 @ PR #12，按 `ZW_BRAIN_MASK_ROLE` (`internal_admin`/`internal_viewer`/`external`) 决策
- [x] **`zw_brain/adapters/legacy/` 包结构** — parser / runner / 10 mapper 全在位 @ PR #11+#12
- [x] **`scripts/import_legacy_dumps.py` CLI 入口** — `list` / `parse-stats` / `cache` / `import` / `verify --strict` 五子命令 @ PR #11+#12
- [x] **mapper 默认行为** — 每条都写 `LegacyObjectMappingRecord` + `AdapterRunRecord` + `audit_event`；机密字段在 §〇.2 边界丢弃；冲突落 `mapping_status='conflicted'` 不自动覆盖（preflight 段 16 强制）
- [x] **导入次序硬约束** — §四.1 八步链，`runner.py` 串行调度；跨 schema 未解析引用走 `unresolved`，由 `verify --strict` 在 tenant 维度统一回扫

---

## 附录 A. 数字漂移防御（已落地）

阶段 1.5 完成后（M1-M6 落地、PR #12 闭环），下列结构性数字已在 `scripts/.stats.json` 注册并在本文 prose 中 stat-wrap，由 preflight §8 `scripts/sync-stats.sh --check` 自动校验：

| stat key | 当前值 | 出现位置 | compute 来源 |
| --- | ---: | --- | --- |
| `legacy.import.schemas` | <!-- stat:legacy.import.schemas -->17<!-- /stat --> | §范围 | `ls old/10示例数据/*.sql \| wc -l` |
| `legacy.import.tables-total` | <!-- stat:legacy.import.tables-total -->740<!-- /stat --> | §范围 | sum of `grep -ac '^CREATE TABLE'` over dumps |
| `legacy.import.record-classes` | <!-- stat:legacy.import.record-classes -->58<!-- /stat --> | §范围 | `grep -cE '^class .*Record' zw_brain/domain/models.py` |
| `legacy.import.missing-records` | <!-- stat:legacy.import.missing-records -->12<!-- /stat --> | §如何使用 | count of `M[N]` rows in §二 |
| `legacy.import.missing-resolved` | <!-- stat:legacy.import.missing-resolved -->6<!-- /stat --> | §如何使用 / §二 阻塞结论 | count of M1–M6 classes present in models.py |

不进入 stat-wrap 的"行级"快照数（e.g. 18752 organ / 16731 region / 710 user / 2683 meta_baseinfo）来自 dump 的具体内容，不同时点 dump 取值不同；它们只是 v1 评估时的快照值，不作为契约。当真实 dump 数据集变化时，prose 中如需新增此类数字应直接标注"快照 @YYYY-MM-DD"，不强行 stat-wrap。
