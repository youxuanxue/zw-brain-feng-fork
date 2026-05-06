"""dsp_pipelines → DeliveryTask + DeliverySubscription + DeliveryAttempt.

Steps 6-7 of the bridging chain. Each `subscribe_job` becomes one DeliveryTask
(state machine entry point) plus one DeliverySubscription (recurring schedule);
each `exchange_executor` row attaches as a DeliveryAttempt, recording the executor
pipeline that ran the exchange.

`exchange_pipelines` rows are channel metadata, not delivery instances — we keep
them as legacy_object_mapping evidence so future lookups can resolve a pipeline_id
back to its registry entry without inflating the canonical delivery aggregate.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from zw_brain.adapters.legacy._common import (
    ImportStats,
    coerce_int,
    coerce_time,
    finish_run,
    schema_from_dump_name,
)
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.models import DeliveryTaskRecord
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json

# subscribe_job.job_status (CREATE TABLE COMMENT): 0 草稿 / 1 待启动 / 2 已启动 / 3 已停止
JOB_STATUS_TO_STATE: dict[int, str] = {
    0: "draft",
    1: "pending",
    2: "running",
    3: "stopped",
}
# subscribe_job.job_type: 0=一次性 1=周期性
JOB_TYPE_TO_CHANNEL: dict[str, str] = {
    "0": "one_shot_exchange",
    "1": "recurring_exchange",
}


class PipelinesMapper:
    HANDLED_TABLES = {
        "subscribe_job",
        "exchange_executor",
        "exchange_pipelines",
    }
    ADAPTER_SLUG = "legacy.pipelines.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.delivery_repo = DeliveryRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

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
                if table == "subscribe_job":
                    self._map_subscribe_job(row, legacy_system)
                elif table == "exchange_executor":
                    self._map_exchange_executor(row, legacy_system)
                elif table == "exchange_pipelines":
                    self._map_exchange_pipelines(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------

    def _map_subscribe_job(self, row: dict[str, Any], legacy_system: str) -> None:
        sub_id = row["subscribe_id"]
        state = JOB_STATUS_TO_STATE.get(coerce_int(row.get("job_status"), 0), "draft")
        channel = JOB_TYPE_TO_CHANNEL.get(str(row.get("job_type") or ""), "exchange")
        # Direct DeliveryTaskRecord upsert — bypasses upsert_from_delivery which
        # auto-creates a DeliveryReceipt; legacy data has no equivalent receipt yet.
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(DeliveryTaskRecord).where(
                    DeliveryTaskRecord.tenant_id == self.tenant_id,
                    DeliveryTaskRecord.delivery_code == sub_id,
                )
            ).scalar_one_or_none()
            payload = safe_json({
                "subscribe_name": row.get("subscribe_name"),
                "subscribe_desc": row.get("subscribe_desc"),
                "job_type": row.get("job_type"),
                "applicant_org_code": row.get("org_code"),
                "applicant_org_name": row.get("org_name"),
                "provide_org_name": row.get("provide_org_name"),
                "region_code": row.get("region_code"),
                "resource_code": row.get("resource_id"),
                "resource_name": row.get("resource_name"),
                "resource_type": row.get("resource_type"),
                "catalog_code": row.get("cata_id"),
                "catalog_title": row.get("cata_title"),
                "user_id": row.get("user_id"),
                "create_time": coerce_time(row.get("create_time")),
                "update_time": coerce_time(row.get("update_time")),
            })
            if record is None:
                record = DeliveryTaskRecord(
                    tenant_id=self.tenant_id,
                    delivery_code=sub_id,
                    application_code=row.get("apply_id") or "",
                    state=state,
                    channel=channel,
                    payload_json=payload,
                )
                session.add(record)
            else:
                record.application_code = row.get("apply_id") or record.application_code
                record.state = state
                record.channel = channel
                record.payload_json = payload
            session.commit()

        # Subscription row (recurring schedule on top of the task)
        self.delivery_repo.upsert_subscription(
            {
                "subscription_code": sub_id,
                "delivery_code": sub_id,
                "resource_code": row.get("resource_id"),
                "status": state,
                "schedule_ref_json": {
                    "job_type": row.get("job_type"),
                    "channel": channel,
                },
                "policy_snapshot_json": {
                    "applicant_org_code": row.get("org_code"),
                    "provide_org_name": row.get("provide_org_name"),
                    "region_code": row.get("region_code"),
                },
                "legacy_status_snapshot_json": {
                    "job_status": row.get("job_status"),
                    "is_del": row.get("is_del"),
                },
            },
            tenant_id=self.tenant_id,
        )

        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="subscribe_job",
            legacy_object_ref=sub_id,
            canonical_type="DeliveryTaskRecord",
            canonical_ref=sub_id,
            evidence={
                "name": row.get("subscribe_name"),
                "apply_id": row.get("apply_id"),
                "resource_id": row.get("resource_id"),
            },
        )

    def _map_exchange_executor(self, row: dict[str, Any], legacy_system: str) -> None:
        executor_id = row["executor_id"]
        obj_id = row.get("obj_id")
        if not obj_id or coerce_int(row.get("obj_type")) != 1:
            # obj_type != 1 means non-subscription executor (e.g. ad-hoc) — skip
            return
        self.delivery_repo.upsert_attempt(
            {
                "attempt_code": executor_id,
                "delivery_code": obj_id,
                "subscription_code": obj_id,
                "attempt_kind": "exchange",
                "state": "completed",  # legacy executor row presence implies executed
                "executor_ref": row.get("executor_pipeline_id"),
                "payload_json": {
                    "executor_code": row.get("executor_code"),
                    "executor_pipeline_name": row.get("executor_pipeline_name"),
                    "executor_etl": row.get("executor_etl"),
                    "executor_param": row.get("executor_param"),
                },
            },
            tenant_id=self.tenant_id,
        )
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="exchange_executor",
            legacy_object_ref=executor_id,
            canonical_type="DeliveryAttemptRecord",
            canonical_ref=executor_id,
            evidence={"obj_id": obj_id, "pipeline_id": row.get("executor_pipeline_id")},
        )

    def _map_exchange_pipelines(self, row: dict[str, Any], legacy_system: str) -> None:
        # Channel definitions are not standalone canonical records; we just register
        # them in legacy_object_mapping so DeliveryAttempt.executor_ref can resolve.
        pipeline_id = row["pipeline_id"]
        self._write_legacy_mapping(
            legacy_system=legacy_system,
            legacy_object_type="exchange_pipelines",
            legacy_object_ref=pipeline_id,
            canonical_type="DeliveryChannelRegistry",
            canonical_ref=pipeline_id,
            evidence={
                "pipeline_name": row.get("pipeline_name"),
                "type_code": row.get("type_code"),
                "org_code": row.get("org_code"),
                "region_code": row.get("region_code"),
                "connect_status": row.get("connect_status"),
            },
        )

    # ------------------------------------------------------------------

    def _write_legacy_mapping(
        self,
        *,
        legacy_system: str,
        legacy_object_type: str,
        legacy_object_ref: str,
        canonical_type: str,
        canonical_ref: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
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
