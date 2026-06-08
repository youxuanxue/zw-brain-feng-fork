"""Resource API serializers — resource_asset / binding / api_test_projection.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.resource_lifecycle import lifecycle_label
from zw_brain.domain.serializers._common import mask


def resource_asset_to_dict(record: Any) -> dict[str, Any]:
    return {
        "resource_code": record.resource_code,
        "resource_kind": record.resource_kind,
        "title": record.title,
        # lifecycle_status = 机器原值（前端逻辑只比对它）；lifecycle_label = 中文展示态（前端零词表）。
        "lifecycle_status": record.lifecycle_status,
        "lifecycle_label": lifecycle_label(record.lifecycle_status),
        "owner_org_id": record.owner_org_id,
        "owner_org_snapshot_json": mask(copy.deepcopy(record.owner_org_snapshot_json)),
        "region_code": record.region_code,
        "catalog_code": record.catalog_code,
        "access_policy_json": mask(copy.deepcopy(record.access_policy_json)),
        "qos_policy_json": copy.deepcopy(record.qos_policy_json),
        "source_ref": record.source_ref,
        "summary_json": mask(copy.deepcopy(record.summary_json)),
    }


def binding_to_dict(record: Any) -> dict[str, Any]:
    return {
        "binding_code": record.binding_code,
        "resource_code": record.resource_code,
        "channel_kind": record.channel_kind,
        "route_ref": record.route_ref,
        "endpoint_ref": copy.deepcopy(record.endpoint_ref),
        "schema_ref": copy.deepcopy(record.schema_ref),
        "auth_ref": record.auth_ref,
        "request_schema_json": copy.deepcopy(record.request_schema_json),
        "response_schema_json": copy.deepcopy(record.response_schema_json),
        "gateway_policy_json": copy.deepcopy(record.gateway_policy_json),
        "lifecycle_status": record.lifecycle_status,
        "source_ref": record.source_ref,
    }


def api_test_projection_to_dict(record: Any) -> dict[str, Any]:
    return {
        "test_ref": record.test_ref,
        "resource_code": record.resource_code,
        "binding_code": record.binding_code,
        "test_result": record.test_result,
        "lifecycle_status": record.lifecycle_status,
        "source_ref": record.source_ref,
        "evidence_json": copy.deepcopy(record.evidence_json),
        "tested_by": record.tested_by,
        "tested_at": record.tested_at.isoformat(),
    }
