"""Topic-package serializers — package / item / visibility (+ helper) /
review / evidence / metric.

Extracted from ``BrainService._<name>_record_to_dict`` and the related
``_topic_visibility_boundary`` helper (Phase 1.1).

Note: ``_topic_package_list_projection`` and ``_topic_package_detail_to_dict``
remain on BrainService — they orchestrate the repo and are aggregate views,
not record-to-dict mappers.
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.serializers._common import mask


def topic_package_to_dict(item: Any) -> dict[str, Any]:
    return mask({
        "package_code": item.package_code,
        "title": item.title,
        "scenario": item.scenario,
        "owner_org_id": item.owner_org_id,
        "owner_org_snapshot_json": copy.deepcopy(item.owner_org_snapshot_json),
        "status": item.status,
        "display_snapshot_json": copy.deepcopy(item.display_snapshot_json),
        "metric_snapshot_json": copy.deepcopy(item.metric_snapshot_json),
        "source_ref": item.source_ref,
    })


def topic_item_to_dict(item: Any) -> dict[str, Any]:
    return {
        "item_code": item.item_code,
        "ref_type": item.ref_type,
        "ref_id": item.ref_id,
        "ref_status": item.ref_status,
        "title": item.title,
        "display_order": item.display_order,
        "summary_json": copy.deepcopy(item.summary_json),
    }


def topic_visibility_boundary(item: Any) -> dict[str, Any]:
    condition = item.condition_json if isinstance(item.condition_json, dict) else {}
    return {
        "policyStatus": item.policy_status,
        "intent": item.intent,
        "surface": item.surface,
        "condition": copy.deepcopy(condition),
        "source": condition.get("source"),
        "requiresApplicationReview": item.policy_status != "approved" or item.intent not in {"view", "discover"},
    }


def topic_visibility_to_dict(item: Any) -> dict[str, Any]:
    condition = copy.deepcopy(item.condition_json)
    return {
        "visibility_code": item.visibility_code,
        "org_code": item.org_code,
        "role_code": item.role_code,
        "region_code": item.region_code,
        "surface": item.surface,
        "intent": item.intent,
        "policy_status": item.policy_status,
        "condition_json": condition,
        "source": condition.get("source") if isinstance(condition, dict) else None,
        "visible_org": item.org_code or item.role_code or item.region_code or "tenant-wide",
        "applicationBoundary": topic_visibility_boundary(item),
    }


def topic_review_to_dict(item: Any) -> dict[str, Any]:
    return {
        "action_type": item.action_type,
        "action_result": item.action_result,
        "from_status": item.from_status,
        "to_status": item.to_status,
        "reviewer_snapshot_json": copy.deepcopy(item.reviewer_snapshot_json),
        "opinion": item.opinion,
        "evidence_json": copy.deepcopy(item.evidence_json),
        "created_at": item.created_at.isoformat(),
    }


def topic_evidence_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "evidence_type": item.evidence_type,
        "title": item.title,
        "related_ref_type": item.related_ref_type,
        "related_ref_id": item.related_ref_id,
        "content_json": copy.deepcopy(item.content_json),
        "submitted_by_json": copy.deepcopy(item.submitted_by_json),
        "created_at": item.created_at.isoformat(),
    }


def topic_metric_to_dict(item: Any) -> dict[str, Any]:
    return {
        "metric_key": item.metric_key,
        "metric_value": item.metric_value,
        "metric_json": copy.deepcopy(item.metric_json),
    }
