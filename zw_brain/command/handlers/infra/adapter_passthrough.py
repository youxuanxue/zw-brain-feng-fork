"""infra `adapter.* / compliance.signal.ingest / risk.event.ingest / standard.asset.recommend /
security.scan.result.sync` handler — record_adapter_operation 物理迁出（F1 turn 3）。

17 cap 共享同一 mutation 逻辑（adapter run record + external object mapping + audit feed）。
adapter.health.probe 走 handler_health_probe（payload 预处理），其余 16 cap 走通用 handler。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.serializers import adapter as adapter_ser


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _record_adapter_operation(brain, skill_id, payload)


def handler_health_probe(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    enriched = {
        "adapter_slug": payload.get("adapter_slug", "adapter-health"),
        "operation": "health_probe",
        "direction": "inbound",
    } | payload
    return _record_adapter_operation(brain, skill_id, enriched)


def _record_adapter_operation(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        repo = brain._external_adapter_repo()
        adapter_slug, operation, direction = brain._adapter_operation_from_skill(skill_id, payload)
        idempotency_key = str(payload.get("idempotency_key") or brain._adapter_idempotency_key(skill_id, payload))
        run = repo.upsert_run_record(
            {
                "adapter_slug": adapter_slug,
                "operation": operation,
                "direction": direction,
                "source_ref": payload.get("source_ref") or payload.get("external_object_id") or payload.get("local_aggregate_id"),
                "idempotency_key": idempotency_key,
                "status": payload.get("status", "succeeded"),
                "target_count": payload.get("target_count", 1),
                "success_count": payload.get("success_count"),
                "failure_count": payload.get("failure_count", 0),
                "receipt_json": payload.get("receipt_json") or payload.get("last_receipt_json") or {"skill_id": skill_id, "actor": actor},
                "error_summary": payload.get("error_summary"),
            }
        )
        mapping = None
        if payload.get("external_object_id") or payload.get("local_aggregate_id") or payload.get("legacy_id"):
            mapping = repo.upsert_mapping(
                {
                    "external_system": payload.get("external_system") or ("cascade_down" if skill_id.startswith("adapter.cascade") else "national_platform"),
                    "direction": direction,
                    "local_aggregate_type": payload.get("local_aggregate_type") or brain._aggregate_type_from_skill(skill_id),
                    "local_aggregate_id": payload.get("local_aggregate_id") or "",
                    "legacy_table": payload.get("legacy_table"),
                    "legacy_id": payload.get("legacy_id"),
                    "external_object_type": payload.get("external_object_type") or brain._aggregate_type_from_skill(skill_id),
                    "external_object_id": payload.get("external_object_id") or payload.get("legacy_id") or idempotency_key,
                    "protocol_version": payload.get("protocol_version", "v0.55"),
                    "batch_no": payload.get("batch_no"),
                    "status": payload.get("mapping_status", "mapped"),
                    "last_receipt_json": payload.get("receipt_json") or {},
                    "extra_json": payload.get("extra_json") or {},
                }
            )
        brain._append_audit_feed(skill_id, idempotency_key, "ok", actor)
        return {
            "run": adapter_ser.adapter_run_to_dict(run),
            "mapping": adapter_ser.external_mapping_to_dict(mapping) if mapping is not None else None,
            "audit_id": audit_id,
        }

    return brain._mutate(skill_id, role, confirmed, payload, mutation)
