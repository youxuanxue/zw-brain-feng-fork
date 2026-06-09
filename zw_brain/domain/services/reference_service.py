"""ReferenceService — 参照主数据只读查询（机构/区划/字典）。

确定性带出的真源封装：复用既有 OrgProjection/RegionProjection（governance.py 已从
pub_organ/pub_region 真导入，~1.8 万机构）+ DictProjection（pub_dict KIND 枚举字典，
阶段1 新增）。本服务只读，供 field_derivation 派生引擎与前端选择器调用。

返回 plain dict（非 ORM Record），便于派生引擎与序列化层无 ORM 依赖地使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


@dataclass
class ReferenceService:
    """机构/区划/字典参照查询（只读）。"""

    repo: GovernanceProjectionRepository = field(default_factory=GovernanceProjectionRepository)

    def organ(self, org_code: str, *, tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any] | None:
        """选机构 → 带出名称 + 所属区划（带出核心）。未命中返回 None（fail-soft）。"""
        if not org_code:
            return None
        rec = self.repo.get_org_by_code(str(org_code), tenant_id=tenant_id)
        if rec is None:
            return None
        profile = rec.profile_json or {}
        return {
            "org_code": rec.org_code,
            "org_name": rec.org_name,
            "parent_org_code": rec.parent_org_code,
            "region_code": rec.region_code,
            # region_name 优先以区划表为权威，回落机构行自带名称。
            "region_name": self._region_name(rec.region_code, tenant_id) or profile.get("region_name"),
            "source_ref": rec.source_ref,
        }

    def region(self, region_code: str, *, tenant_id: str = _DEFAULT_TENANT_ID) -> dict[str, Any] | None:
        if not region_code:
            return None
        rec = self.repo.get_region_by_code(str(region_code), tenant_id=tenant_id)
        if rec is None:
            return None
        return {
            "region_code": rec.region_code,
            "region_name": rec.region_name,
            "parent_region_code": rec.parent_region_code,
            "region_level": rec.region_level,
            "source_ref": rec.source_ref,
        }

    def region_children(self, parent_region_code: str, *, tenant_id: str = _DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
        """区划树逐级下钻：某区划的直接下级。"""
        return [
            {"code": r.region_code, "name": r.region_name, "parent_code": r.parent_region_code}
            for r in self.repo.list_region_children(str(parent_region_code), tenant_id=tenant_id)
        ]

    def search_organ(
        self,
        *,
        keyword: str = "",
        region_code: str = "",
        offset: int = 0,
        limit: int = 20,
        tenant_id: str = _DEFAULT_TENANT_ID,
    ) -> dict[str, Any]:
        """机构选择器搜索分页：keyword 模糊 + 可选区划过滤 → 当前页 options + total。"""
        rows, total = self.repo.search_orgs(
            keyword=keyword, region_code=region_code, offset=offset, limit=limit, tenant_id=tenant_id
        )
        return {
            "options": [{"code": o.org_code, "name": o.org_name, "region_code": o.region_code} for o in rows],
            "total": total,
        }

    def dict_options(self, dict_type: str, *, tenant_id: str = _DEFAULT_TENANT_ID, parent_code: str | None = None) -> list[dict[str, Any]]:
        """枚举字段 options：某字典分组（KIND，如 organLine）下的 code↔name 列表。"""
        return [
            {"code": d.code, "name": d.name, "parent_code": d.parent_code}
            for d in self.repo.list_dicts(str(dict_type), tenant_id=tenant_id, parent_code=parent_code)
        ]

    def _region_name(self, region_code: str | None, tenant_id: str) -> str | None:
        if not region_code:
            return None
        rec = self.repo.get_region_by_code(str(region_code), tenant_id=tenant_id)
        return rec.region_name if rec else None
