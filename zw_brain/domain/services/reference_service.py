"""ReferenceService — 参照主数据只读查询（机构/区划/字典）。

确定性带出的真源封装：复用既有 OrgProjection/RegionProjection（governance.py 已从
pub_organ/pub_region 真导入，~1.8 万机构）+ DictProjection（pub_dict KIND 枚举字典，
阶段1 新增）。本服务只读，供 field_derivation 派生引擎与前端选择器调用。

返回 plain dict（非 ORM Record），便于派生引擎与序列化层无 ORM 依赖地使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

# 部门数据可见域角色划分（D55/D52 角色码；与 ops_service._scope_invocations_for_manager 同口径）：
# 全局角色不受部门收口（业务运营员/平台运维员/安全审计员 = v5 平台级口径，见全量）；
# 仅部门管理员 / 部门操作员按机构收口。其余未知角色按最小权限当部门角色处理（仅本机构）。
_GLOBAL_SCOPE_ROLES = frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM", "ROLE_SECURITY_AUDIT"})
_DEPT_MANAGER_ROLE = "ROLE_ORGAN_MANAGER"
_MAX_ORG_TREE_DEPTH = 64  # 下级递归保险栓：父链脏数据成环时兜底，避免无限下钻。
_MACHINE_ORG_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,}$")


@dataclass
class ReferenceService:
    """机构/区划/字典参照查询（只读）。"""

    repo: GovernanceProjectionRepository = field(default_factory=GovernanceProjectionRepository)
    # 实例级 resolve memo（消 N+1）：参照主数据（org_projection）在单次只读快照内稳定不变，
    # 同一机构名/码被 N 行×多个面反复 resolve_org_code（每次最多 2 次 DB 点查）是部门角色快照
    # ~5x 慢的主因。实例短命（每次 enrich / 每个快照新建），memo 仅在该实例生命周期内复用、
    # 不跨快照/不跨 DB，故无陈旧风险；重名→None 的 fail-closed 结果照常缓存。键=(tenant_id, 原值)。
    _resolve_memo: dict[tuple[str, str], str | None] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

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

    def resolve_org_code(self, value: str | None, *, tenant_id: str = _DEFAULT_TENANT_ID) -> str | None:
        """机构名/码归一到**码**：投影命中码 → 直通；按名精确唯一命中 → 翻码；
        未知/重名歧义 → None（fail-soft，由调用方决定 fail-closed 后果）。

        背景（债 legacy-catalog-owner-org-name-mismatch）：legacy 导入的目录 owner_org_id
        存机构名（如「省大数据局」），资源侧用统一社会信用代码——同机构裸字符串比对必然不等。
        归一只认参照主数据（org_projection），不做模糊匹配。

        实例级 memo（见 _resolve_memo 注释）：同一 (tenant_id, 原值) 在本实例生命周期内只查一次
        DB，消除部门隔离行级过滤的 N+1。
        """
        v = str(value or "").strip()
        if not v:
            return None
        key = (str(tenant_id), v)
        memo = self._resolve_memo
        if key in memo:
            return memo[key]
        if self.repo.get_org_by_code(v, tenant_id=tenant_id) is not None:
            result: str | None = v
        else:
            rows = self.repo.list_orgs_by_name(v, tenant_id=tenant_id)
            result = rows[0].org_code if len(rows) == 1 else None
        memo[key] = result
        return result

    def display_org_name(self, value: str | None, *, tenant_id: str = _DEFAULT_TENANT_ID) -> str:
        """机构展示名只从 org_projection 解析。

        ``value`` 可是机构码，也可是不规范旧数据里落入 owner 字段的机构名；命中投影才返回
        org_name。未知/歧义时返回空串，调用方展示空态，避免把机构码当可读名称漏到页面。
        """
        v = str(value or "").strip()
        if not v:
            return ""
        rec = self.repo.get_org_by_code(v, tenant_id=tenant_id)
        if rec is not None:
            return str(rec.org_name or "")
        if _MACHINE_ORG_TOKEN_RE.fullmatch(v):
            return ""
        rows = self.repo.list_orgs_by_name(v, tenant_id=tenant_id)
        return str(rows[0].org_name or "") if len(rows) == 1 else ""

    def org_name_resolver(self, *, tenant_id: str = _DEFAULT_TENANT_ID):
        """返回带 memo 的 org_projection 展示名解析器，供列表投影消除 N+1 重复点查。"""
        cache: dict[str, str] = {}

        def resolve(value: Any) -> str:
            v = str(value or "").strip()
            if not v:
                return ""
            if v not in cache:
                cache[v] = self.display_org_name(v, tenant_id=tenant_id)
            return cache[v]

        return resolve

    def visible_org_codes(
        self, actor_org_code: str, role: str, *, tenant_id: str = _DEFAULT_TENANT_ID
    ) -> set[str] | None:
        """部门数据可见机构集（「本机构 + 下级」），三态返回，调用方据此 fail-closed：

        - ``None``           → 全局角色（业务运营员/平台运维员/安全审计员）：不限定，放行全量。
        - ``{actor_org, …}`` → 部门角色且有机构上下文：本机构 +（管理员才有的）下级机构。
        - ``set()``（空集）   → 部门角色但缺机构上下文：fail-closed 信号，调用方返空列表/0 计数。

        下级语义：部门管理员见本机构子树（list_org_children 递归），部门操作员仅本机构。
        当前 org_projection.parent_org_code 全空（legacy pub_organ_tree.PARENT_CODE 未导入），
        故子树恒为 {actor_org}；待父子树填充后下级自动展开，本方法与所有调用方零改动。
        与 ops_service._scope_invocations_for_manager（D57⑥）同一收口范式。
        """
        role_code = str(role or "")
        if role_code in _GLOBAL_SCOPE_ROLES:
            return None
        org = str(actor_org_code or "")
        if not org:
            return set()
        visible: set[str] = {org}
        if role_code == _DEPT_MANAGER_ROLE:
            frontier = [org]
            depth = 0
            while frontier and depth < _MAX_ORG_TREE_DEPTH:
                children: list[str] = []
                for parent in frontier:
                    for child in self.repo.list_org_children(parent, tenant_id=tenant_id):
                        code = str(child.org_code or "")
                        if code and code not in visible:
                            visible.add(code)
                            children.append(code)
                frontier = children
                depth += 1
        return visible

    def org_in_scope(
        self, owner_value: str | None, visible_org_codes: set[str] | None, *, tenant_id: str = _DEFAULT_TENANT_ID
    ) -> bool:
        """行级成员判定：某行的 owner（机构码或机构名）是否落在部门可见域内。

        visible_org_codes 语义同 :meth:`visible_org_codes` 返回值：
          - None  → 全局放行（不过滤），恒 True；
          - 空集  → fail-closed，恒 False；
          - 非空集 → 行 owner 归一到码后判成员。

        owner 归一（债 legacy-catalog-owner-org-name-mismatch）：legacy 行 owner 可能存
        机构**名**而资源侧存统一社会信用**代码**，裸比对必不等。先走「裸值命中」快路径
        （绝大多数行 owner 本就是码、零 DB），未命中再 resolve_org_code 归一到码兜底。
        """
        if visible_org_codes is None:
            return True
        if not visible_org_codes:
            return False
        raw = str(owner_value or "")
        if raw and raw in visible_org_codes:
            return True
        code = self.resolve_org_code(raw, tenant_id=tenant_id)
        return bool(code) and code in visible_org_codes

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
