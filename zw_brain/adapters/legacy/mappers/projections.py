"""dsp_monitor + dsp_perform → compliance/ops projections.

Activates the M1-M6 records that alembic 0007 made room for:

  warning_message_info          → RiskEventProjectionRecord
  matter_handle / matter_manage → ComplianceCaseRecord
  warning_handle_process        → ComplianceCaseRecord (resolution side)
  warning_notice_rules          → ComplianceRuleRecord
  interface_result / product_call_result → HealthSignalProjectionRecord
  kpi_index_info                → MetricDefinitionProjectionRecord

Per legacy-import-mapping-v1.md §一.12 monitor and §一.14 perform: these are
projection-only consumers — none of them feed back into canonical state. Repeat
imports overwrite the projection rows in place via the repository's own UPSERTs
(idempotent by their canonical UNIQUE keys).
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from zw_brain.domain.repositories.compliance_ops import ComplianceOpsRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository

# warning_message_info.warning_level → severity
LEVEL_TO_SEVERITY: dict[str, str] = {
    "normal": "low",
    "serious": "high",
    "deadly": "critical",
}
# warning_message_info.status: 0 已清除, 1 未接收, 2 处理中, 3 已处理
WARNING_STATUS_TO_RESOLVED: dict[str, bool] = {
    "0": True,
    "1": False,
    "2": False,
    "3": True,
}


class MonitorMapper:
    HANDLED_TABLES = {
        "warning_message_info",
        "warning_handle_process",
        "warning_notice_rules",
        "matter_handle",
        "matter_manage",
        "interface_result",
        "product_call_result",
        "ip_connection_failure",
    }
    ADAPTER_SLUG = "legacy.monitor.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.compliance_repo = ComplianceOpsRepository()
        self.adapter_repo = ExternalAdapterRepository()
        self.legacy_repo = LegacyObjectMappingRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # Explicit dispatch — `getattr(self, handler_name)` was silently dropping
        # rows when a handler was missing, skewing stats.
        dispatch = {
            "warning_message_info": self._map_warning_message_info,
            "warning_handle_process": self._map_warning_handle_process,
            "warning_notice_rules": self._map_warning_notice_rules,
            "matter_handle": self._map_matter_handle,
            "matter_manage": self._map_matter_manage,
            "interface_result": self._map_interface_result,
            "product_call_result": self._map_product_call_result,
            "ip_connection_failure": self._map_ip_connection_failure,
        }
        # Sanity: dispatch keys must equal HANDLED_TABLES (catches drift).
        assert set(dispatch.keys()) == self.HANDLED_TABLES, "MonitorMapper dispatch / HANDLED_TABLES drift"

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                dispatch[table](row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------

    def _map_warning_message_info(self, row: dict[str, Any], legacy_system: str) -> None:
        wid = row["id"]
        self.compliance_repo.upsert_risk_event(
            {
                "event_kind": "abnormal",
                "severity": LEVEL_TO_SEVERITY.get(str(row.get("warning_level") or ""), "medium"),
                "source_system": "dsp-monitor",
                "source_ref": f"warning_message_info:{wid}",
                "target_type": str(row.get("warning_origin") or "unknown"),
                "target_ref": str(row.get("module_id") or ""),
                "detected_at": coerce_datetime(row.get("warning_time")) or datetime.now(UTC),
                "summary_json": {
                    "title": row.get("title"),
                    "content": row.get("content"),
                    "warning_sort": row.get("warning_sort"),
                    "module_name": row.get("module_name"),
                    "handle_mode": row.get("handle_mode"),
                    "handle_result": row.get("handle_result"),
                    "status": row.get("status"),
                    "work_order_id": row.get("work_order_id"),
                    "is_work_order": row.get("is_work_order"),
                },
            },
            tenant_id=self.tenant_id,
        )

    def _map_warning_notice_rules(self, row: dict[str, Any], legacy_system: str) -> None:
        rule_id = row["id"]
        self.compliance_repo.upsert_rule(
            {
                "rule_code": rule_id,
                "rule_kind": "alert_routing",
                "target_scope": str(row.get("warning_origin") or "all"),
                "title": row.get("name") or rule_id,
                "threshold_json": {
                    "warning_level": row.get("warning_level"),
                    "warning_sort": row.get("warning_sort"),
                    "method": row.get("method"),
                    "linked_items": row.get("warning_origin_linked_items"),
                    "linked_items_name": row.get("linked_items_name"),
                    "notice_roles_id": row.get("notice_roles_id"),
                    "notice_roles_name": row.get("notice_roles_name"),
                    "start_time": coerce_time(row.get("start_time")),
                    "end_time": coerce_time(row.get("end_time")),
                },
                "review_status": "pending_review",  # legacy rules don't auto-activate
                "source_ref": f"{legacy_system}:warning_notice_rules:{rule_id}",
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(legacy_system, "warning_notice_rules", rule_id, "ComplianceRuleRecord", rule_id, evidence={"name": row.get("name")})

    def _map_matter_handle(self, row: dict[str, Any], legacy_system: str) -> None:
        case_id = row["id"]
        self.compliance_repo.upsert_case(
            {
                "case_code": case_id,
                "case_kind": "operations",
                "target_type": "matter",
                "target_ref": str(row.get("matter_id") or ""),
                "severity": "medium",
                "status": "resolved" if str(row.get("status") or "") == "0" else "closed",
                "detected_summary": row.get("remark") or row.get("flow_name") or "运营事项",
                "resolved_summary": row.get("handle_result"),
                "evidence_json": {
                    "handle_way": row.get("handle_way"),
                    "handle_user": row.get("handle_user"),
                    "handle_time": coerce_time(row.get("handle_time")),
                    "creator": row.get("creator"),
                    "flow_code": row.get("flow_code"),
                },
                "source_ref": f"{legacy_system}:matter_handle:{case_id}",
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(legacy_system, "matter_handle", case_id, "ComplianceCaseRecord", case_id)

    def _map_matter_manage(self, row: dict[str, Any], legacy_system: str) -> None:
        # matter_manage has issues; we treat as detected case awaiting handle.
        case_id = row.get("id")
        if not case_id:
            return
        self.compliance_repo.upsert_case(
            {
                "case_code": str(case_id),
                "case_kind": "operations",
                "target_type": str(row.get("matter_type") or "matter"),
                "target_ref": str(row.get("id") or ""),
                "severity": "medium",
                "status": "detected",
                "detected_summary": row.get("matter_describe") or row.get("matter_name") or "运营事项",
                "evidence_json": {k: v for k, v in row.items() if k not in {"id"}},
                "source_ref": f"{legacy_system}:matter_manage:{case_id}",
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(legacy_system, "matter_manage", str(case_id), "ComplianceCaseRecord", str(case_id))

    def _map_warning_handle_process(self, row: dict[str, Any], legacy_system: str) -> None:
        # Resolution evidence — attach to existing case or create one.
        proc_id = row["id"]
        warning_id = row.get("warning_id")
        if not warning_id:
            return
        case_code = f"WARN-{warning_id}"
        self.compliance_repo.upsert_case(
            {
                "case_code": case_code,
                "case_kind": "alert_resolution",
                "target_type": "warning",
                "target_ref": str(warning_id),
                "severity": "medium",
                "status": "resolved" if row.get("resolve_time") else "remediating",
                "detected_summary": row.get("handle_describe") or "告警处理",
                "resolved_summary": row.get("handle_describe"),
                "evidence_json": {
                    "process_id": proc_id,
                    "confirm_time": coerce_time(row.get("confirm_time")),
                    "resolve_time": coerce_time(row.get("resolve_time")),
                },
                "source_ref": f"{legacy_system}:warning_handle_process:{proc_id}",
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(legacy_system, "warning_handle_process", proc_id, "ComplianceCaseRecord", case_code)

    def _map_interface_result(self, row: dict[str, Any], legacy_system: str) -> None:
        rid = row["id"]
        is_healthy = str(row.get("is_normal") or "") == "1"
        self.compliance_repo.upsert_health_signal(
            {
                "subject_kind": "service_probe",
                "subject_ref": str(row.get("service_id") or rid),
                "status": "healthy" if is_healthy else "degraded",
                "metric_json": {
                    "service_name": row.get("service_name"),
                    "ip_name": row.get("ip_name"),
                    "call_time": row.get("call_time"),
                    "task_name": row.get("task_name"),
                    "org_name": row.get("org_name"),
                    "result_num_time": row.get("result_num_time"),
                },
                "last_observed_at": coerce_datetime(row.get("create_time")),
                "source_ref": f"{legacy_system}:interface_result:{rid}",
            },
            tenant_id=self.tenant_id,
        )

    def _map_product_call_result(self, row: dict[str, Any], legacy_system: str) -> None:
        rid = row.get("id")
        if not rid:
            return
        is_correct = str(row.get("is_correct") or "") == "1"
        self.compliance_repo.upsert_health_signal(
            {
                "subject_kind": "service_call",
                "subject_ref": str(row.get("service_id") or rid),
                "status": "healthy" if is_correct else "degraded",
                "metric_json": {
                    "service_name": row.get("service_name"),
                    "gateway_ip": row.get("gateway_ip"),
                    "call_time": row.get("call_time"),
                    "task_name": row.get("task_name"),
                    "org_name": row.get("org_name"),
                    "call_batch": row.get("call_batch"),
                },
                "last_observed_at": coerce_datetime(row.get("create_time")),
                "source_ref": f"{legacy_system}:product_call_result:{rid}",
            },
            tenant_id=self.tenant_id,
        )

    # ------------------------------------------------------------------

    def _write_legacy_mapping(self, legacy_system: str, legacy_object_type: str, legacy_object_ref: str,
                              canonical_type: str, canonical_ref: str, *, evidence: dict[str, Any] | None = None) -> None:
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:{legacy_object_type}:{legacy_object_ref}",
                "legacy_system": legacy_system,
                "legacy_object_type": legacy_object_type,
                "legacy_object_ref": legacy_object_ref,
                "canonical_type": canonical_type,
                "canonical_ref": canonical_ref,
                "evidence_json": evidence or {},
            },
            tenant_id=self.tenant_id,
        )

    def _map_ip_connection_failure(self, row: dict[str, Any], legacy_system: str) -> None:
        rid = row.get("id") or ""
        self.compliance_repo.upsert_risk_event(
            {
                "event_kind": "connectivity",
                "severity": "high",
                "source_system": "dsp-monitor",
                "source_ref": f"ip_connection_failure:{rid}",
                "target_type": "service",
                "target_ref": str(row.get("service_id") or row.get("ip") or ""),
                "detected_at": coerce_time(row.get("create_time")) or datetime.now(UTC),
                "summary_json": {k: v for k, v in row.items() if k != "id"},
            },
            tenant_id=self.tenant_id,
        )


class PerformMapper:
    # Only `kpi_index_info` lands in canonical state; kpi_index_system /
    # kpi_index_calculation_rule are too narrow without a richer KPI model and
    # are intentionally not in HANDLED_TABLES (they fall through to stats.skip).
    HANDLED_TABLES = {"kpi_index_info"}
    ADAPTER_SLUG = "legacy.perform.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.compliance_repo = ComplianceOpsRepository()
        self.adapter_repo = ExternalAdapterRepository()
        self.legacy_repo = LegacyObjectMappingRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                self._map_kpi_index_info(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    def _map_kpi_index_info(self, row: dict[str, Any], legacy_system: str) -> None:
        kpi_id = row["ID"]
        method_int = coerce_int(row.get("METHOD"), 0)
        self.compliance_repo.upsert_metric_definition(
            {
                "metric_code": kpi_id,
                "title": row.get("TITLE") or kpi_id,
                "metric_kind": "score" if method_int == 0 else "manual_score",
                "target_aggregate": str(row.get("SYSTEM_CODE") or "kpi_system"),
                "dimension_json": {
                    "data_source": row.get("SOURCE"),
                    "data_requirement": row.get("DATA"),
                    "scoring_standard": row.get("STANDARD"),
                    "calculation_rule": row.get("RULE"),
                    "rule_type": row.get("RULE_TYPE"),
                    "frequency": row.get("FREQUENCY"),
                    "is_submit": row.get("IS_SUBMIT"),
                    "version": row.get("VERSION"),
                    "method": row.get("METHOD"),
                },
                "owner_org_id": row.get("CREATOR"),
                "source_ref": f"{legacy_system}:kpi_index_info:{kpi_id}",
            },
            tenant_id=self.tenant_id,
        )
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:kpi_index_info:{kpi_id}",
                "legacy_system": legacy_system,
                "legacy_object_type": "kpi_index_info",
                "legacy_object_ref": kpi_id,
                "canonical_type": "MetricDefinitionProjectionRecord",
                "canonical_ref": kpi_id,
                "evidence_json": {"title": row.get("TITLE")},
            },
            tenant_id=self.tenant_id,
        )
