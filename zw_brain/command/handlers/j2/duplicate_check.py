"""J2 catalog.duplicate.check — F3 发布前轻量重复率检测（非硬拦）。

匹配维度（最小可用集合，覆盖 90% 真实重复）：
  - title：与本 catalog 完全相等的其他 active / approved_pending_publish 目录；
  - region+org：同 region_code + 同 owner_org_id 且非自身的其他目录。

更高级的模糊匹配 / Embedding similarity 不在 F3 scope（归 R14 三引擎或 ML stage）。
本 handler 只读 catalog_repo.list_entries，不写状态、不做合并、不抛阻拦异常。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.brain import NotFoundError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def _candidate_lifecycle(record: Any) -> bool:
    return record.lifecycle_status in {"active", "approved_pending_publish", "pending_platform_review", "pending_review"}


def check_catalog_duplicate(brain: BrainService, catalog_code: str) -> dict[str, Any]:
    """Pure helper — read-only, no audit. Used both by the standalone skill and by
    `handler_catalog_entry_publish` to inline-attach `duplicate_warnings` to publish result."""
    store = brain._state_store.database_store
    repo = store.catalog_repo if store is not None else CatalogRepository()
    target = repo.get_entry(catalog_code, tenant_id=_DEFAULT_TENANT_ID)
    if target is None:
        raise NotFoundError(catalog_code)
    title = (target.title or "").strip()
    region = (target.region_code or "").strip()
    owner_org = (target.owner_org_id or "").strip()

    warnings: list[dict[str, Any]] = []
    for record in repo.list_entries(tenant_id=_DEFAULT_TENANT_ID):
        if record.catalog_code == target.catalog_code:
            continue
        if not _candidate_lifecycle(record):
            continue
        dims: list[str] = []
        if title and (record.title or "").strip() == title:
            dims.append("title")
        if (
            region
            and owner_org
            and (record.region_code or "").strip() == region
            and (record.owner_org_id or "").strip() == owner_org
        ):
            dims.append("region+org")
        if dims:
            warnings.append(
                {
                    "catalog_code": record.catalog_code,
                    "title": record.title,
                    "region_code": record.region_code,
                    "owner_org_id": record.owner_org_id,
                    "lifecycle_status": record.lifecycle_status,
                    "match_dimensions": dims,
                }
            )
    return {
        "catalog_code": catalog_code,
        "duplicate_warnings": warnings,
        "total": len(warnings),
    }


def handler_catalog_duplicate_check(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return check_catalog_duplicate(brain, str(payload["catalog_code"]))
