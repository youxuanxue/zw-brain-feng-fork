"""Catalog serializers — model / model_field / entry.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
``_catalog_record_to_card_dict`` stays on BrainService (depends on multiple
helpers + ``_now_date``).
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.serializers._common import mask


def catalog_model_to_dict(record: Any) -> dict[str, Any]:
    return {
        "model_code": record.model_code,
        "title": record.title,
        "status": record.status,
        "owner_org_id": record.owner_org_id,
        "model_schema_json": copy.deepcopy(record.model_schema_json),
        "source_ref": record.source_ref,
    }


def catalog_model_field_to_dict(record: Any) -> dict[str, Any]:
    return {
        "model_code": record.model_code,
        "field_code": record.field_code,
        "title": record.title,
        "data_type": record.data_type,
        "sensitive_level": record.sensitive_level,
        "field_policy_json": copy.deepcopy(record.field_policy_json),
        "display_order": record.display_order,
        "source_ref": record.source_ref,
    }


def catalog_entry_to_dict(record: Any) -> dict[str, Any]:
    return {
        "catalog_code": record.catalog_code,
        "title": record.title,
        "lifecycle_status": record.lifecycle_status,
        "owner_org_id": record.owner_org_id,
        "region_code": record.region_code,
        "summary_json": mask(copy.deepcopy(record.summary_json)),
    }
