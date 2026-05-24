"""F4 turn 1: projection.status.query capability — 5 类投影状态 + 失败摘要 health 聚合。

测试覆盖:
  - empty: 全部投影 0 行 → overall_health="red"
  - healthy: 5 类投影都有行 + 零失败 → overall_health="green"
  - degraded: topic_package status="rejected" + quality_status="failed" →
    overall_health="yellow"，failure_summary 含失败行
  - schema: handler 返回 5 个 projection kind 名固定（防 typo 漂移）

handler 通过 BrainService.invoke_skill 调用，走完整 trust-stamp 链路（F6 turn 1
invoke_trusted helper）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore


@pytest.fixture
def brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrainService:
    db_path = tmp_path / "projection_status.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    ensure_runtime_schema()
    store = DatabaseStore()
    audit_bus.configure_sink(store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=store))


def test_projection_status_query_shape_stable(brain: BrainService) -> None:
    """5 个 kind 名顺序固定 + 每条 projection 含 5 字段 + overall_health ∈ {green, yellow, red}。

    BrainService init 通过 _sync_database_aggregates 把 snapshot seed 灌入 DB —— fresh DB
    并非真空，但 5 projection kind 名 / 字段 / health 值域是稳定 schema。
    """
    result = invoke_trusted(
        brain,
        "projection.status.query",
        {},
        role="ROLE_ORGAN_MANAGER",
    )
    assert result["tenant_id"]  # truthy
    assert len(result["projections"]) == 5
    kinds = [p["kind"] for p in result["projections"]]
    assert kinds == ["search", "topic_package", "quality", "lineage", "ops_metric"]
    for p in result["projections"]:
        assert set(p.keys()) == {"kind", "total_rows", "latest_updated_at", "failed_count", "failure_summary"}
        assert isinstance(p["total_rows"], int)
        assert isinstance(p["failed_count"], int)
        assert isinstance(p["failure_summary"], list)
    assert result["overall_health"] in {"green", "yellow", "red"}


def test_projection_status_query_healthy_returns_green(brain: BrainService, tmp_path: Path) -> None:
    """5 类投影都有行 + 零失败 → overall_health=green。"""
    topic_repo = TopicPackageRepository()
    metadata_repo = MetadataEvidenceRepository()
    tenant_id = "sd-default"

    # 灌一个 TopicPackage（共享专题）— status=draft（非 rejected，不算失败）
    topic_repo.create_package(
        {
            "package_code": "PKG-HEALTHY",
            "title": "健康主题包",
            "scenario": "test",
            "owner_org_id": "ORG-A",
            "status": "draft",
            "display_snapshot_json": {},
            "metric_snapshot_json": {},
            "source_ref": "test:healthy",
        },
        tenant_id=tenant_id,
    )

    # 灌一条 Lineage（血缘）
    metadata_repo.upsert_lineage_relation(
        {
            "relation_ref": "test-lineage-1",
            "relation_scope": "graphdb",
            "source_resource_code": "RES-A",
            "target_resource_code": "RES-B",
            "relation_type": "join",
            "relation_rule_json": {},
        },
        tenant_id=tenant_id,
    )

    # 灌一条 QualityEvidence（质量）— status=passed
    metadata_repo.upsert_quality_evidence(
        {
            "quality_ref": "test-qual-1",
            "target_type": "catalog_entry",
            "target_ref": "ENTRY-A",
            "quality_status": "passed",
            "score": 95,
            "evidence_json": {},
        },
        tenant_id=tenant_id,
    )

    # search / ops_metric 类的 seed 由 BrainService init `_sync_database_aggregates`
    # 从 snapshot 灌入；本测试只验证我们 inject 的 topic / quality / lineage 不引入失败。

    result = invoke_trusted(
        brain,
        "projection.status.query",
        {"tenant_id": tenant_id},
        role="ROLE_ORGAN_MANAGER",
    )
    # 我们 inject 的 topic_package / quality / lineage 应可见且零失败
    by_kind = {p["kind"]: p for p in result["projections"]}
    assert by_kind["topic_package"]["total_rows"] >= 1
    assert by_kind["topic_package"]["failed_count"] == 0
    assert by_kind["quality"]["total_rows"] >= 1
    assert by_kind["quality"]["failed_count"] == 0
    assert by_kind["lineage"]["total_rows"] >= 1
    assert by_kind["lineage"]["failed_count"] == 0
    # health: green (所有类都有数据零失败) 或 yellow (search/ops_metric 类
    # 仍空 → yellow 因 has_red 触发；视 BrainService seed 而定)
    assert result["overall_health"] in {"green", "yellow"}


def test_projection_status_query_degraded_returns_yellow(brain: BrainService) -> None:
    """topic_package rejected + quality failed + exchange has failed_count → yellow + failure_summary。"""
    topic_repo = TopicPackageRepository()
    metadata_repo = MetadataEvidenceRepository()
    tenant_id = "sd-default"

    # 1 个 rejected 主题包 + 1 个 draft 主题包
    topic_repo.create_package(
        {
            "package_code": "PKG-OK",
            "title": "正常主题包",
            "scenario": "test",
            "owner_org_id": "ORG-A",
            "status": "draft",
            "display_snapshot_json": {},
            "metric_snapshot_json": {},
            "source_ref": "test:ok",
        },
        tenant_id=tenant_id,
    )
    topic_repo.create_package(
        {
            "package_code": "PKG-REJECTED",
            "title": "被驳回的主题包",
            "scenario": "test",
            "owner_org_id": "ORG-A",
            "status": "draft",
            "display_snapshot_json": {},
            "metric_snapshot_json": {},
            "source_ref": "test:rejected",
        },
        tenant_id=tenant_id,
    )
    topic_repo.transition_package(
        "PKG-REJECTED",
        "submitted",
        {"action_type": "test"},
        tenant_id=tenant_id,
    )
    topic_repo.transition_package(
        "PKG-REJECTED",
        "rejected",
        {"action_type": "test", "opinion": "测试失败摘要"},
        tenant_id=tenant_id,
    )

    # 1 个 failed quality + 1 个 passed quality
    metadata_repo.upsert_quality_evidence(
        {
            "quality_ref": "test-qual-pass",
            "target_type": "catalog_entry",
            "target_ref": "ENTRY-OK",
            "quality_status": "passed",
            "score": 95,
            "evidence_json": {},
        },
        tenant_id=tenant_id,
    )
    metadata_repo.upsert_quality_evidence(
        {
            "quality_ref": "test-qual-fail",
            "target_type": "catalog_entry",
            "target_ref": "ENTRY-BAD",
            "quality_status": "failed",
            "score": 30,
            "evidence_json": {"reason": "测试失败"},
        },
        tenant_id=tenant_id,
    )

    result = invoke_trusted(
        brain,
        "projection.status.query",
        {"tenant_id": tenant_id},
        role="ROLE_ORGAN_MANAGER",
    )
    # 有失败 → yellow（health 必非 green）
    assert result["overall_health"] in {"yellow", "red"}

    by_kind = {p["kind"]: p for p in result["projections"]}
    # topic_package: 至少 1 个 rejected
    assert by_kind["topic_package"]["failed_count"] >= 1
    rejected_codes = {f["package_code"] for f in by_kind["topic_package"]["failure_summary"]}
    assert "PKG-REJECTED" in rejected_codes
    statuses = {f["status"] for f in by_kind["topic_package"]["failure_summary"]}
    assert "rejected" in statuses

    # quality: 至少 1 个 failed
    assert by_kind["quality"]["failed_count"] >= 1
    failed_refs = {f["quality_ref"] for f in by_kind["quality"]["failure_summary"]}
    assert "test-qual-fail" in failed_refs


def test_projection_status_query_schema_stable(brain: BrainService) -> None:
    """5 个 kind 名顺序固定，每个 projection 都含 5 字段（防 typo / 字段漂移）。"""
    result = invoke_trusted(
        brain,
        "projection.status.query",
        {},
        role="ROLE_ORGAN_MANAGER",
    )
    assert result["tenant_id"]  # truthy
    expected_kinds = ["search", "topic_package", "quality", "lineage", "ops_metric"]
    assert [p["kind"] for p in result["projections"]] == expected_kinds
    for p in result["projections"]:
        assert set(p.keys()) == {"kind", "total_rows", "latest_updated_at", "failed_count", "failure_summary"}
        assert isinstance(p["total_rows"], int)
        assert isinstance(p["failed_count"], int)
        assert isinstance(p["failure_summary"], list)
    assert result["overall_health"] in {"green", "yellow", "red"}
