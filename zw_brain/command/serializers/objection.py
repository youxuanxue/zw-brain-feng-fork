"""Objection serializers — case / process / evidence / evaluation.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
``case_to_dict`` was ``_objection_record_to_dict``; renamed for namespace
clarity (each aggregate's evidence serializer lives in its own module).
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.command.serializers._common import mask


def case_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "objection_kind": item.objection_kind,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "related_application_id": item.related_application_id,
        "title": item.title,
        "complainant_org_id": item.complainant_org_id,
        "provider_org_id": item.provider_org_id,
        "basis_text": item.basis_text,
        "expected_result": item.expected_result,
        "status": item.status,
        "resolved_summary": item.resolved_summary,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "closed_at": item.closed_at.isoformat() if item.closed_at else None,
    }


def process_to_dict(item: Any) -> dict[str, Any]:
    # handler_snapshot_json may carry handler_name + handler_phone — mask.
    return mask({
        "id": item.id,
        "objection_id": item.objection_id,
        "node_name": item.node_name,
        "handler_org_id": item.handler_org_id,
        "handler_snapshot_json": copy.deepcopy(item.handler_snapshot_json),
        "action_type": item.action_type,
        "action_result": item.action_result,
        "opinion": item.opinion,
        "created_at": item.created_at.isoformat(),
    })


def evidence_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "objection_id": item.objection_id,
        "evidence_type": item.evidence_type,
        "content_json": copy.deepcopy(item.content_json),
        "submitted_by_json": copy.deepcopy(item.submitted_by_json),
        "created_at": item.created_at.isoformat(),
    }


def evaluation_to_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "objection_id": item.objection_id,
        "evaluator_snapshot_json": copy.deepcopy(item.evaluator_snapshot_json),
        "solved_flag": item.solved_flag,
        "overall_score": item.overall_score,
        "timeliness_score": item.timeliness_score,
        "result_score": item.result_score,
        "comment": item.comment,
    }
