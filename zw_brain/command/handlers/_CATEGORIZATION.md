# handlers — capability 分桶清单（211 cap，SoT）

每个 capability 一行；新增 capability 必须同步本表 + [`zw_brain/command/dispatch.py`](../dispatch.py) DISPATCH_TABLE + 对应桶 handler 模块（基线 §11 反 per-tenant fork + R10/R11/R12 三层依赖）。

## 历史溯源

F1 拆分前 BrainService 单文件 8155 LOC，`_dispatch_skill` `match skill_id:` 共 172 case 分支但展平后 **185 unique cap**（12 个 adapter.national.* 多行 case 块 + 4 个 compliance.signal.ingest 类多 cap 单行 case 块均展平）。F1 完结后业务全部迁到本目录 40 handler module，BrainService 保留 ~3375 LOC 仅含 internal helper / lazy property / 异常类 / dataclass — 非业务逻辑。

## 分桶判定规则

- **J1（找数→用数）**：catalog/search/request/delivery/provider/objection 消费端流
- **J2（挂数→维数）**：topic_package/governance/policy mapping/compliance 生产/治理端
- **B1（后台支撑）**：ops/iam/projection/audit/system/registry/capability/package(cap-pkg)/tenant.capability
- **infra**：adapter.* / record_adapter_operation 透传 / legacy.* 迁移

## J1 找数→用数 — 96 caps

