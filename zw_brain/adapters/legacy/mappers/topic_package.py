"""dsp_example → TopicPackageRecord mapper (A1 customer-grade demo seed).

Step 5 (sharezone branch) of the bridging chain. Loads the 10 真政务案例 from
`old/10示例数据/dump-dsp_example-*.sql` directly into TopicPackageRecord, attaches
items / contacts / files / feedback as evidence, and pushes them through the
`draft → configuring → submitted → published` state machine so the WebUI / Dashboard
can read real cases from day one of customer trial.

Sensitive fields:
  - data_example_contact.contact_name + contact_phone are stored raw in
    `display_snapshot_json.contacts` (per [2026-05-06] override) — read paths must
    apply zw_brain.shared.sensitive_mask before display.
  - No real secrets in dsp_example.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from zw_brain.adapters.legacy._common import ImportStats, coerce_time, finish_run, parse_json_blob, schema_from_dump_name
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.models import TopicPackageEvidenceRecord
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.topic_package import (
    TopicPackageRepository,
    TopicPackageStateError,
)
from zw_brain.shared.db import create_session_factory

# Legacy `data_example.status` (CREATE TABLE COMMENT in dump-dsp_example-*.sql) →
# canonical TopicPackageRecord state machine target. None means: stop after
# configure_package (i.e. legacy was a draft — don't lie about its review state).
_LEGACY_EXAMPLE_STATUS_TO_TARGET: dict[str, str | None] = {
    "0": None,            # 草稿 — leave at configuring
    "1": "submitted",     # 待审核
    "2": "submitted",     # 待发布 (next user action = publish; not auto-advanced)
    "3": "rejected",      # 审核驳回
    "4": "published",     # 已发布
    "5": "rejected",      # 发布驳回
}


class TopicPackageMapper:
    """Maps dsp_example.* tables onto TopicPackage* records.

    Parse order matters: data_example must be processed before its child tables so the
    package row exists when items / files / feedback / contacts are attached. The
    parser yields rows in dump order (CREATE TABLE order), and dsp_example dumps the
    parent table first; in defensive mode the mapper buffers child rows for unknown
    parents and applies them at the end.
    """

    HANDLED_TABLES = {
        "data_example",
        "data_example_item",
        "data_example_file",
        "data_example_feedback",
        "data_example_contact",
    }
    ADAPTER_SLUG = "legacy.sharezone.example.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.topic_repo = TopicPackageRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # First pass: collect rows so we can apply parents before children.
        examples: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        feedbacks: list[dict[str, Any]] = []
        contacts: list[dict[str, Any]] = []

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            if table == "data_example":
                examples.append(row)
            elif table == "data_example_item":
                items.append(row)
            elif table == "data_example_file":
                files.append(row)
            elif table == "data_example_feedback":
                feedbacks.append(row)
            elif table == "data_example_contact":
                contacts.append(row)

        # Group children by org_code+example_id where applicable
        items_by_example = _group_by(items, "example_id") if items and "example_id" in items[0] else {}
        files_by_example = _group_by(files, "example_id") if files and "example_id" in files[0] else {}
        feedbacks_by_example = _group_by(feedbacks, "example_id") if feedbacks and "example_id" in feedbacks[0] else {}
        contacts_by_org = _group_by(contacts, "org_code") if contacts else {}

        for example in examples:
            try:
                self._import_one(
                    example,
                    legacy_system=legacy_system,
                    items=items_by_example.get(example.get("id"), []),
                    files=files_by_example.get(example.get("id"), []),
                    feedbacks=feedbacks_by_example.get(example.get("id"), []),
                    contacts=contacts_by_org.get(example.get("org_code"), []),
                )
                stats.bump("data_example")
            except (TopicPackageStateError, KeyError) as exc:
                stats.bump("data_example", "errors")
                key = f"data_example.error:{type(exc).__name__}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        for table, count in (
            ("data_example_item", sum(len(v) for v in items_by_example.values())),
            ("data_example_file", sum(len(v) for v in files_by_example.values())),
            ("data_example_feedback", sum(len(v) for v in feedbacks_by_example.values())),
            ("data_example_contact", sum(len(v) for v in contacts_by_org.values())),
        ):
            if count:
                stats.counts[f"{table}.attached"] = count

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    # ------------------------------------------------------------------
    # one-package pipeline
    # ------------------------------------------------------------------

    def _import_one(
        self,
        example: dict[str, Any],
        *,
        legacy_system: str,
        items: list[dict[str, Any]],
        files: list[dict[str, Any]],
        feedbacks: list[dict[str, Any]],
        contacts: list[dict[str, Any]],
    ) -> None:
        package_code = example["id"]
        title = example.get("example_name") or package_code
        scenario = "一表通 / 基层报表减负"

        self.topic_repo.create_package(
            {
                "package_code": package_code,
                "title": title,
                "scenario": scenario,
                "owner_org_id": example.get("org_code"),
                "owner_org_snapshot_json": {
                    "org_code": example.get("org_code"),
                    "org_name": example.get("org_name"),
                    "region_code": example.get("region_code"),
                    "region_name": example.get("region_name"),
                },
                "status": "draft",
                "display_snapshot_json": {
                    "summary": example.get("example_desc"),
                    "process_desc": example.get("process_desc"),
                    "result_desc": example.get("result_desc"),
                    "field_type": example.get("field_type"),
                    "implement_key": example.get("implement_key"),
                    "security_way": example.get("security_way"),
                    "work_rule": example.get("work_rule"),
                    "opinion": example.get("opinion"),
                    "push_status": example.get("push_status"),
                    "visit_count": example.get("visit_count"),
                    "average_score": example.get("example_average_score"),
                    "create_time": coerce_time(example.get("create_time")),
                    # business-visible sensitive — read layer applies sensitive_mask
                    "contacts": [
                        {
                            # legacy column is `contact` (the person's name); we keep
                            # the canonical key `contact_name` so the mask layer can
                            # auto-detect via DEFAULT_MASK_HINTS.
                            "contact_name": c.get("contact") or c.get("contact_name"),
                            "contact_phone": c.get("contact_phone"),
                            "title": c.get("title"),
                            "org_code": c.get("org_code"),
                            "org_name": c.get("org_name"),
                            "region_name": c.get("region_name"),
                            "default_flag": c.get("status"),
                        }
                        for c in contacts
                    ],
                },
                "metric_snapshot_json": {
                    "visit_count": example.get("visit_count"),
                    "average_score": example.get("example_average_score"),
                },
                "source_ref": f"{legacy_system}:data_example:{package_code}",
            },
            tenant_id=self.tenant_id,
        )

        # legacy mapping for the package
        self.legacy_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:data_example:{package_code}",
                "legacy_system": legacy_system,
                "legacy_object_type": "data_example",
                "legacy_object_ref": package_code,
                "canonical_type": "TopicPackageRecord",
                "canonical_ref": package_code,
                "evidence_json": {"title": title, "field_type": example.get("field_type")},
            },
            tenant_id=self.tenant_id,
        )

        # configure with items + a default approved visibility so we can publish
        configure_payload: dict[str, Any] = {
            "items": [
                {
                    "item_code": item.get("example_item_id") or item.get("id") or f"item-{idx}",
                    "ref_type": item.get("res_type") or "resource",
                    "ref_id": item.get("res_id") or item.get("example_item_id") or f"item-{idx}",
                    "title": item.get("res_name") or item.get("task_name") or item.get("material_name") or "未命名材料",
                    "display_order": idx,
                    "summary_json": {
                        "task_code": item.get("task_code"),
                        "task_name": item.get("task_name"),
                        "material_id": item.get("material_id"),
                        "material_name": item.get("material_name"),
                        "resource_name": item.get("res_name"),
                        "resource_id": item.get("res_id"),
                        "resource_type": item.get("res_type"),
                        "resource_status": item.get("res_status"),
                        "catalog_id": item.get("cata_id"),
                        "catalog_title": item.get("cata_title"),
                    },
                }
                for idx, item in enumerate(items)
            ],
            "visibility": [
                {
                    "visibility_code": f"{package_code}-default",
                    "role_code": "shandong-province",
                    "policy_status": "approved",
                    "condition_json": {"region_code": example.get("region_code")},
                }
            ],
        }
        if items:
            self.topic_repo.configure_package(package_code, configure_payload, tenant_id=self.tenant_id)
        else:
            # No items in the dump — still record the visibility so any future configure
            # will not double-create the default policy.
            self.topic_repo.configure_package(package_code, {"visibility": configure_payload["visibility"]}, tenant_id=self.tenant_id)

        # Wipe any existing evidence for this package before re-attaching, so re-imports
        # are idempotent (TopicPackageRepository.attach_evidence has no dedup —
        # without this, a re-import would double every file/feedback row).
        # Items + visibility are managed by configure_package's UPSERT path; only
        # evidence needs explicit cleanup.
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            session.execute(
                delete(TopicPackageEvidenceRecord).where(
                    TopicPackageEvidenceRecord.tenant_id == self.tenant_id,
                    TopicPackageEvidenceRecord.package_code == package_code,
                )
            )
            session.commit()

        # files → evidence (file_path is a JSON string per CREATE TABLE COMMENT)
        for f in files:
            file_meta = parse_json_blob(f.get("file_path"))
            self.topic_repo.attach_evidence(
                package_code,
                {
                    "evidence_type": "file",
                    "title": file_meta.get("file_name") or f.get("file_type") or "附件",
                    "related_ref_type": "data_example_file",
                    "related_ref_id": f.get("example_file_id"),
                    "content_json": {
                        "file_type": f.get("file_type"),
                        **file_meta,
                    },
                    "submitted_by_json": {"source": "legacy:dsp_example"},
                },
                tenant_id=self.tenant_id,
            )
        # feedback → evidence (kind='feedback'; objection-flow upgrade is deferred)
        for fb in feedbacks:
            self.topic_repo.attach_evidence(
                package_code,
                {
                    "evidence_type": "feedback",
                    "title": fb.get("res_name") or fb.get("example_name") or fb.get("require_title") or "反馈",
                    "related_ref_type": "data_example_feedback",
                    "related_ref_id": fb.get("id"),
                    "content_json": {
                        "is_apply": fb.get("is_apply"),
                        "is_need": fb.get("is_need"),
                        "reason": fb.get("reason"),
                        "creator_org_name": fb.get("org_name"),
                        "feedback_org_name": fb.get("feedback_org_name"),
                        "require_id": fb.get("require_id"),
                        "require_title": fb.get("require_title"),
                        "link_type": fb.get("link_type"),
                        "create_time": coerce_time(fb.get("create_time")),
                    },
                    "submitted_by_json": {"creator": fb.get("creator")},
                },
                tenant_id=self.tenant_id,
            )

        # Walk the canonical state machine to the position implied by legacy
        # `data_example.status`. The legacy enum (CREATE TABLE COMMENT) is:
        #   0 = 草稿       → stay at "configuring" (post-configure_package)
        #   1 = 待审核     → "submitted"
        #   2 = 待发布     → "submitted" (next user action would be publish)
        #   3 = 审核驳回   → "rejected" via "submitted"
        #   4 = 已发布     → "published" via "submitted"
        #   5 = 发布驳回   → "rejected" via "submitted"
        # We do NOT force-publish drafts: that would lie to operators about which
        # cases the legacy platform actually approved. Items must exist for any
        # forward transition (publish guard requires items + approved visibility).
        path_for_target: dict[str, list[str]] = {
            "submitted": ["submitted"],
            "rejected": ["submitted", "rejected"],
            "published": ["submitted", "published"],
        }
        target = _LEGACY_EXAMPLE_STATUS_TO_TARGET.get(str(example.get("status") or ""))
        if items and target is not None:
            for next_state in path_for_target[target]:
                try:
                    self.topic_repo.transition_package(
                        package_code,
                        next_state,
                        {
                            "action_type": "legacy_import",
                            "opinion": (example.get("opinion") or f"legacy status={example.get('status')}"),
                        },
                        tenant_id=self.tenant_id,
                    )
                except TopicPackageStateError:
                    # Guard rejected (e.g. publish without approved visibility) — stop walk
                    break


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.get(key), []).append(row)
    return out
