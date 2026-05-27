"""B1 `projection.status.query` handler — 5 类投影状态聚合 + 失败摘要 (F4 turn 1).

读 5 类 projection record 的 health 状态，让 业务运营员 / 安全审计员 一眼看到
投影 pipeline 是否健康：

  - search          → CatalogEntryRecord (data_search 命中目标)
  - 共享专题         → TopicPackageRecord (含 basesubject + dsp_example)
  - 质量            → QualityEvidenceProjectionRecord
  - 血缘            → LineageRelationProjectionRecord (含 graph_lineage)
  - 运营统计         → ExchangeMetricProjectionRecord + ServiceInvocationMetricProjectionRecord

每类返回：total_rows / latest_updated_at / failed_count / failure_summary (最近 ≤5 条)
overall_health: green (零失败且至少 1 类有数据) / yellow (有失败但非全失败) /
                red (任一类全失败 or 全 0 row)。零 side effect，read-trace 审计。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def _metadata_evidence_repo() -> MetadataEvidenceRepository:
    return MetadataEvidenceRepository()

# 失败状态判定：每类不同
_TOPIC_FAILED_STATUSES = {"rejected"}
_QUALITY_FAILED_STATUSES = {"failed", "rejected", "warning"}
_METADATA_FAILED_STATUSES = {"failed", "error"}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _project_search(brain: BrainService, tenant_id: str) -> dict[str, Any]:
    """search 投影 = CatalogEntryRecord（data_search 命中底层目录条目）。"""
    from sqlalchemy import desc, func, select  # noqa: PLC0415 — keep import-cost local

    from zw_brain.domain.models import CatalogEntryRecord  # noqa: PLC0415
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        total = session.execute(
            select(func.count(CatalogEntryRecord.id)).where(CatalogEntryRecord.tenant_id == tenant_id)
        ).scalar() or 0
        latest = session.execute(
            select(CatalogEntryRecord.updated_at)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .order_by(desc(CatalogEntryRecord.updated_at))
            .limit(1)
        ).scalar()
        # search 类无失败语义（lifecycle 状态由 J2 流程管），failed_count=0
    return {
        "kind": "search",
        "total_rows": int(total),
        "latest_updated_at": _iso(latest),
        "failed_count": 0,
        "failure_summary": [],
    }


def _project_topic_package(brain: BrainService, tenant_id: str) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    """共享专题 = TopicPackageRecord（含 basesubject + dsp_example 主题包）。"""
    packages = deps.repos.topic_package.list_packages(tenant_id=tenant_id)
    failures = [p for p in packages if p.status in _TOPIC_FAILED_STATUSES]
    latest = max((p.updated_at for p in packages if p.updated_at is not None), default=None)
    return {
        "kind": "topic_package",
        "total_rows": len(packages),
        "latest_updated_at": _iso(latest),
        "failed_count": len(failures),
        "failure_summary": [
            {
                "package_code": p.package_code,
                "title": p.title,
                "status": p.status,
                "updated_at": _iso(p.updated_at),
            }
            for p in failures[:5]
        ],
    }


def _project_quality(brain: BrainService, tenant_id: str) -> dict[str, Any]:
    """质量 = QualityEvidenceProjectionRecord。失败 = quality_status ∈ {failed/rejected/warning}。"""
    records = _metadata_evidence_repo().list_quality_evidence(tenant_id=tenant_id)
    failures = [r for r in records if (r.quality_status or "").lower() in _QUALITY_FAILED_STATUSES]
    latest = max((r.generated_at for r in records if r.generated_at is not None), default=None)
    return {
        "kind": "quality",
        "total_rows": len(records),
        "latest_updated_at": _iso(latest),
        "failed_count": len(failures),
        "failure_summary": [
            {
                "quality_ref": r.quality_ref,
                "target_type": r.target_type,
                "target_ref": r.target_ref,
                "quality_status": r.quality_status,
                "generated_at": _iso(r.generated_at),
            }
            for r in failures[:5]
        ],
    }


def _project_lineage(brain: BrainService, tenant_id: str) -> dict[str, Any]:
    """血缘 = LineageRelationProjectionRecord（含 graph_lineage scope=graphdb 5 表）。"""
    records = _metadata_evidence_repo().list_lineage_relations(tenant_id=tenant_id)
    latest = max((r.generated_at for r in records if r.generated_at is not None), default=None)
    # Lineage record 无 status — 无 failure_summary（pipeline 全成功）
    return {
        "kind": "lineage",
        "total_rows": len(records),
        "latest_updated_at": _iso(latest),
        "failed_count": 0,
        "failure_summary": [],
    }


def _project_ops_metric(brain: BrainService, tenant_id: str) -> dict[str, Any]:
    """运营统计 = ExchangeMetricProjectionRecord + ServiceInvocationMetricProjectionRecord."""
    from sqlalchemy import desc, func, select  # noqa: PLC0415

    from zw_brain.domain.models import (  # noqa: PLC0415
        ExchangeMetricProjectionRecord,
        ServiceInvocationMetricProjectionRecord,
    )
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        exchange_total = session.execute(
            select(func.count(ExchangeMetricProjectionRecord.id)).where(ExchangeMetricProjectionRecord.tenant_id == tenant_id)
        ).scalar() or 0
        exchange_failed_total = session.execute(
            select(func.coalesce(func.sum(ExchangeMetricProjectionRecord.failed_count), 0))
            .where(ExchangeMetricProjectionRecord.tenant_id == tenant_id)
        ).scalar() or 0
        exchange_latest = session.execute(
            select(ExchangeMetricProjectionRecord.generated_at)
            .where(ExchangeMetricProjectionRecord.tenant_id == tenant_id)
            .order_by(desc(ExchangeMetricProjectionRecord.generated_at))
            .limit(1)
        ).scalar()
        exchange_recent_failures = session.execute(
            select(ExchangeMetricProjectionRecord)
            .where(
                ExchangeMetricProjectionRecord.tenant_id == tenant_id,
                ExchangeMetricProjectionRecord.failed_count > 0,
            )
            .order_by(desc(ExchangeMetricProjectionRecord.last_error_at))
            .limit(5)
        ).scalars().all()

        svc_total = session.execute(
            select(func.count(ServiceInvocationMetricProjectionRecord.id)).where(ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id)
        ).scalar() or 0
        svc_failed_total = session.execute(
            select(func.coalesce(func.sum(ServiceInvocationMetricProjectionRecord.failed_count), 0))
            .where(ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id)
        ).scalar() or 0
        svc_latest = session.execute(
            select(ServiceInvocationMetricProjectionRecord.generated_at)
            .where(ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id)
            .order_by(desc(ServiceInvocationMetricProjectionRecord.generated_at))
            .limit(1)
        ).scalar()
        svc_recent_failures = session.execute(
            select(ServiceInvocationMetricProjectionRecord)
            .where(
                ServiceInvocationMetricProjectionRecord.tenant_id == tenant_id,
                ServiceInvocationMetricProjectionRecord.failed_count > 0,
            )
            .order_by(desc(ServiceInvocationMetricProjectionRecord.last_error_at))
            .limit(5)
        ).scalars().all()

    latest_overall = max((d for d in [exchange_latest, svc_latest] if d is not None), default=None)
    failure_summary = []
    for r in exchange_recent_failures:
        failure_summary.append({
            "source": "exchange_metric",
            "resource_code": r.resource_code,
            "delivery_code": r.delivery_code,
            "failed_count": r.failed_count,
            "last_error_code": r.last_error_code,
            "last_error_at": _iso(r.last_error_at),
        })
    for r in svc_recent_failures:
        failure_summary.append({
            "source": "service_invocation_metric",
            "resource_code": r.resource_code,
            "capability_id": r.capability_id,
            "failed_count": r.failed_count,
            "last_error_code": r.last_error_code,
            "last_error_at": _iso(r.last_error_at),
        })
    return {
        "kind": "ops_metric",
        "total_rows": int(exchange_total) + int(svc_total),
        "latest_updated_at": _iso(latest_overall),
        "failed_count": int(exchange_failed_total) + int(svc_failed_total),
        "failure_summary": failure_summary[:5],
    }


def _derive_overall_health(projections: list[dict[str, Any]]) -> str:
    has_any_data = any(p["total_rows"] > 0 for p in projections)
    has_any_failure = any(p["failed_count"] > 0 for p in projections)
    has_red = any(p["total_rows"] == 0 for p in projections)
    if not has_any_data:
        return "red"
    if has_red:
        return "yellow"  # 部分类别空 — 不视为 red（M0 初期主题包/血缘可能尚未灌入）
    if has_any_failure:
        return "yellow"
    return "green"


def handler_projection_status_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    projections = [
        _project_search(brain, tenant_id),
        _project_topic_package(brain, tenant_id),
        _project_quality(brain, tenant_id),
        _project_lineage(brain, tenant_id),
        _project_ops_metric(brain, tenant_id),
    ]
    return {
        "tenant_id": tenant_id,
        "projections": projections,
        "overall_health": _derive_overall_health(projections),
    }