| capability_id | bucket | method_name | method_lines |
|---|---|---|---|
| `application.grant.approve` | j1 | `approve_application_grant` | 3873 |
| `recommendation.similar_catalog.suggest` | j1 | `handler_recommendation_similar_catalog_suggest` | E3 Wave-2 F6 新增 |
| `application.grant.renew` | j1 | `renew_application_grant` | 3894 |
| `application.grant.revoke` | j1 | `revoke_application_grant` | 3928 |
| `application.grant.suspend` | j1 | `suspend_application_grant` | 3912 |
| `application.resource.review` | j1 | `review_request` | 6245 |
| `application.draft.suggest` | j1 | `do_application_draft_suggest` | 0 |
| `application.resource.submit` | j1 | `create_request` | 5993 |
| `approval.case.decide` | j1 | `review_request` | 6245 |
| `approval.evidence.summarize` | j1 | `do_approval_evidence_summarize` | 0 |
| `approval.review_decide` | j1 | `review_request` | 6245 |
| `application.dept_approve` | j1 | `handler_application_dept_approve` | j1-approval-conditional 两步第一步（部门审 + 补件重提） |
| `application.platform_approve` | j1 | `handler_application_platform_approve` | j1-approval-conditional 两步第二步（平台复核） |
| `application.escalate_national` | j1 | `handler_application_escalate_national` | j1/escalate.py（C6 国家直达转报，计算态不入主状态机） |
| `approval.view` | j1 | `get_approval` | 3455 |
| `backflow.confirm` | j1 | `confirm_backflow` | 6478 |
| `catalog.browse` | j1 | `browse_catalog_entries` | 4420 |
| `catalog.entry.create` | j1 | `create_catalog_entry_draft` | 4776 |
| `catalog.entry.create_draft` | j1 | `create_catalog_entry_draft` | 4776 |
| `catalog.entry.publish` | j1 | `transition_catalog_entry` | 4814 |
| `catalog.entry.query` | j1 | `query_catalog_entries` | 4385 |
| `catalog.entry.reverse_draft.confirm` | j1 | `confirm_catalog_entry_reverse_draft` | 2215 |
| `catalog.entry.reverse_draft.create` | j1 | `create_catalog_entry_reverse_draft` | 2183 |
| `catalog.entry.reverse_draft.reject` | j1 | `reject_catalog_entry_reverse_draft` | 2241 |
| `catalog.entry.reverse_draft.suggest` | j1 | `suggest_catalog_entry_reverse_draft` | 2136 |
| `catalog.entry.review` | j1 | `review_catalog_entry` | 4805 |
| `catalog.entry.submit_review` | j1 | `submit_catalog_entry_review` | 4802 |
| `catalog.entry.update` | j1 | `update_catalog_entry` | 4865 |
| `catalog.entry.withdraw` | j1 | `transition_catalog_entry` | 4814 |
| `catalog.group.query` | j1 | `query_catalog_groups` | 4326 |
| `catalog.manage_entry` | j1 | `manage_catalog_entry` | 6590 |
| `catalog.model.field.query` | j1 | `query_catalog_model_fields` | 4379 |
| `catalog.model.query` | j1 | `query_catalog_models` | 4371 |
| `catalog.model.upsert` | j1 | `upsert_catalog_model` | 4696 |
| `catalog.resource.bind` | j1 | `bind_catalog_resource` | 4897 |
| `catalog.resource_view` | j1 | `get_resource` | 3281 |
| `catalog.resource.list` | j1 | `list_catalog_resources` | 0 |
| `catalog.schema.mapping.upsert` | j1 | `upsert_catalog_schema_mapping` | 4711 |
| `catalog.share_zone.query` | j1 | `query_catalog_share_zones` | 4345 |
| `credential.issue` | j1 | `issue_credential` | 8037 |
| `credential.query` | j1 | `get_credential` | 8084 |
| `credential.sample.render` | j1 | `render_credential_samples` | 0 |
| `data.search` | j1 | `search_resources` | 4143 |
| `search.intent.parse` | j1 | `parse_search_intent` | 0 |
| `delivery.access.grant` | j1 | `grant_delivery_access` | 6929 |
| `delivery.exchange.plan` | j1 | `plan_delivery_exchange` | 3861 |
| `delivery.exchange.publish` | j1 | `publish_delivery_exchange` | 3867 |
| `delivery.exchange.start` | j1 | `start_delivery_exchange` | 3864 |
| `delivery.exchange.stop` | j1 | `stop_delivery_exchange` | 3870 |
| `delivery.file.download` | j1 | `download_delivery_file` | 0 |
| `delivery.list` | j1 | `list_delivery_tasks` | 3146 |
| `delivery.status.explain` | j1 | `do_delivery_status_explain` | 0 |
| `delivery.receipt.ingest` | j1 | `ingest_delivery_receipt` | 3809 |
| `delivery.reconcile_receipt` | j1 | `reconcile_delivery_receipt` | 6959 |
| `delivery.replace_or_cancel` | j1 | `replace_or_cancel_delivery` | 2507 |
| `delivery.subscription.manage` | j1 | `manage_delivery_subscription` | 4068 |
| `delivery.trigger_recovery` | j1 | `trigger_delivery_recovery` | 6506 |
| `delivery.view` | j1 | `get_delivery_task` | 3517 |
| `direct_access.catalog.query` | j1 | `query_direct_access_catalog` | 2394 |
| `direct_access.delivery.list` | j1 | `list_direct_access_delivery` | 2424 |
| `governance.dispute_list` | j1 | `list_governance_disputes` | 3184 |
| `governance.dispute_view` | j1 | `get_dispute` | 3752 |
| `objection.case.accept` | j1 | `transition_objection_case` | 722 |
| `objection.case.assign` | j1 | `transition_objection_case` | 722 |
| `objection.case.close` | j1 | `transition_objection_case` | 722 |
| `objection.case.create` | j1 | `create_objection_case` | 703 |
| `objection.case.escalate` | j1 | `transition_objection_case` | 722 |
| `objection.case.evaluate` | j1 | `evaluate_objection_case` | 775 |
| `objection.case.query` | j1 | `query_objection_cases` | 796 |
| `objection.case.reject` | j1 | `transition_objection_case` | 722 |
| `objection.case.reply` | j1 | `reply_objection_case` | 750 |
| `objection.case.review` | j1 | `transition_objection_case` | 722 |
| `objection.case.submit` | j1 | `transition_objection_case` | 722 |
| `objection.metric.query` | j1 | `query_objection_metrics` | 812 |
| `objection.process.query` | j1 | `query_objection_process` | 804 |
| `provider.view` | j1 | `get_provider_view` | 3233 |
| `request.create` | j1 | `create_request` | 5993 |
| `request.list` | j1 | `list_requests` | 2984 |
| `demand.register` | j1 | `SupplyDemandRepository.register_demand` | supply_demand_handlers |
| `demand.phase.advance` | j1 | `SupplyDemandRepository.advance_phase` | supply_demand_handlers |
| `demand.list` | j1 | `SupplyDemandRepository.list_demands` | supply_demand_handlers |
| `request.submit` | j1 | `submit_request` | 6207 |
| `request.view` | j1 | `get_request` | 3309 |
| `require.intent.refine` | j1 | `refine_requirement_intent` | 4035 |
| `require.intent.review` | j1 | `review_requirement_intent` | 4050 |
| `require.intent.submit` | j1 | `submit_requirement_intent` | 4032 |
| `require.resource.dispatch` | j1 | `dispatch_require_resource` | 2458 |
| `require.resource.match` | j1 | `match_requirement_resource` | 4053 |
| `require.task.handoff` | j1 | `handoff_require_task` | 2490 |
| `resource.api.change` | j1 | `change_api_resource` | 4925 |
| `resource.api.policy.update` | j1 | `update_api_resource_policy` | 5047 |
| `resource.api.publish` | j1 | `transition_api_resource` | 4953 |
| `resource.api.register` | j1 | `register_api_resource` | 4910 |
| `resource.api.review` | j1 | `review_api_resource` | 4946 |
| `resource.api.revoke` | j1 | `transition_api_resource` | 4953 |
| `resource.api.submit_review` | j1 | `submit_api_resource_review` | 4943 |
| `resource.api.test` | j1 | `test_api_resource` | 4997 |
| `resource.api.withdraw` | j1 | `transition_api_resource` | 4953 |
| `resource.asset.publish` | j1 | `transition_api_resource` | 4953 |
| `resource.asset.query` | j1 | `query_resource_assets` | 4481 |
| `resource.asset.review` | j1 | `review_api_resource` | 4946 |
| `resource.asset.submit_review` | j1 | `submit_api_resource_review` | 4943 |
| `resource.manage_asset` | j1 | `manage_resource_asset` | 6628 |
| `resource.mount.file.prepare` | j1 | `prepare_file` | 0 |
| `resource.mount.table.prepare` | j1 | `prepare_table` | 0 |
| `service.rating.submit` | j1 | `submit_service_rating` | 3945 |
| `subscription.terminate` | j1 | `terminate_subscription` | 2546 |
| `summary.confirm` | j1 | `confirm_summary` | 6437 |
| `supplement.submit` | j1 | `submit_supplement` | 6392 |
| `workbench.view` | j1 | `get_workbench` | 2978 |

