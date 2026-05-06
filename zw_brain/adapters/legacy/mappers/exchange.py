"""Exchange mapper: dsp_require + dsp_catalog application/approval/grant tables.

Covers the application–approval–grant arc end-to-end:
    `data_require` / `data_original_require`        → ApplicationRecord
    `data_apply`                                    → ApplicationRecord (kind=apply)
    `data_apply_course`                             → ApprovalCase + ApprovalStep + ApprovalDecision
    `data_apply_authrization`                       → DeliveryTaskRecord(state=granted/revoked)

Real secrets dropped at boundary: `data_apply.app_key`, `data_apply_course.hmac`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from zw_brain.adapters.legacy._common import (
    ImportStats,
    coerce_datetime,
    coerce_int,
    coerce_time,
    finish_run,
    schema_from_dump_name,
)
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.models import (
    ApprovalCaseRecord,
    ApprovalDecisionRecord,
    ApprovalStepRecord,
    DeliveryTaskRecord,
)
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json

REQUIRE_STATUS_MAP: dict[int, str] = {
    1: "submitted",
    2: "under_review",
    3: "rejected",
    4: "under_review",
    5: "rejected",
    6: "approved",
    7: "withdrawn",
}
ORIGINAL_REQUIRE_STATUS_MAP: dict[int, str] = {
    0: "draft",
    1: "submitted",
    2: "approved",
    3: "rejected",
    4: "approved",
    5: "effective",
    6: "expired",
}
# `data_apply.status` per CREATE TABLE COMMENT (only the reasonable values are kept;
# vendor-specific tags like 2=乌鲁木齐 collapse to under_review)
APPLY_STATUS_MAP: dict[int, str] = {
    -1: "withdrawn",
    0: "submitted",
    1: "draft",
    2: "under_review",
    3: "under_review",
    6: "submitted",
    7: "rejected",
    8: "rejected",
    9: "approved",
    10: "change_pending",
    11: "approved",
    12: "rejected",
    14: "suspended",
    15: "revoked",
}

# Real secrets in data_apply
APPLY_DROP_FIELDS = {"app_key"}
# Real secret in data_apply_course
APPLY_COURSE_DROP_FIELDS = {"hmac"}

# data_apply_course.status (CREATE TABLE COMMENT): -1 删除 / 0 待处理 / 1 已处理
COURSE_STATUS_TO_STEP_STATUS: dict[int, str] = {
    0: "pending",
    1: "completed",
}
# data_apply_course.check_status (CREATE TABLE COMMENT): 0 驳回补正 / 1 审核通过 / 2 驳回
COURSE_CHECK_STATUS_TO_DECISION: dict[int, str] = {
    0: "request_correction",
    1: "approved",
    2: "rejected",
}
# data_apply_authrization.status: 0 待处理 / 1 已处理
AUTHZ_APPLY_STATUS_TO_DELIVERY_STATE: dict[int, str] = {
    -1: "withdrawn",
    0: "pending",
    1: "draft",
    6: "pending",
    7: "rejected",
    8: "rejected",
    9: "granted",
}


class ExchangeMapper:
    HANDLED_TABLES = {
        "data_require",
        "data_original_require",
        "data_apply",
        "data_apply_course",
        "data_apply_authrization",
    }
    ADAPTER_SLUG = "legacy.exchange.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.application_repo = ApplicationRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        legacy_system = legacy_system_for(schema)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                if table == "data_require":
                    self._map_data_require(row, legacy_system)
                elif table == "data_original_require":
                    self._map_data_original_require(row, legacy_system)
                elif table == "data_apply":
                    self._map_data_apply(row, legacy_system)
                elif table == "data_apply_course":
                    self._map_data_apply_course(row, legacy_system)
                elif table == "data_apply_authrization":
                    self._map_data_apply_authrization(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    def _map_data_require(self, row: dict[str, Any], legacy_system: str) -> None:
        require_id = row["require_id"]
        applicant_org_names = row.get("requireorg_names") or ""
        applicant_dept = applicant_org_names.split("|")[0].strip() or applicant_org_names or row.get("dutyorg_name") or "unknown"
        status = REQUIRE_STATUS_MAP.get(coerce_int(row.get("status")), "submitted")
        self.application_repo.upsert_from_request(
            {
                "id": require_id,
                "status": status,
                "applicant": row.get("dutyorg_name") or applicant_dept,
                "applicantDept": applicant_dept,
                "source_ref": f"{legacy_system}:data_require:{require_id}",
                "legacy_object_ref": require_id,
                "kind": "require",
                "title": row.get("require_title"),
                "content": row.get("require_content"),
                "share_type": row.get("share_type"),
                "update_cycle": row.get("update_cycle"),
                "data_source": row.get("data_source"),
                "duty_org_id": row.get("dutyorg_id"),
                "duty_region_code": row.get("dutyregion_code"),
                "predict_time": coerce_time(row.get("predict_time")),
                "create_time": coerce_time(row.get("create_time")),
                "applicant_org_names": applicant_org_names,
                "applicant_org_ids": row.get("requireorg_ids"),
                "task_id": row.get("task_id"),
                "subtask_id": row.get("subtask_id"),
                "is_resolve": row.get("is_resolve"),
                "reviewed": row.get("reviewed"),
                "require_columns": row.get("require_columns"),
                "api_info": row.get("api_info"),
                "file_info": row.get("file_info"),
                "other_info": row.get("other_info"),
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_apply(self, row: dict[str, Any], legacy_system: str) -> None:
        apply_id = row["id"]
        scrubbed = {k: v for k, v in row.items() if k not in APPLY_DROP_FIELDS}  # drop app_key (real secret)
        status = APPLY_STATUS_MAP.get(coerce_int(scrubbed.get("status")), "submitted")
        applicant_name = scrubbed.get("contact") or scrubbed.get("creator_name") or scrubbed.get("creator") or "未提供"
        applicant_dept = scrubbed.get("apply_org_name") or scrubbed.get("dept") or "unknown"
        self.application_repo.upsert_from_request(
            {
                "id": apply_id,
                "status": status,
                "applicant": applicant_name,
                "applicantDept": applicant_dept,
                "resourceId": scrubbed.get("resource_id"),
                "source_ref": f"{legacy_system}:data_apply:{apply_id}",
                "legacy_object_ref": apply_id,
                "kind": "apply",
                # business-visible sensitive — read layer applies sensitive_mask
                "contact_name": scrubbed.get("contact"),
                "contact_phone": scrubbed.get("phone"),
                "contact_email": scrubbed.get("email"),
                "use_contact_name": scrubbed.get("use_contact"),
                "use_contact_phone": scrubbed.get("use_phone"),
                "use_contact_email": scrubbed.get("use_email"),
                # routing context
                "catalog_id": scrubbed.get("cata_id"),
                "resource_name": scrubbed.get("resource_name"),
                "provider_org_id": scrubbed.get("org_id"),
                "provider_org_name": scrubbed.get("org_name"),
                "applicant_org_id": scrubbed.get("apply_org_id"),
                "applicant_org_name": scrubbed.get("apply_org_name"),
                "use_dept_id": scrubbed.get("deptid"),
                "use_dept_name": scrubbed.get("dept"),
                "use_reason": scrubbed.get("use_reason"),
                "other_reason": scrubbed.get("other_reason"),
                "use_region": scrubbed.get("use_region"),
                "use_item": scrubbed.get("use_item"),
                "system_id": scrubbed.get("system_id"),
                "system_name": scrubbed.get("system_name"),
                "system_type": scrubbed.get("system_type"),
                "is_proxy": scrubbed.get("is_proxy"),
                "service_apply_id": scrubbed.get("service_apply_id"),
                "service_type": scrubbed.get("service_type"),
                "service_times": scrubbed.get("service_times"),
                "service_most_times": scrubbed.get("service_most_times"),
                "service_times_unit": scrubbed.get("service_times_unit"),
                "service_usetime": scrubbed.get("service_usetime"),
                "service_usedays": scrubbed.get("service_usedays"),
                "resource_type": scrubbed.get("type"),
                "resource_status": scrubbed.get("resource_status"),
                "batch_id": scrubbed.get("batch_id"),
                "flow_code": scrubbed.get("flow_code"),
                "has_condition": scrubbed.get("has_condition"),
                "create_time": coerce_time(scrubbed.get("create_time")),
                "apply_basis": scrubbed.get("apply_basis"),
            },
            tenant_id=self.tenant_id,
        )

    def _map_data_original_require(self, row: dict[str, Any], legacy_system: str) -> None:
        require_id = row["id"]
        status = ORIGINAL_REQUIRE_STATUS_MAP.get(coerce_int(row.get("status")), "draft")
        applicant_dept = row.get("org_name") or "unknown"
        self.application_repo.upsert_from_request(
            {
                "id": require_id,
                "status": status,
                "applicant": row.get("creator") or applicant_dept,
                "applicantDept": applicant_dept,
                "source_ref": f"{legacy_system}:data_original_require:{require_id}",
                "legacy_object_ref": require_id,
                "kind": "original_require",
                "title": row.get("require_title"),
                "content": row.get("require_content"),
                "applicant_org_id": row.get("org_id"),
                "region_code": row.get("region_code"),
                "region_name": row.get("region_name"),
                "share_type": row.get("share_type"),
                "update_cycle": row.get("update_cycle"),
                "duty_org_id": row.get("dutyorg_id"),
                "duty_region_code": row.get("dutyregion_code"),
                "task_id": row.get("task_id"),
                "subtask_id": row.get("subtask_id"),
                "business_id": row.get("business_id"),
                "business_object": row.get("business_object"),
                "business_tag": row.get("business_tag"),
                "require_columns": row.get("require_columns"),
                "api_info": row.get("api_info"),
                "file_info": row.get("file_info"),
                "other_info": row.get("other_info"),
            },
            tenant_id=self.tenant_id,
        )

    # ------------------------------------------------------------------
    # data_apply_course → ApprovalCase + ApprovalStep + ApprovalDecision
    # ------------------------------------------------------------------

    def _map_data_apply_course(self, row: dict[str, Any], legacy_system: str) -> None:
        scrubbed = {k: v for k, v in row.items() if k not in APPLY_COURSE_DROP_FIELDS}  # drop hmac
        course_id = scrubbed["id"]
        apply_id = scrubbed.get("apply_id")
        if not apply_id or coerce_int(scrubbed.get("status")) == -1:
            return  # apply_id missing or row marked deleted in legacy
        step_status = COURSE_STATUS_TO_STEP_STATUS.get(coerce_int(scrubbed.get("status"), 0), "pending")
        decision = COURSE_CHECK_STATUS_TO_DECISION.get(coerce_int(scrubbed.get("check_status"), 1), "approved")
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            # ApprovalCase: one per application_code; create on first course row
            case = session.execute(
                select(ApprovalCaseRecord).where(
                    ApprovalCaseRecord.tenant_id == self.tenant_id,
                    ApprovalCaseRecord.application_code == apply_id,
                )
            ).scalar_one_or_none()
            if case is None:
                case = ApprovalCaseRecord(
                    tenant_id=self.tenant_id,
                    application_code=apply_id,
                    current_status=decision if step_status == "completed" else "pending_decision",
                    current_step=1,
                    decision_payload_json={"source": f"{legacy_system}:data_apply_course"},
                )
                session.add(case)
                session.flush()
            else:
                # Walk current_step forward; the latest course row dictates current_status
                case.current_step = (case.current_step or 1) + 1
                case.current_status = decision if step_status == "completed" else "pending_decision"

            # ApprovalStep — keyed by case + course id (idempotent: replace if re-imported)
            step = session.execute(
                select(ApprovalStepRecord).where(
                    ApprovalStepRecord.approval_case_id == case.id,
                    ApprovalStepRecord.step_name == (scrubbed.get("node_name") or course_id),
                )
            ).scalar_one_or_none()
            step_payload = {
                "approval_case_id": case.id,
                "step_no": case.current_step,
                "step_name": scrubbed.get("node_name") or "审核",
                "decision_mode": "single",
                "status": step_status,
                "approver_scope_json": safe_json({
                    "org_id": scrubbed.get("org_id"),
                    "org_name": scrubbed.get("org_name"),
                    "user_code": scrubbed.get("user_code"),
                    "user_name": scrubbed.get("user_name"),
                    "approve_person": scrubbed.get("approve_person"),
                    "approve_phone": scrubbed.get("approve_phone"),
                    "flow_code": scrubbed.get("flow_code"),
                    "flow_name": scrubbed.get("flow_name"),
                }),
                "started_at": coerce_datetime(scrubbed.get("create_time")),
                "completed_at": coerce_datetime(scrubbed.get("create_time")) if step_status == "completed" else None,
            }
            if step is None:
                step = ApprovalStepRecord(**step_payload)
                session.add(step)
                session.flush()
            else:
                for k, v in step_payload.items():
                    setattr(step, k, v)

            # ApprovalDecision: only if completed
            if step_status == "completed":
                existing = session.execute(
                    select(ApprovalDecisionRecord).where(ApprovalDecisionRecord.step_id == step.id)
                ).scalar_one_or_none()
                decision_payload = {
                    "step_id": step.id,
                    "decision": decision,
                    "decision_reason": scrubbed.get("opinion"),
                    "actor_snapshot_json": safe_json({
                        "user_code": scrubbed.get("user_code"),
                        "user_name": scrubbed.get("user_name"),
                        "org_id": scrubbed.get("org_id"),
                        "org_name": scrubbed.get("org_name"),
                    }),
                    "evidence_json": safe_json({
                        "course_id": course_id,
                        "attachment": scrubbed.get("attachment"),
                        "check_status": scrubbed.get("check_status"),
                    }),
                }
                if existing is None:
                    session.add(ApprovalDecisionRecord(**decision_payload))
                else:
                    for k, v in decision_payload.items():
                        setattr(existing, k, v)
            session.commit()

    # ------------------------------------------------------------------
    # data_apply_authrization → DeliveryTaskRecord (grant snapshot)
    # ------------------------------------------------------------------

    def _map_data_apply_authrization(self, row: dict[str, Any], legacy_system: str) -> None:
        authz_id = row["id"]
        apply_id = row.get("apply_id")
        if not apply_id:
            return
        delivery_state = AUTHZ_APPLY_STATUS_TO_DELIVERY_STATE.get(coerce_int(row.get("apply_status")), "pending")
        # Direct DeliveryTaskRecord upsert — keyed on delivery_code = apply_id so the
        # subscription/attempt mappers (pipelines.py) and this grant mapper share the
        # same task row when both legacy sources reference the same apply.
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            task = session.execute(
                select(DeliveryTaskRecord).where(
                    DeliveryTaskRecord.tenant_id == self.tenant_id,
                    DeliveryTaskRecord.delivery_code == apply_id,
                )
            ).scalar_one_or_none()
            grant_snapshot = safe_json({
                "authz_id": authz_id,
                "limit_day": row.get("limit_day"),
                "status": row.get("status"),
                "apply_status": row.get("apply_status"),
                "opinion": row.get("opinion"),
                "handler_code": row.get("handler_code"),
                "handler_name": row.get("handler_name"),
                "org_id": row.get("org_id"),
                "org_name": row.get("org_name"),
                "res_type": row.get("res_type"),
                "create_time": coerce_time(row.get("create_time")),
            })
            payload = {"access_grant": grant_snapshot, "kind": "apply_grant"}
            channel = row.get("res_type") or "exchange"
            if task is None:
                task = DeliveryTaskRecord(
                    tenant_id=self.tenant_id,
                    delivery_code=apply_id,
                    application_code=apply_id,
                    state=delivery_state,
                    channel=channel,
                    payload_json=payload,
                )
                session.add(task)
            else:
                # Preserve any existing payload_json keys (e.g. subscription's snapshot)
                # and overlay the grant.
                merged = {**(task.payload_json or {}), "access_grant": grant_snapshot}
                if "kind" not in merged:
                    merged["kind"] = "apply_grant"
                task.payload_json = merged
                task.state = delivery_state
                task.channel = channel
            session.commit()
