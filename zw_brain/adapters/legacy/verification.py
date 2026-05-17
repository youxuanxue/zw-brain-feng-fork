from __future__ import annotations

from collections import Counter
from typing import Any

from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.compliance_ops import ComplianceOpsRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.gateway_runtime import GatewayRuntimeRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.service_invocation import ServiceInvocationMetricRepository, metric_canonical_ref
from zw_brain.domain.repositories.topic_package import TopicPackageRepository

WEAK_RESOLVED_TYPES = {"DeliveryChannelRegistry", "ExternalApplicationMapping", "capability", "anchor_outbox", "legacy_only_evidence"}


def verify_legacy_migration(*, tenant_id: str, require_zero_conflicts: bool = False) -> dict[str, Any]:
    resolvers = _canonical_ref_resolvers(tenant_id)
    mappings = LegacyObjectMappingRepository().list_mappings(tenant_id=tenant_id)
    by_type: dict[str, list[Any]] = {}
    for mapping in mappings:
        by_type.setdefault(mapping.canonical_type, []).append(mapping)

    total_unresolved = 0
    total_unknown = 0
    total_conflicted = 0
    rows = []
    for canonical_type, records in sorted(by_type.items()):
        statuses = Counter(record.mapping_status for record in records)
        conflicted = statuses.get("conflicted", 0)
        total_conflicted += conflicted
        if canonical_type in WEAK_RESOLVED_TYPES:
            rows.append(
                {
                    "canonical_type": canonical_type,
                    "mapped": len(records),
                    "resolved": len(records),
                    "unresolved": 0,
                    "conflicted": conflicted,
                    "unknown_type": False,
                    "sample_unresolved": [],
                    "mapping_statuses": dict(sorted(statuses.items())),
                }
            )
            continue
        known = resolvers.get(canonical_type)
        if known is None:
            total_unknown += len(records)
            total_unresolved += len(records)
            rows.append(
                {
                    "canonical_type": canonical_type,
                    "mapped": len(records),
                    "resolved": 0,
                    "unresolved": len(records),
                    "conflicted": conflicted,
                    "unknown_type": True,
                    "sample_unresolved": [record.canonical_ref for record in records[:3]],
                    "mapping_statuses": dict(sorted(statuses.items())),
                }
            )
            continue
        resolved = sum(1 for record in records if record.canonical_ref in known)
        unresolved = len(records) - resolved
        total_unresolved += unresolved
        rows.append(
            {
                "canonical_type": canonical_type,
                "mapped": len(records),
                "resolved": resolved,
                "unresolved": unresolved,
                "conflicted": conflicted,
                "unknown_type": False,
                "sample_unresolved": [record.canonical_ref for record in records if record.canonical_ref not in known][:3],
                "mapping_statuses": dict(sorted(statuses.items())),
            }
        )

    canonical_counts = _canonical_counts(tenant_id)
    failed = total_unresolved > 0 or total_unknown > 0 or (require_zero_conflicts and total_conflicted > 0)
    return {
        "tenant_id": tenant_id,
        "total_mappings": len(mappings),
        "total_unresolved": total_unresolved,
        "total_unknown_type": total_unknown,
        "total_conflicted": total_conflicted,
        "require_zero_conflicts": require_zero_conflicts,
        "failed": failed,
        "canonical_counts": canonical_counts,
        "by_type": rows,
    }


