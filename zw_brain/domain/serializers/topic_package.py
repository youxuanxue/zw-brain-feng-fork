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


# 悬挂引用诚实信号（缺陷 4 / 设计 §三.3）：ref_type=catalog_entry 的 item 若 ref_id
# 未录入 catalog_entry 主表，参照完整性不可达——复用现成 ref_status 列，派生为
# "dangling"（诚实信号，不假装 active）。这是**只读派生**，不写库（无新写入口，§9.5）；
# 所以始终与主表现状一致、无漂移。功能（补录可检索 + 详情页）已剥离回 J1 立项。
DANGLING_REF_STATUS = "dangling"


def effective_ref_status(
    ref_type: str,
    ref_id: str | None,
    stored_status: str,
    *,
    present_catalog_codes: set[str] | None,
) -> str:
    """item 的有效 ref_status：catalog_entry 引用悬挂时降级为 dangling 诚实信号。

    present_catalog_codes=None → 调用方未提供完整性上下文，原样返回（不臆断）。
    仅对 ref_type=catalog_entry 生效；其它多态 ref（resource/bs_resource…）不在本守卫。
    """
    if present_catalog_codes is None:
        return stored_status
    if ref_type == "catalog_entry" and ref_id and ref_id not in present_catalog_codes:
        return DANGLING_REF_STATUS
    return stored_status


def topic_item_to_dict(
    item: Any, *, present_catalog_codes: set[str] | None = None
) -> dict[str, Any]:
    eff_status = effective_ref_status(
        item.ref_type, item.ref_id, item.ref_status, present_catalog_codes=present_catalog_codes
    )
    return {
        "item_code": item.item_code,
        "ref_type": item.ref_type,
        "ref_id": item.ref_id,
        "ref_status": eff_status,
        # 诚实可达信号：仅在调用方提供完整性上下文时给出（None=未校验）。
        "ref_resolvable": None if present_catalog_codes is None else eff_status != DANGLING_REF_STATUS,
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
