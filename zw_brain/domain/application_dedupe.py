"""Application uniqueness helpers.

Business rule: one applicant should have at most one visible application for the
same resource. Runtime creation enforces the write path; these helpers keep
legacy imports and read projections from leaking duplicate old rows.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

REQUEST_RECREATE_ALLOWED_STATUSES = frozenset(
    {"withdrawn", "revoked", "expired", "completed", "closed"}
)

_STATUS_PRIORITY = {
    "draft": 100,
    "need-fix": 95,
    "supplementing": 92,
    "summary-pending": 92,
    "pending": 90,
    "submitted": 90,
    "under_review": 88,
    "dept_approved": 85,
    "approved": 80,
    "granted": 75,
    "effective": 75,
    "change_pending": 60,
    "suspended": 50,
    "rejected": 40,
    "withdrawn": 10,
    "revoked": 10,
    "expired": 10,
    "completed": 10,
    "closed": 10,
}


def _payload(record: Any) -> dict[str, Any]:
    payload = getattr(record, "payload_json", None)
    return payload if isinstance(payload, dict) else {}


def application_is_legacy_import(record: Any) -> bool:
    payload = _payload(record)
    return bool(payload.get("source_ref") or payload.get("legacy_object_ref"))


def application_unique_key(record: Any) -> tuple[str, str] | None:
    """Return the applicant+resource uniqueness key for an application record."""
    payload = _payload(record)
    resource_id = str(payload.get("resourceId") or payload.get("resource_id") or "").strip()
    if not resource_id:
        return None

    applicant = str(payload.get("applicant") or getattr(record, "applicant_name", "") or "").strip()
    if not applicant:
        return None

    if not application_is_legacy_import(record) and payload.get("applicant"):
        return resource_id, f"actor:{applicant}"

    applicant_org = str(
        payload.get("applicant_org_code")
        or payload.get("applicant_org_id")
        or payload.get("apply_org_id")
        or payload.get("applicantDept")
        or getattr(record, "applicant_org", "")
        or ""
    ).strip()
    return resource_id, f"legacy:{applicant_org}:{applicant}"


def _parse_time(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _sort_time(record: Any) -> str:
    payload = _payload(record)
    return (
        _parse_time(payload.get("updatedAt"))
        or _parse_time(payload.get("updated_at"))
        or _parse_time(payload.get("submittedAt"))
        or _parse_time(payload.get("submitted_at"))
        or _parse_time(payload.get("create_time"))
        or _parse_time(getattr(record, "updated_at", None))
        or _parse_time(getattr(record, "created_at", None))
    )


def prefer_application_record(candidate: Any, current: Any | None) -> bool:
    """Pick the single record that should represent an applicant/resource pair."""
    if current is None:
        return True
    candidate_legacy = application_is_legacy_import(candidate)
    current_legacy = application_is_legacy_import(current)
    if candidate_legacy != current_legacy:
        return not candidate_legacy

    candidate_status = str(getattr(candidate, "status", "") or _payload(candidate).get("status") or "")
    current_status = str(getattr(current, "status", "") or _payload(current).get("status") or "")
    candidate_score = _STATUS_PRIORITY.get(candidate_status, 20)
    current_score = _STATUS_PRIORITY.get(current_status, 20)
    if candidate_score != current_score:
        return candidate_score > current_score

    candidate_time = _sort_time(candidate)
    current_time = _sort_time(current)
    if candidate_time != current_time:
        return candidate_time > current_time

    return str(getattr(candidate, "application_code", "") or "") > str(
        getattr(current, "application_code", "") or ""
    )


def request_item_sort_time(item: dict[str, Any]) -> str:
    return (
        _parse_time(item.get("updatedAt"))
        or _parse_time(item.get("updated_at"))
        or _parse_time(item.get("submittedAt"))
        or _parse_time(item.get("submitted_at"))
        or _parse_time(item.get("createdAt"))
        or _parse_time(item.get("created_at"))
        or ""
    )


def prefer_existing_request_item(
    candidate: dict[str, Any],
    current: dict[str, Any] | None,
) -> bool:
    """Pick the request dict that should represent an applicant/resource pair."""
    if current is None:
        return True
    candidate_status = str(candidate.get("status") or "")
    current_status = str(current.get("status") or "")
    candidate_score = _STATUS_PRIORITY.get(candidate_status, 20)
    current_score = _STATUS_PRIORITY.get(current_status, 20)
    if candidate_score != current_score:
        return candidate_score > current_score
    return request_item_sort_time(candidate) >= request_item_sort_time(current)


def existing_request_for_applicant(
    requests: list[dict[str, Any]],
    *,
    canonical_id: str,
    applicant_actor: str,
) -> dict[str, Any] | None:
    existing: dict[str, Any] | None = None
    for item in requests:
        if str(item.get("resourceId") or item.get("resource_id") or "") != canonical_id:
            continue
        if str(item.get("applicant") or "") != str(applicant_actor or ""):
            continue
        if str(item.get("status") or "") in REQUEST_RECREATE_ALLOWED_STATUSES:
            continue
        if prefer_existing_request_item(item, existing):
            existing = item
    return existing


def dedupe_application_records(records: Iterable[Any]) -> list[Any]:
    """Collapse same applicant+resource records into a single preferred record."""
    keyed: dict[tuple[str, str], Any] = {}
    passthrough: list[Any] = []
    for record in records:
        key = application_unique_key(record)
        if key is None:
            passthrough.append(record)
            continue
        current = keyed.get(key)
        if prefer_application_record(record, current):
            keyed[key] = record
    return passthrough + list(keyed.values())