## J2 挂数→维数 — 38 caps

| capability_id | bucket | method_name | method_lines |
|---|---|---|---|
| `catalog.duplicate.check` | j2 | `check_catalog_duplicate` | 0 |
| `compliance.case.assign` | j2 | `transition_compliance_case` | 934 |
| `compliance.case.close` | j2 | `transition_compliance_case` | 934 |
| `compliance.case.open` | j2 | `open_compliance_case` | 903 |
| `compliance.case.query` | j2 | `query_compliance_cases` | 963 |
| `compliance.case.resolve` | j2 | `transition_compliance_case` | 934 |
| `compliance.investigate_case` | j2 | `investigate_dispute` | 6551 |
| `compliance.metric.query` | j2 | `query_compliance_metrics` | 971 |
| `compliance.rule.configure` | j2 | `configure_compliance_rule` | 878 |
| `governance.iam_overview` | j2 | `get_governance_iam_overview` | 1028 |
| `governance.policy_candidate.list` | j2 | `list_policy_mapping_candidates` | 1103 |
| `governance.policy_candidate.review` | j2 | `review_policy_mapping_candidates` | 1138 |
| `metadata.catalog_item.query` | j2 | `query_metadata_catalog_items` | 4508 |
| `metadata.gather.evidence.query` | j2 | `query_metadata_gather_evidence` | 4539 |
| `metadata.gather.evidence.upsert` | j2 | `upsert_metadata_gather_evidence` | 4737 |
| `metadata.lineage.query` | j2 | `query_metadata_lineage` | 4553 |
| `metadata.lineage.upsert` | j2 | `upsert_metadata_lineage` | 4750 |
| `metadata.schema.discover` | j2 | `discover_metadata_schema` | 2265 |
| `metadata.schema.query` | j2 | `query_metadata_schema` | 4494 |
| `metadata.schema.snapshot.upsert` | j2 | `upsert_metadata_schema_snapshot` | 4724 |
| `quality.rule.upsert` | j2 | `upsert_quality_rule` | 2304 |
| `quality.task.replay` | j2 | `replay_quality_task` | 2364 |
| `quality.task.run` | j2 | `run_quality_task` | 2335 |
| `service.publish_or_suspend` | j2 | `publish_or_suspend_service` | 6985 |
| `tenant.policy.evaluate` | j2 | `evaluate_tenant_policy` | 1379 |
| `catalog.national_ext_elem.compile` | j2 | `handler_national_ext_elem_compile` | j2/national_ext_elem.py |
| `topic.package.configure` | j2 | `configure_topic_package` | 1778 |
| `topic.package.create` | j2 | `create_topic_package` | 1767 |
| `topic.package.evidence.attach` | j2 | `attach_topic_package_evidence` | 1841 |
| `topic.package.metric.query` | j2 | `query_topic_package_metrics` | 1870 |
| `topic.package.policy.update` | j2 | `update_topic_package_policy` | 1813 |
| `topic.package.publish` | j2 | `transition_topic_package` | 1793 |
| `topic.package.query` | j2 | `query_topic_packages` | 1856 |
| `topic.package.review` | j2 | `transition_topic_package` | 1793 |
| `topic.package.submit` | j2 | `transition_topic_package` | 1793 |
| `topic.package.subscribe` | j2 | `subscribe_topic_package` | 1828 |
| `zone.list` | j2 | `list_zones` | 3172 |
| `zone.publish_topic_projection` | j2 | `publish_zone_topic_projection` | 6913 |
| `zone.view` | j2 | `get_zone` | 4106 |

