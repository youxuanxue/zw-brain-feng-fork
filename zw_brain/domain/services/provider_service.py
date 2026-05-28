"""ProviderService — provider resource asset lifecycle + diagnostics.

Owns: provider primary resource id, provider focus delivery selection,
provider manage payload normalization, resource asset enrichment with
bindings / mappings / snapshots / evidence, provider asset diagnostics,
resource transition, field evidence completion, binding confirmation,
external execution request.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.errors import AccessDeniedError, BrainServiceError, NotFoundError
from zw_brain.domain.serializers import delivery as delivery_ser
from zw_brain.domain.serializers import metadata as metadata_ser
from zw_brain.domain.serializers import quality as quality_ser
from zw_brain.domain.serializers import resource_api as resource_api_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sanitization import safe_json

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


@dataclass(frozen=True)
class ProviderService:
    """Provider resource asset lifecycle + diagnostics (P5 provider)."""

    brain: BrainService

    def primary_resource_id(self) -> str | None:
        """Resolve provider's primary resource id from snapshot."""
        provider = self.brain._snapshot.get("provider", {})
        resources = provider.get("resources", []) if isinstance(provider, dict) else []
        for item in resources:
            if isinstance(item, dict) and item.get("id"):
                return str(item["id"])
        return None

    def find_api_resource(self, resource_code: str) -> dict[str, Any] | None:
        """Lookup an API resource by resource_code.

        Action E: lifted from ``BrainService._find_api_resource``. Returns a
        deepcopy of the in-memory snapshot fallback or a freshly-serialized
        dict for DB-backed lookups, so mutations on the returned dict do
        NOT propagate to the live snapshot.
        """
        store = self.brain._state_store.database_store
        if store is None:
            item = next(
                (
                    item for item in self.brain._snapshot.get("api_resources", [])
                    if item["resource_code"] == resource_code
                ),
                None,
            )
            return copy.deepcopy(item) if item is not None else None
        record = store.resource_api_repo.get_asset(resource_code)
        return resource_api_ser.resource_asset_to_dict(record) if record is not None else None

    def focus_delivery(self) -> dict[str, Any]:
        """Pick the focus delivery task (backflow candidates) for provider summary."""
        tasks = self.brain.list_delivery_tasks()
        for item in tasks:
            backflow = item.get("backflow", {}) if isinstance(item, dict) else {}
            if isinstance(backflow, dict) and backflow.get("candidateFields"):
                return self.brain.get_delivery_task(item["id"])
        if tasks:
            return self.brain.get_delivery_task(tasks[0]["id"])
        return {}

    def manage_payload(
        self, resource_id: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize resource.manage_asset payload by action kind."""
        return {
            "resource_id": resource_id,
            "action": action,
            "tenant_id": payload.get("tenant_id", _DEFAULT_TENANT_ID),
            "target_ref": resource_id,
            "field_evidence": safe_json(payload.get("field_evidence") or {}),
            "binding_confirmations": safe_json(payload.get("binding_confirmations") or []),
            "external_execution": safe_json(payload.get("external_execution") or {}),
        } | ({"role": payload["role"]} if "role" in payload else {})

    def enrich_resource_asset(self, item: dict[str, Any], store: Any) -> dict[str, Any]:
        """Enrich a provider resource asset with bindings/mappings/snapshots/quality."""
        resource_code = str(item["resource_code"])
        bindings = [
            resource_api_ser.binding_to_dict(record)
            for record in store.resource_api_repo.list_bindings(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        mappings = store.metadata_evidence_repo.list_schema_mappings(
            resource_code=resource_code,
            include_inactive=True,
            tenant_id=_DEFAULT_TENANT_ID,
        )
        schema_snapshots = [
            metadata_ser.schema_snapshot_to_dict(record)
            for record in store.metadata_evidence_repo.list_schema_snapshots(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        gather_evidence = [
            metadata_ser.gather_evidence_to_dict(record)
            for record in store.metadata_evidence_repo.list_gather_evidence(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        lineage = [
            metadata_ser.lineage_to_dict(record)
            for record in store.metadata_evidence_repo.list_lineage_relations(resource_code=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        quality = [
            quality_ser.quality_to_dict(record)
            for record in store.metadata_evidence_repo.list_quality_evidence(target_type="resource_asset", target_ref=resource_code, tenant_id=_DEFAULT_TENANT_ID)
        ]
        attempts = [
            delivery_ser.delivery_attempt_to_dict(record)
            for record in store.delivery_repo.list_attempts(delivery_code=f"provider-external:{resource_code}", tenant_id=_DEFAULT_TENANT_ID)
        ]
        execution_evidence = [
            delivery_ser.delivery_evidence_to_dict(record)
            for record in store.delivery_repo.list_execution_evidence(delivery_code=f"provider-external:{resource_code}", tenant_id=_DEFAULT_TENANT_ID)
        ]
        legacy_mappings = [
            {
                "legacy_system": record.legacy_system,
                "legacy_object_type": record.legacy_object_type,
                "legacy_object_ref": record.legacy_object_ref,
                "canonical_type": record.canonical_type,
                "canonical_ref": record.canonical_ref,
                "mapping_status": record.mapping_status,
                "source_ref": record.source_ref,
            }
            for record in store.legacy_mapping_repo.list_mappings(tenant_id=_DEFAULT_TENANT_ID, canonical_ref=resource_code)
        ]
        diagnostics = self.brain._mapping_diagnostics(mappings, store=store)
        return item | {
            "channel_bindings": bindings,
            "schema_snapshots": schema_snapshots,
            "schema_mappings": diagnostics["items"],
            "mapping_summary": diagnostics["summary"],
            "gather_evidence": gather_evidence,
            "lineage_evidence": lineage,
            "quality_evidence": quality,
            "external_execution_tasks": attempts,
            "external_execution_receipts": execution_evidence,
            "legacy_object_mappings": legacy_mappings,
            "provider_diagnostics": self.asset_diagnostics(item, bindings, diagnostics["summary"], schema_snapshots),
        }

    def asset_diagnostics(
        self,
        item: dict[str, Any],
        bindings: list[dict[str, Any]],
        mapping_summary: dict[str, Any],
        schema_snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Provider asset readiness diagnostics for the share lifecycle."""
        issues: list[dict[str, str]] = []
        if not bindings:
            issues.append({"stage": "channel", "reason": "missing_channel_binding", "detail": "resource has no channel binding"})
        if mapping_summary.get("diagnosis") != "ok":
            issues.append({"stage": "schema_mapping", "reason": str(mapping_summary.get("diagnosis")), "detail": "catalog item to resource field mapping needs attention"})
        if not schema_snapshots:
            issues.append({"stage": "schema_snapshot", "reason": "missing_schema_snapshot", "detail": "resource has no schema snapshot evidence"})
        if item.get("lifecycle_status") not in {"active", "approved_pending_publish", "pending_review"}:
            issues.append({"stage": "lifecycle", "reason": "not_ready_for_share", "detail": f"resource lifecycle is {item.get('lifecycle_status')}"})
        return {"ok": not issues, "issues": issues}

    def transition_resource(
        self, resource_id: str, status: str, actor: str, audit_id: str
    ) -> dict[str, Any]:
        """Transition a provider resource asset to a new lifecycle status."""
        from zw_brain.shared import clock  # noqa: PLC0415

        store = self.brain._state_store.database_store
        record = store.resource_api_repo.transition_asset(resource_id, status, tenant_id=_DEFAULT_TENANT_ID) if store is not None else None
        if store is None:
            resource = self.find_api_resource(resource_id)
            if resource is None:
                snapshot_resource = next((item for item in self.brain._snapshot.get("provider", {}).get("resources", []) if item.get("id") == resource_id), None)
                if snapshot_resource is None:
                    raise NotFoundError(resource_id)
                resource = {
                    "resource_code": resource_id,
                    "title": snapshot_resource.get("name", resource_id),
                    "resource_kind": "dataset",
                    "lifecycle_status": status,
                    "source_ref": snapshot_resource.get("source_ref") or f"provider:resource:{resource_id}",
                    "summary_json": snapshot_resource,
                }
            resource["lifecycle_status"] = status
            resource["updated_at"] = clock.now_datetime()
            result = self.brain._upsert_api_resource(resource)
        else:
            if record is None:
                snapshot_resource = next((item for item in self.brain._snapshot.get("provider", {}).get("resources", []) if item.get("id") == resource_id), None)
                if snapshot_resource is None:
                    raise NotFoundError(resource_id)
                record = store.resource_api_repo.upsert_asset(
                    {
                        "resource_code": resource_id,
                        "title": snapshot_resource.get("name", resource_id),
                        "resource_kind": "dataset",
                        "lifecycle_status": status,
                        "owner_org_id": snapshot_resource.get("owner_org_id"),
                        "source_ref": snapshot_resource.get("source_ref") or f"provider:resource:{resource_id}",
                        "legacy_object_ref": snapshot_resource.get("legacy_object_ref") or resource_id,
                        "summary_json": snapshot_resource,
                    },
                    tenant_id=_DEFAULT_TENANT_ID,
                )
            store.approval_repo.upsert_api_resource_lifecycle(
                resource_id,
                status,
                actor=actor,
                skill_id="resource.manage_asset",
                audit_id=audit_id,
                decision="return" if status in {"draft", "suspended"} else None,
                tenant_id=_DEFAULT_TENANT_ID,
            )
            result = resource_api_ser.resource_asset_to_dict(record)
        return {"resource_id": resource_id, "lifecycle_status": status, "asset": result, "result": "published" if status == "active" else "suspended"}

    def complete_field_evidence(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        """Confirm field evidence for resource asset; sync schema snapshots."""
        field_evidence = safe_json(payload.get("field_evidence") or {})
        if not field_evidence:
            raise BrainServiceError("field_evidence is required")
        store = self.brain._state_store.database_store
        resource = self.find_api_resource(resource_id)
        if resource is None:
            raise NotFoundError(resource_id)
        summary = copy.deepcopy(resource.get("summary_json") or {})
        existing_evidence = copy.deepcopy(summary.get("field_evidence") or {})
        existing_evidence.update(field_evidence)
        summary["field_evidence"] = existing_evidence
        summary["field_evidence_confirmed_by"] = actor
        summary["field_evidence_audit_ref"] = audit_id
        updated_resource = self.brain._upsert_api_resource({**resource, "summary_json": summary})
        snapshot_refs: list[str] = []
        if store is not None:
            for field_ref, evidence in field_evidence.items():
                evidence_payload = evidence if isinstance(evidence, dict) else {"value": evidence}
                snapshot = store.metadata_evidence_repo.upsert_schema_snapshot(
                    {
                        "snapshot_ref": f"{resource_id}:provider-field:{field_ref}",
                        "resource_code": resource_id,
                        "binding_code": payload.get("binding_code"),
                        "schema_json": {
                            "field_ref": field_ref,
                            "name_cn": evidence_payload.get("name_cn") or evidence_payload.get("title"),
                            "data_format": evidence_payload.get("data_format") or evidence_payload.get("format"),
                            "length": evidence_payload.get("length"),
                            "sensitive_level": evidence_payload.get("sensitive_level"),
                            "masking_policy": evidence_payload.get("masking_policy") or evidence_payload.get("mask_rule"),
                            "source_note": evidence_payload.get("source_note") or evidence_payload.get("source"),
                            "provider_confirmed_by": actor,
                            "provider_audit_ref": audit_id,
                        },
                        "source_ref": f"resource.manage_asset:field_evidence:{audit_id}:{field_ref}",
                        "legacy_object_ref": field_ref,
                    },
                    tenant_id=_DEFAULT_TENANT_ID,
                )
                snapshot_refs.append(snapshot.snapshot_ref)
        return {
            "resource_id": resource_id,
            "lifecycle_status": updated_resource.get("lifecycle_status"),
            "field_evidence_count": len(field_evidence),
            "schema_snapshot_refs": snapshot_refs,
        }

    def confirm_field_binding(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        """Confirm field bindings (catalog item ↔ resource column) for an asset."""
        confirmations = payload.get("binding_confirmations") or []
        if not isinstance(confirmations, list) or not confirmations:
            raise BrainServiceError("binding_confirmations is required")
        store = self.brain._state_store.database_store
        if store is None:
            raise BrainServiceError("database store is required for provider binding confirmation")
        if self.find_api_resource(resource_id) is None:
            raise NotFoundError(resource_id)
        mapping_codes: list[str] = []
        for confirmation in confirmations:
            if not isinstance(confirmation, dict):
                raise BrainServiceError("binding confirmation must be an object")
            if str(confirmation.get("resource_code") or resource_id) != resource_id:
                raise AccessDeniedError("binding confirmation resource mismatch")
            mapping = store.metadata_evidence_repo.upsert_schema_mapping(
                {
                    **confirmation,
                    "resource_code": resource_id,
                    "confidence_level": confirmation.get("confidence_level", "confirmed"),
                    "status": confirmation.get("status", "active"),
                    "evidence_ref": confirmation.get("evidence_ref") or audit_id,
                    "source_ref": confirmation.get("source_ref") or f"resource.manage_asset:binding_confirmation:{audit_id}",
                    "legacy_object_ref": confirmation.get("legacy_object_ref") or confirmation.get("mapping_code"),
                    "confirmed_by": actor,
                },
                tenant_id=_DEFAULT_TENANT_ID,
            )
            mapping_codes.append(mapping.mapping_code)
        return {"resource_id": resource_id, "confirmed_mapping_codes": mapping_codes, "binding_confirmation_count": len(mapping_codes)}

    def request_external_execution(
        self,
        resource_id: str,
        payload: dict[str, Any],
        actor: str,
        audit_id: str,
    ) -> dict[str, Any]:
        """Request external execution (metadata_gather / schema_structure / exchange)."""
        execution = safe_json(payload.get("external_execution") or {})
        execution_kind = str(execution.get("execution_kind") or execution.get("kind") or "schema_structure")
        if execution_kind not in {"metadata_gather", "schema_structure", "materialize", "exchange"}:
            raise BrainServiceError(f"unsupported external execution kind: {execution_kind}")
        store = self.brain._state_store.database_store
        if store is None:
            raise BrainServiceError("database store is required for external execution receipts")
        if self.find_api_resource(resource_id) is None:
            raise NotFoundError(resource_id)
        attempt_code = str(execution.get("attempt_code") or f"provider-external:{resource_id}:{execution_kind}:{audit_id}")
        delivery_code = str(execution.get("delivery_code") or f"provider-external:{resource_id}")
        callback_skill_id = str(
            execution.get("callback_skill_id")
            or ("metadata.schema.snapshot.upsert" if execution_kind in {"metadata_gather", "schema_structure"} else "delivery.receipt.ingest")
        )
        contract_skill_id = "external.schema.structure.apply" if execution_kind in {"metadata_gather", "schema_structure", "materialize"} else "external.exchange.executor.execute"
        attempt = store.delivery_repo.upsert_attempt(
            {
                "attempt_code": attempt_code,
                "delivery_code": delivery_code,
                "attempt_kind": execution_kind,
                "state": "planned",
                "executor_ref": execution.get("executor_ref") or contract_skill_id,
                "evidence_ref": audit_id,
                "payload_json": {
                    "resource_code": resource_id,
                    "contract_skill_id": contract_skill_id,
                    "callback_skill_id": callback_skill_id,
                    "change_plan_json": execution.get("change_plan_json") or {},
                    "canonical_write_policy": "callback_only",
                },
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        evidence = store.delivery_repo.add_execution_evidence(
            {
                "evidence_ref": f"{audit_id}:external-receipt",
                "delivery_code": delivery_code,
                "attempt_code": attempt.attempt_code,
                "executor_kind": "external_contract",
                "executor_ref": contract_skill_id,
                "evidence_kind": "executor_task_receipt",
                "result_status": "planned",
                "sanitized_payload_json": {
                    "resource_code": resource_id,
                    "attempt_code": attempt.attempt_code,
                    "callback_skill_id": callback_skill_id,
                    "canonical_write_policy": "callback_only",
                },
            },
            tenant_id=_DEFAULT_TENANT_ID,
        )
        return {
            "resource_id": resource_id,
            "attempt_code": attempt.attempt_code,
            "delivery_code": delivery_code,
            "executor_contract": contract_skill_id,
            "callback_skill_id": callback_skill_id,
            "receipt_ref": evidence.evidence_ref,
            "core_state_unchanged": True,
        }
