from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from zw_brain.domain.models import (
    AnchorOutboxRecord,
    AuditEventRecord,
    AuditReceiptRecord,
    CapabilityCallRecord,
    CapabilityManifestRecord,
    RuntimeStateRecord,
)
from zw_brain.domain.repositories import (
    ApplicationRepository,
    ApprovalRepository,
    CapabilityPackageRepository,
    CatalogRepository,
    DeliveryRepository,
    ExternalAdapterRepository,
    GatewayRuntimeRepository,
    GovernanceProjectionRepository,
    LegacyObjectMappingRepository,
    MetadataEvidenceRepository,
    ObjectionRepository,
    ResourceApiRepository,
    ServiceInvocationMetricRepository,
    TopicPackageRepository,
)
from zw_brain.domain.seed import clone_seed_snapshot
from zw_brain.shared.db import create_session_factory, ensure_parent_dir
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


class DatabaseStore:
    def __init__(self) -> None:
        self.catalog_repo = CatalogRepository()
        self.application_repo = ApplicationRepository()
        self.approval_repo = ApprovalRepository()
        self.delivery_repo = DeliveryRepository()
        self.capability_package_repo = CapabilityPackageRepository()
        self.external_adapter_repo = ExternalAdapterRepository()
        self.gateway_runtime_repo = GatewayRuntimeRepository()
        self.governance_projection_repo = GovernanceProjectionRepository()
        self.legacy_mapping_repo = LegacyObjectMappingRepository()
        self.metadata_evidence_repo = MetadataEvidenceRepository()
        self.objection_repo = ObjectionRepository()
        self.resource_api_repo = ResourceApiRepository()
        self.service_invocation_repo = ServiceInvocationMetricRepository()
        self.topic_package_repo = TopicPackageRepository()

    def initialize(self) -> None:
        ensure_parent_dir()

    def _session_factory(self):
        return create_session_factory()

    def load_runtime_state(self) -> tuple[dict[str, Any], dict[str, Any]]:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            record = session.execute(select(RuntimeStateRecord).where(RuntimeStateRecord.id == 1)).scalar_one_or_none()
            if record is None:
                snapshot = clone_seed_snapshot()
                ui_state = {
                    "role": "r1",
                    "discoveryQuery": "",
                    "brainOutage": False,
                }
                return snapshot, ui_state
            return dict(record.snapshot_json), dict(record.ui_state_json)

    def save_runtime_state(self, snapshot: dict[str, Any], ui_state: dict[str, Any]) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            record = session.execute(select(RuntimeStateRecord).where(RuntimeStateRecord.id == 1)).scalar_one_or_none()
            now = _now()
            if record is None:
                record = RuntimeStateRecord(id=1, snapshot_json=snapshot, ui_state_json=ui_state, updated_at=now)
                session.add(record)
            else:
                record.snapshot_json = snapshot
                record.ui_state_json = ui_state
                record.updated_at = now
            session.commit()

    def append_audit_event(self, request_id: str, actor: str, skill_id: str, phase: str, payload: dict[str, Any]) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            session.add(
                AuditEventRecord(
                    request_id=request_id,
                    actor=actor,
                    skill_id=skill_id,
                    phase=phase,
                    payload_json=safe_json(payload),
                    occurred_at=_now(),
                )
            )
            session.commit()

    def list_audit_events(self) -> list[AuditEventRecord]:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(AuditEventRecord).order_by(AuditEventRecord.occurred_at)).scalars())

    def append_capability_call(self, payload: dict[str, Any]) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            session.add(CapabilityCallRecord(**payload))
            session.commit()

    def list_capability_calls(self) -> list[CapabilityCallRecord]:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(CapabilityCallRecord).order_by(CapabilityCallRecord.started_at)).scalars())

    def replace_capability_manifests(self, manifests: dict[str, dict[str, Any]]) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            session.execute(delete(CapabilityManifestRecord))
            now = _now()
            for skill_id, manifest in manifests.items():
                session.add(
                    CapabilityManifestRecord(
                        skill_id=skill_id,
                        title=manifest["title"],
                        version=manifest["version"],
                        registry_source=manifest["registry_source"],
                        manifest_json=manifest,
                        updated_at=now,
                    )
                )
            session.commit()

    def append_anchor_outbox(self, request_id: str, skill_id: str, content_hash: str, chain_id: str) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            session.add(
                AnchorOutboxRecord(
                    request_id=request_id,
                    skill_id=skill_id,
                    content_hash=content_hash,
                    chain_id=chain_id,
                    delivered=False,
                    created_at=_now(),
                )
            )
            session.commit()

    def list_pending_anchor_outbox(self) -> list[AnchorOutboxRecord]:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            return list(
                session.execute(
                    select(AnchorOutboxRecord)
                    .where(AnchorOutboxRecord.delivered.is_(False))
                    .order_by(AnchorOutboxRecord.created_at)
                ).scalars()
            )

    def append_anchor_receipt(self, outbox: AnchorOutboxRecord, receipt: Any) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            existing = session.execute(
                select(AuditReceiptRecord).where(AuditReceiptRecord.content_hash == outbox.content_hash)
            ).scalar_one_or_none()
            receipt_json = {
                "tx_hash": receipt.tx_hash,
                "block_height": receipt.block_height,
                "chain_id": receipt.chain_id,
                "confirmed_at": receipt.confirmed_at.isoformat(),
            }
            if existing is None:
                session.add(
                    AuditReceiptRecord(
                        request_id=outbox.request_id,
                        skill_id=outbox.skill_id,
                        content_hash=outbox.content_hash,
                        chain_id=receipt.chain_id,
                        tx_hash=receipt.tx_hash,
                        block_height=receipt.block_height,
                        receipt_json=receipt_json,
                        confirmed_at=receipt.confirmed_at,
                    )
                )
            else:
                existing.request_id = outbox.request_id
                existing.skill_id = outbox.skill_id
                existing.chain_id = receipt.chain_id
                existing.tx_hash = receipt.tx_hash
                existing.block_height = receipt.block_height
                existing.receipt_json = receipt_json
                existing.confirmed_at = receipt.confirmed_at
            session.commit()

    def list_audit_receipts(self) -> list[AuditReceiptRecord]:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            return list(session.execute(select(AuditReceiptRecord).order_by(AuditReceiptRecord.confirmed_at)).scalars())

    def mark_anchor_delivered(self, content_hash: str) -> None:
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            record = session.execute(select(AnchorOutboxRecord).where(AnchorOutboxRecord.content_hash == content_hash)).scalar_one_or_none()
            if record is not None:
                record.delivered = True
                session.commit()

    def sync_reference_tables(self, snapshot: dict[str, Any]) -> None:
        for pkg in snapshot.get("capability_packages", []):
            self.capability_package_repo.upsert_from_package(pkg)

    def sync_aggregate_tables(self, snapshot: dict[str, Any]) -> None:
        self.sync_reference_tables(snapshot)

        for resource in snapshot.get("discovery", {}).get("resources", []):
            self.catalog_repo.upsert_from_resource(resource)
        for catalog in snapshot.get("provider", {}).get("catalogs", []):
            self.catalog_repo.upsert_from_resource(
                {
                    "id": catalog["id"],
                    "name": catalog.get("name", catalog["id"]),
                    "status": "approved_pending_publish" if catalog.get("status") != "已发布" else "active",
                    "provider": catalog.get("owner", ""),
                    "source_ref": catalog.get("source_ref") or f"provider:catalog:{catalog['id']}",
                    "legacy_object_ref": catalog.get("legacy_object_ref") or catalog["id"],
                    "summary_json": catalog,
                }
            )
        for resource in snapshot.get("provider", {}).get("resources", []):
            self.resource_api_repo.upsert_asset(
                {
                    "resource_code": resource["id"],
                    "title": resource.get("name", resource["id"]),
                    "resource_kind": "dataset",
                    "lifecycle_status": "approved_pending_publish" if resource.get("status") != "可共享" else "active",
                    "owner_org_id": resource.get("owner_org_id"),
                    "source_ref": resource.get("source_ref") or f"provider:resource:{resource['id']}",
                    "legacy_object_ref": resource.get("legacy_object_ref") or resource["id"],
                    "summary_json": resource,
                }
            )
        for item in snapshot.get("catalog_items", []) + snapshot.get("discovery", {}).get("catalog_items", []) + snapshot.get("provider", {}).get("catalog_items", []):
            self.catalog_repo.upsert_item(item)

        approvals = {item["id"]: item for item in snapshot.get("approvals", [])}
        for request in snapshot.get("requests", []):
            self.application_repo.upsert_from_request(request)
            self.approval_repo.upsert_from_request_and_approval(request, approvals.get(request["id"], {}))

        for delivery in snapshot.get("delivery_tasks", []):
            self.delivery_repo.upsert_from_delivery(delivery)

        if not self.resource_api_repo.has_assets():
            for resource in snapshot.get("api_resources", []):
                self.resource_api_repo.upsert_asset(resource)
                for binding in resource.get("channel_bindings", []):
                    self.resource_api_repo.upsert_binding({**binding, "resource_code": resource["resource_code"]})

        if not self.gateway_runtime_repo.has_statuses():
            for gateway in snapshot.get("gateway_runtime_statuses", []):
                self.gateway_runtime_repo.upsert_heartbeat(gateway)

        if not self.service_invocation_repo.has_metrics():
            for metric in snapshot.get("service_invocation_metrics", []):
                self.service_invocation_repo.upsert_metric(metric)

        for dispute in snapshot.get("disputes", []):
            self.objection_repo.upsert_from_dispute(dispute)