def _canonical_ref_resolvers(tenant_id: str) -> dict[str, set[str]]:
    catalog = CatalogRepository()
    resource_api = ResourceApiRepository()
    metadata = MetadataEvidenceRepository()
    governance = GovernanceProjectionRepository()
    compliance = ComplianceOpsRepository()
    delivery = DeliveryRepository()
    metric_repo = ServiceInvocationMetricRepository()
    gateway = GatewayRuntimeRepository()
    return {
        "OrgProjectionRecord": {item.org_code for item in governance.list_orgs(tenant_id=tenant_id)},
        "RegionProjectionRecord": {item.region_code for item in governance.list_regions(tenant_id=tenant_id)},
        "ActorProjectionRecord": {item.external_actor_id for item in governance.list_actors(tenant_id=tenant_id)},
        "RoleProjectionRecord": {item.role_code for item in governance.list_roles(tenant_id=tenant_id)},
        "catalog_model": {item.model_code for item in catalog.list_models(tenant_id=tenant_id)},
        "catalog_model_field": {f"{item.model_code}:{item.field_code}" for item in catalog.list_model_fields_all(tenant_id=tenant_id)},
        "catalog_entry": {item.catalog_code for item in catalog.list_entries(tenant_id=tenant_id)},
        "catalog_item": {item.item_code for item in catalog.list_items(tenant_id=tenant_id)},
        "resource_asset": {item.resource_code for item in resource_api.list_assets(tenant_id=tenant_id)},
        "resource_channel_binding": {item.binding_code for item in resource_api.list_bindings(tenant_id=tenant_id)},
        "resource_schema_mapping": {item.mapping_code for item in metadata.list_schema_mappings(tenant_id=tenant_id)},
        "resource_api_test_projection": {item.test_ref for item in resource_api.list_test_projections(tenant_id=tenant_id)},
        "resource_schema_snapshot": {item.snapshot_ref for item in metadata.list_schema_snapshots(tenant_id=tenant_id)},
        "metadata_gather_evidence_projection": {item.gather_task_ref for item in metadata.list_gather_evidence(tenant_id=tenant_id)},
        "lineage_relation_projection": {item.relation_ref for item in metadata.list_lineage_relations(tenant_id=tenant_id)},
        "quality_evidence_projection": {item.quality_ref for item in metadata.list_quality_evidence(tenant_id=tenant_id)},
        "application_record": {item.application_code for item in ApplicationRepository().list_records(tenant_id=tenant_id)},
        "approval_step": _approval_step_refs(tenant_id),
        "approval_decision": _approval_decision_refs(tenant_id),
        "ObjectionCaseRecord": {item.id for item in ObjectionRepository().list_cases(tenant_id=tenant_id)},
        "TopicPackageRecord": {item.package_code for item in TopicPackageRepository().list_packages(tenant_id=tenant_id)},
        "TopicPackageVisibilityRecord": _topic_package_visibility_refs(tenant_id),
        "TopicPackageItemRecord": _topic_package_item_refs(tenant_id),
        "DeliveryTaskRecord": {item.delivery_code for item in delivery.list_tasks(tenant_id=tenant_id)},
        "DeliveryAttemptRecord": {item.attempt_code for item in delivery.list_attempts(tenant_id=tenant_id)},
        "ComplianceCaseRecord": {item.case_code for item in compliance.list_cases(tenant_id=tenant_id)},
        "ComplianceRuleRecord": {item.rule_code for item in compliance.list_rules(tenant_id=tenant_id)},
        "MetricDefinitionProjectionRecord": {item.metric_code for item in compliance.list_metric_definitions(tenant_id=tenant_id)},
        "gateway_runtime_status_projection": {item.gateway_instance_id for item in gateway.list_statuses(tenant_id=tenant_id)},
        "service_invocation_metric_projection": {
            metric_canonical_ref(
                metric_scope=item.metric_scope,
                resource_code=item.resource_code,
                capability_id=item.capability_id,
                provider_org_id=item.provider_org_id,
                consumer_org_id=item.consumer_org_id,
                provider_region_code=item.provider_region_code,
                consumer_region_code=item.consumer_region_code,
                bucket_granularity=item.bucket_granularity,
                time_bucket=item.time_bucket,
            )
            for item in metric_repo.list_metrics(tenant_id=tenant_id)
        },
    }


def _topic_package_visibility_refs(tenant_id: str) -> set[str]:
    repo = TopicPackageRepository()
    refs: set[str] = set()
    for package in repo.list_packages(tenant_id=tenant_id):
        refs.update(f"{package.package_code}:{item.visibility_code}" for item in repo.list_visibility(package.package_code, tenant_id=tenant_id))
    return refs