## B1 后台支撑 — 42 caps

| capability_id | bucket | method_name | method_lines |
|---|---|---|---|
| `actor.projection.sync` | b1 | `sync_actor_projection` | 1568 |
| `projection.status.query` | b1 | `handler_projection_status_query` | F4 turn 1 新增 |
| `approval_flow.schema.commit` | b1 | `handler_approval_flow_schema_commit` | E3 Wave-2 F1 新增 |
| `approval_flow.nl_draft` | b1 | `handler_approval_flow_nl_draft` | E3 Wave-2 F3 新增 |
| `approval_flow.schema.promote_to_preview` | b1 | `handler_approval_flow_schema_promote_to_preview` | E3 Wave-2 F3 新增 |
| `approval_flow.schema.revert_to_draft` | b1 | `handler_approval_flow_schema_revert_to_draft` | E3 Wave-2 F3 新增 |
| `assistant.investigation_summary` | b1 | `handler_assistant_investigation_summary` | E4 F3-backend |
| `audit.event.accountability` | b1 | `handler_audit_event_accountability` | E4 F3-backend |
| `audit.event.anomaly` | b1 | `handler_audit_event_anomaly` | E4 F3-backend |
| `audit.event.query` | b1 | `handler_audit_event_query` | E4 F2 |
| `audit.event.replay` | b1 | `handler_audit_event_replay` | E4 F2 |
| `audit.event.statistics` | b1 | `handler_audit_event_statistics` | E4 F3-backend |
| `form_schema.commit` | b1 | `handler_form_schema_commit` | E3 Wave-2 F4 新增 |
| `form_schema.nl_draft` | b1 | `handler_form_schema_nl_draft` | E3 Wave-2 F5 新增 |
| `form_schema.promote_to_preview` | b1 | `handler_form_schema_promote_to_preview` | E3 Wave-2 F5 新增 |
| `form_schema.revert_to_draft` | b1 | `handler_form_schema_revert_to_draft` | E3 Wave-2 F5 新增 |
| `recommendation.rule.commit` | b1 | `handler_recommendation_rule_commit` | E3 Wave-2 F6 新增 |
| `audit.list` | b1 | `list_audit_events` | 3096 |
| `audit.replay_evidence_chain` | b1 | `replay_evidence_chain` | 3785 |
| `capability.exposure.configure` | b1 | `configure_package_exposure` | 6529 |
| `capability.package.register` | b1 | `register_capability_package` | 7096 |
| `capability.version.review` | b1 | `review_package` | 7066 |
| `capability.version.submit` | b1 | `register_package_version` | 7012 |
| `ops.catalog.quality.query` | b1 | `query_catalog_quality` | 4567 |
| `ops.catalog.quality.upsert` | b1 | `upsert_catalog_quality_evidence` | 4763 |
| `ops.catalog.statistics.query` | b1 | `query_catalog_statistics` | 4581 |
| `ops.exchange.diagnose` | b1 | `diagnose_exchange` | 3853 |
| `ops.exchange.statistics.query` | b1 | `query_exchange_statistics` | 3849 |
| `ops.gateway.heartbeat.ingest` | b1 | `ingest_gateway_heartbeat` | 4662 |
| `ops.gateway.log.anchor` | b1 | `anchor_gateway_log` | 5067 |
| `ops.service.invocation.query` | b1 | `query_service_invocations` | 4614 |
| `ops.service.report.query` | b1 | `query_service_report` | 4640 |
| `ops.shift_handover.submit` | b1 | `submit_shift_handover` | 4009 |
| `ops.ticket.close` | b1 | `close_ops_ticket` | 3992 |
| `ops.ticket.create` | b1 | `create_ops_ticket` | 3967 |
| `org.projection.sync` | b1 | `sync_org_projection` | 1545 |
| `package.apply_tenant_policy` | b1 | `apply_package_tenant_policy` | 7032 |
| `package.configure_exposure` | b1 | `configure_package_exposure` | 6529 |
| `package.exposure.matrix.query` | b1 | `handler_package_exposure_matrix_query` | F4 |
| `package.list` | b1 | `list_packages` | 3071 |
| `package.register_version` | b1 | `register_package_version` | 7012 |
| `package.review_decide` | b1 | `review_package` | 7066 |
| `package.rollback` | b1 | `handler_package_rollback` | F4 |
| `package.trust_level.update` | b1 | `handler_package_trust_level_update` | F4 |
| `package.view` | b1 | `get_package` | 4112 |
| `registry.artifact.export` | b1 | `export_registry_artifacts` | 7171 |
| `system.schema_info` | b1 | `?` | ? |
| `system.snapshot` | b1 | `snapshot` | 131 |
| `system.toggle_outage` | b1 | `toggle_outage` | 7176 |
| `tenant.capability.disable` | b1 | `disable_tenant_capability` | 7137 |
| `tenant.capability.enable` | b1 | `apply_package_tenant_policy` | 7032 |

