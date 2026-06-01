from __future__ import annotations

import hashlib
import json
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
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.sanitization import safe_json

# Process-wide ui_state keys only — per-request `role` lives in ContextVar.
DEFAULT_PERSISTABLE_UI_STATE: dict[str, Any] = {
    "discoveryQuery": "",
    "brainOutage": False,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _content_fingerprint(*parts: Any) -> str:
    """Stable content hash of the exact inputs an aggregate upsert consumes.

    ``json.dumps(sort_keys=True, default=str)`` mirrors the ``safe_json``
    shape the repositories persist, so a matching fingerprint guarantees the
    upsert would write byte-identical column values (a no-op) — which is what
    makes skipping it observationally identical to running it.
    """
    blob = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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
        # HIGH-2 — per-write aggregate sync is O(snapshot) by design (it
        # re-upserts every request/approval/delivery/api_resource each write).
        # On the H3 write-lock hot path that means ~528 transactions per write
        # on a populated snapshot, all serialized inside the global write lock.
        # ``_aggregate_fingerprints`` lets ``sync_aggregate_tables`` skip the
        # upsert for any entity whose content is byte-identical to the last
        # sync — a re-upsert of unchanged content is a no-op, so skipping is
        # observationally identical while collapsing the per-write cost to
        # O(entities this write actually touched). Process-local cache keyed by
        # (kind, tenant_id, entity_id) → content sha256; mirrors the
        # process-singleton snapshot's lifecycle (rebuilt on a fresh store).
        self._aggregate_fingerprints: dict[tuple[str, str, str], str] = {}

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
                return snapshot, dict(DEFAULT_PERSISTABLE_UI_STATE)
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

    def list_audit_events(self, *, limit: int = 500) -> list[AuditEventRecord]:
        """Return the most-recent audit events (default 500). Without LIMIT the
        page hot path hydrates thousands of large payload_json blobs (~14 s for
        ~2300 rows), which is what made audit.list and compliance.case.query
        time out. Callers that genuinely need all events should iterate paged.
        """
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            statement = select(AuditEventRecord).order_by(AuditEventRecord.occurred_at.desc())
            if limit and limit > 0:
                statement = statement.limit(limit)
            records = list(session.execute(statement).scalars())
            records.reverse()  # 调用方期望 ascending by time
            return records

    def count_audit_events(self) -> int:
        from sqlalchemy import func
        SessionLocal = self._session_factory()
        with SessionLocal() as session:
            return int(session.execute(select(func.count()).select_from(AuditEventRecord)).scalar() or 0)

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

    def sync_reference_tables(self, snapshot: dict[str, Any], *, full: bool = False) -> None:
        tenant_id = get_runtime_tenant_id()
        for pkg in snapshot.get("capability_packages", []):
            # Reference data (capability manifests) rarely changes per write;
            # fingerprint-gate the re-upsert so the per-write hot path doesn't
            # re-write every package each time (HIGH-2 same root cause).
            changed = self._aggregate_changed(
                "capability_package", str(pkg.get("slug") or id(pkg)),
                _content_fingerprint(pkg, tenant_id), tenant_id=tenant_id,
            )
            if full or changed:
                self.capability_package_repo.upsert_from_package(pkg)
        if not self.topic_package_repo.list_packages(tenant_id=get_runtime_tenant_id()):
            for zone in snapshot.get("zones", []):
                self.topic_package_repo.create_package(
                    {
                        "package_code": str(zone["id"]),
                        "title": str(zone.get("name") or zone["id"]),
                        "scenario": str(zone.get("desc") or "共享专区"),
                        "status": "published" if zone.get("status") == "已上线" else "draft",
                        "display_snapshot_json": {**safe_json(zone), "projection_kind": "share_zone"},
                        "source_ref": f"seed:zone:{zone['id']}",
                    },
                    tenant_id=get_runtime_tenant_id(),
                )
        # F9 (D32.a) — sd-default 山东标杆专题包：create→configure(items+visibility)→publish。
        # 与上面 zones 注入分开、per-package 幂等（已存在则跳过），引用真 catalog_entry（守 D11）。
        self._seed_topic_packages(snapshot.get("topic_packages", []))

    def _seed_topic_packages(self, packages: list[dict[str, Any]]) -> None:
        tenant_id = get_runtime_tenant_id()
        for pkg in packages:
            code = str(pkg["package_code"])
            if self.topic_package_repo.get_package(code, tenant_id=tenant_id) is not None:
                continue
            self.topic_package_repo.create_package(pkg, tenant_id=tenant_id)
            self.topic_package_repo.configure_package(code, pkg, tenant_id=tenant_id)
            self.topic_package_repo.transition_package(code, "submitted", {"action_type": "submit"}, tenant_id=tenant_id)
            self.topic_package_repo.transition_package(code, "published", {"action_type": "publish"}, tenant_id=tenant_id)

    def _aggregate_changed(self, kind: str, entity_id: str, fingerprint: str, *, tenant_id: str) -> bool:
        """Check-and-update the per-entity fingerprint cache.

        Always records ``fingerprint`` as the latest synced value for
        ``(kind, tenant_id, entity_id)`` (so a ``full`` sweep primes the cache
        too), and returns whether it *differs* from the previously cached one.
        HIGH-2: callers upsert iff ``full or changed`` — turning the per-write
        O(snapshot) re-upsert sweep into O(entities this write changed) without
        altering DB state (a skipped no-op upsert would have written
        byte-identical columns).
        """
        key = (kind, tenant_id, entity_id)
        changed = self._aggregate_fingerprints.get(key) != fingerprint
        self._aggregate_fingerprints[key] = fingerprint
        return changed

    def sync_aggregate_tables(self, snapshot: dict[str, Any], *, full: bool = False) -> None:
        """Mirror aggregate-shaped snapshot slices into the DB.

        ``full=True`` (startup / first sync) bypasses the fingerprint delta and
        unconditionally upserts every entity, priming the fingerprint cache so
        subsequent per-write syncs (``full=False``, the H3 write-lock hot path)
        only touch entities whose content changed. The persisted DB state is
        identical either way — the delta only elides no-op re-upserts.
        """
        self.sync_reference_tables(snapshot, full=full)
        tenant_id = get_runtime_tenant_id()
        should_seed_static_projection = not (self.resource_api_repo.has_assets(tenant_id=tenant_id) or self.catalog_repo.list_entries(tenant_id=tenant_id))

        if should_seed_static_projection:
            for resource in snapshot.get("discovery", {}).get("resources", []):
                self.catalog_repo.upsert_from_resource(resource, tenant_id=tenant_id)
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
                    },
                    tenant_id=tenant_id,
                )
            for resource in snapshot.get("provider", {}).get("resources", []):
                self.resource_api_repo.upsert_asset(
                    {
                        "resource_code": resource["id"],
                        "title": resource.get("name", resource["id"]),
                        "resource_kind": resource.get("resource_kind", "dataset"),
                        "lifecycle_status": resource.get("lifecycle_status")
                        or ("approved_pending_publish" if resource.get("status") != "可共享" else "active"),
                        "owner_org_id": resource.get("owner_org_id"),
                        # 目录归属：让 seed 资源能挂到目录（catalog.resource.list 钻取依赖此）
                        "catalog_code": resource.get("catalog_code"),
                        "source_ref": resource.get("source_ref") or f"provider:resource:{resource['id']}",
                        "legacy_object_ref": resource.get("legacy_object_ref") or resource["id"],
                        "summary_json": resource,
                    },
                    tenant_id=tenant_id,
                )
            for item in snapshot.get("catalog_items", []) + snapshot.get("discovery", {}).get("catalog_items", []) + snapshot.get("provider", {}).get("catalog_items", []):
                self.catalog_repo.upsert_item(item, tenant_id=tenant_id)

        # Per-write hot loops — fingerprint-gated delta when not a full sync.
        # ``application_record`` + ``approval`` share the request dict (approval
        # upsert keys off the same request id), so their fingerprint spans both
        # request and approval payloads; skipping requires *both* unchanged.
        approvals = {item["id"]: item for item in snapshot.get("approvals", [])}
        for request in snapshot.get("requests", []):
            approval = approvals.get(request["id"], {})
            changed = self._aggregate_changed(
                "request_approval", str(request["id"]),
                _content_fingerprint(request, approval), tenant_id=tenant_id,
            )
            if full or changed:
                self.application_repo.upsert_from_request(request, tenant_id=tenant_id)
                self.approval_repo.upsert_from_request_and_approval(request, approval, tenant_id=tenant_id)

        for delivery in snapshot.get("delivery_tasks", []):
            changed = self._aggregate_changed(
                "delivery", str(delivery.get("id") or delivery.get("deliveryCode") or id(delivery)),
                _content_fingerprint(delivery), tenant_id=tenant_id,
            )
            if full or changed:
                self.delivery_repo.upsert_from_delivery(delivery, tenant_id=tenant_id)

        for resource in snapshot.get("api_resources", []):
            existing_asset = self.resource_api_repo.get_asset(resource["resource_code"], tenant_id=tenant_id)
            if existing_asset is not None and not should_seed_static_projection:
                continue
            changed = self._aggregate_changed(
                "api_resource", str(resource["resource_code"]),
                _content_fingerprint(resource), tenant_id=tenant_id,
            )
            if not (full or changed):
                continue
            self.resource_api_repo.upsert_asset(resource, tenant_id=tenant_id)
            for binding in resource.get("channel_bindings", []):
                self.resource_api_repo.upsert_binding({**binding, "resource_code": resource["resource_code"]}, tenant_id=tenant_id)

        if not self.gateway_runtime_repo.has_statuses(tenant_id=tenant_id):
            for gateway in snapshot.get("gateway_runtime_statuses", []):
                self.gateway_runtime_repo.upsert_heartbeat(gateway, tenant_id=tenant_id)

        if not self.service_invocation_repo.has_metrics(tenant_id=tenant_id):
            for metric in snapshot.get("service_invocation_metrics", []):
                self.service_invocation_repo.upsert_metric(metric, tenant_id=tenant_id)

        for dispute in snapshot.get("disputes", []):
            changed = self._aggregate_changed(
                "dispute", str(dispute.get("id") or dispute.get("case_code") or id(dispute)),
                _content_fingerprint(dispute), tenant_id=tenant_id,
            )
            if full or changed:
                self.objection_repo.upsert_from_dispute(dispute, tenant_id=tenant_id)
