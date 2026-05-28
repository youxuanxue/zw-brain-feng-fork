"""Governance projection serializers — tenant / org / region / role / actor +
legacy_policy_candidate + tenant_policy.

Extracted from ``BrainService._<name>_record_to_dict`` (Phase 1.1).
"""
from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.serializers._common import mask


def tenant_projection_to_dict(item: Any) -> dict[str, Any]:
    return {
        "tenant_id": item.tenant_id,
        "tenant_name": item.tenant_name,
        "status": item.status,
        "source_ref": item.source_ref,
        "profile_json": copy.deepcopy(item.profile_json),
    }


def org_projection_to_dict(item: Any) -> dict[str, Any]:
    return {
        "org_code": item.org_code,
        "org_name": item.org_name,
        "parent_org_code": item.parent_org_code,
        "region_code": item.region_code,
        "status": item.status,
        "source_ref": item.source_ref,
        "profile_json": copy.deepcopy(item.profile_json),
    }


def region_projection_to_dict(item: Any) -> dict[str, Any]:
    return {
        "region_code": item.region_code,
        "region_name": item.region_name,
        "parent_region_code": item.parent_region_code,
        "region_level": item.region_level,
        "status": item.status,
        "source_ref": item.source_ref,
        "profile_json": copy.deepcopy(item.profile_json),
    }


def role_projection_to_dict(item: Any) -> dict[str, Any]:
    return {
        "role_code": item.role_code,
        "role_name": item.role_name,
        "status": item.status,
        "source_ref": item.source_ref,
        "profile_json": copy.deepcopy(item.profile_json),
    }


def actor_projection_to_dict(item: Any) -> dict[str, Any]:
    # display_name + profile_json may carry person names / phone / email /
    # id_card / address — mask before egress per [2026-05-06] policy.
    return mask({
        "external_actor_id": item.external_actor_id,
        "display_name": item.display_name,
        "org_code": item.org_code,
        "role_codes_json": copy.deepcopy(item.role_codes_json),
        "status": item.status,
        "source_ref": item.source_ref,
        "profile_json": copy.deepcopy(item.profile_json),
    })


def legacy_policy_candidate_to_dict(item: Any) -> dict[str, Any]:
    return {
        "legacy_system": item.legacy_system,
        "legacy_permission_ref": item.legacy_permission_ref,
        "legacy_role_ref": item.legacy_role_ref,
        "capability_id": item.capability_id,
        "surface": item.surface,
        "candidate_status": item.candidate_status,
        "evidence_json": copy.deepcopy(item.evidence_json),
    }


def tenant_policy_to_dict(item: Any) -> dict[str, Any]:
    return {
        "tenant_id": item.tenant_id,
        "package_slug": item.package_slug,
        "policy_status": item.policy_status,
        "policy_json": copy.deepcopy(item.policy_json),
    }