## infra 跨系统 connector — 22 caps

| capability_id | bucket | method_name | method_lines |
|---|---|---|---|
| `adapter.cascade.consume` | infra | `record_adapter_operation` | 827 |
| `adapter.cascade.health.query` | infra | `query_adapter_health` | 981 |
| `adapter.cascade.replay` | infra | `record_adapter_operation` | 827 |
| `adapter.external.mapping.query` | infra | `query_external_mappings` | 993 |
| `adapter.health.probe` | infra | `record_adapter_operation` | 827 |
| `adapter.national.application.receive` | infra | `record_adapter_operation` | 827 |
| `adapter.national.application.reconcile` | infra | `record_adapter_operation` | 827 |
| `adapter.national.application.submit` | infra | `record_adapter_operation` | 827 |
| `adapter.national.catalog.pull` | infra | `record_adapter_operation` | 827 |
| `adapter.national.catalog.report` | infra | `record_adapter_operation` | 827 |
| `adapter.national.delivery.receipt.sync` | infra | `record_adapter_operation` | 827 |
| `adapter.national.objection.sync` | infra | `record_adapter_operation` | 827 |
| `adapter.national.resource.pull` | infra | `record_adapter_operation` | 827 |
| `adapter.national.resource.report` | infra | `record_adapter_operation` | 827 |
| `adapter.national.topic.report` | infra | `record_adapter_operation` | 827 |
| `compliance.signal.ingest` | infra | `record_adapter_operation` | 827 |
| `legacy.bsp.mapping.import` | infra | `import_legacy_bsp_mapping` | 1628 |
| `legacy.migration.status.query` | infra | `get_legacy_migration_status` | 1897 |
| `legacy.sharezone.mapping.import` | infra | `import_legacy_sharezone_mapping` | 1886 |
| `risk.event.ingest` | infra | `record_adapter_operation` | 827 |
| `security.scan.result.sync` | infra | `record_adapter_operation` | 827 |
| `standard.asset.recommend` | infra | `record_adapter_operation` | 827 |
| `platform.docs.search` | infra | `do_platform_docs_search` | infra/platform_docs.py |
| `platform.docs.read` | infra | `do_platform_docs_read` | infra/platform_docs.py |

## 总计

- J1: 96 caps
- J2: 38 caps
- B1: 42 caps
- infra: 24 caps
- 未归类: 0 caps
- **合计：209 caps**