def _topic_package_item_refs(tenant_id: str) -> set[str]:
    repo = TopicPackageRepository()
    refs: set[str] = set()
    for package in repo.list_packages(tenant_id=tenant_id):
        refs.update(f"{package.package_code}:{item.item_code}" for item in repo.list_items(package.package_code, tenant_id=tenant_id))
    return refs


def _approval_step_refs(tenant_id: str) -> set[str]:
    from sqlalchemy import select

    from zw_brain.domain.models import ApprovalCaseRecord, ApprovalStepRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        tenant_case_ids = select(ApprovalCaseRecord.id).where(ApprovalCaseRecord.tenant_id == tenant_id)
        return {
            item.id
            for item in session.execute(
                select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id.in_(tenant_case_ids))
            ).scalars()
        }


def _approval_decision_refs(tenant_id: str) -> set[str]:
    from sqlalchemy import select

    from zw_brain.domain.models import ApprovalCaseRecord, ApprovalDecisionRecord, ApprovalStepRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        tenant_case_ids = select(ApprovalCaseRecord.id).where(ApprovalCaseRecord.tenant_id == tenant_id)
        tenant_step_ids = select(ApprovalStepRecord.id).where(ApprovalStepRecord.approval_case_id.in_(tenant_case_ids))
        return {
            item.id
            for item in session.execute(
                select(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id.in_(tenant_step_ids))
            ).scalars()
        }


def _canonical_counts(tenant_id: str) -> dict[str, int]:
    from sqlalchemy import select

    from zw_brain.domain.models import ApprovalCaseRecord, ApprovalDecisionRecord, ApprovalStepRecord
    from zw_brain.shared.db import create_session_factory

    catalog = CatalogRepository()
    resource_api = ResourceApiRepository()
    metadata = MetadataEvidenceRepository()
    delivery = DeliveryRepository()
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        tenant_case_ids = select(ApprovalCaseRecord.id).where(ApprovalCaseRecord.tenant_id == tenant_id)
        approval_case_count = len(
            list(
                session.execute(
                    select(ApprovalCaseRecord).where(ApprovalCaseRecord.tenant_id == tenant_id)
                ).scalars()
            )
        )
        approval_steps = list(
            session.execute(
                select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id.in_(tenant_case_ids))
            ).scalars()
        )
        approval_decision_count = len(
            list(
                session.execute(
                    select(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id.in_([item.id for item in approval_steps]))
                ).scalars()
            )
        )
    return {
        "catalog_model": len(catalog.list_models(tenant_id=tenant_id)),
        "catalog_model_field": len(catalog.list_model_fields_all(tenant_id=tenant_id)),
        "catalog_entry": len(catalog.list_entries(tenant_id=tenant_id)),
        "catalog_item": len(catalog.list_items(tenant_id=tenant_id)),
        "resource_asset": len(resource_api.list_assets(tenant_id=tenant_id)),
        "resource_channel_binding": len(resource_api.list_bindings(tenant_id=tenant_id)),
        "resource_schema_mapping": len(metadata.list_schema_mappings(tenant_id=tenant_id)),
        "resource_schema_snapshot": len(metadata.list_schema_snapshots(tenant_id=tenant_id)),
        "metadata_gather_evidence_projection": len(metadata.list_gather_evidence(tenant_id=tenant_id)),
        "lineage_relation_projection": len(metadata.list_lineage_relations(tenant_id=tenant_id)),
        "quality_evidence_projection": len(metadata.list_quality_evidence(tenant_id=tenant_id)),
        "application_record": len(ApplicationRepository().list_records(tenant_id=tenant_id)),
        "approval_case": approval_case_count,
        "approval_step": len(approval_steps),
        "approval_decision": approval_decision_count,
        "delivery_task": len(delivery.list_tasks(tenant_id=tenant_id)),
    }
