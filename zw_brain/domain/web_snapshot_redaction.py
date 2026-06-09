"""Web UI snapshot redaction — align server-side preload with shell / ZW_PAGE_ACCESS.

Full runtime state remains in :meth:`zw_brain.command.brain.BrainService.snapshot` for
DB sync and tests; only ``system.snapshot`` / ``GET /api/snapshot`` serve this shape.
"""

from __future__ import annotations

import copy
from typing import Any

# D23 (2026-05-19): R1-R8 退役。Mirrors zw-brain-web/js/pages.js `window.ZW_PAGE_ACCESS` — update both when nav roles change.
# 角色码（D55/P16 安全管理员退役后 5 业务角色）：ROLE_ORGAN_OPERATER / ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT / ROLE_SECURITY_AUDIT / ROLE_SYSTEM
_DISCOVERY = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
# ROLE_BUSIAUDIT：j1-credential-revoke 决策 A —— 业务运营员合规收回/暂停授权需在 P3 申请详情
# 操作，故须能预载 requests（与 productShellNav「办共享申请」shell 对齐）；否则 shell 进得去但
# 申请列表/详情空（lookupRequest → 未找到该申请），合规撤回入口不可达。
_REQUEST = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
_DELIVERY = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
# provider snapshot 是 "shell + sub-key" 两层鉴权：
#   _PROVIDER_FULL：见全部 sub-keys（catalogs + 各 reviewer/responder 待办）。
#   _PROVIDER_PARTIAL：只看 _PROVIDER_PARTIAL_KEYS 列出的 sub-keys（J2 在线编制 OPERATER 视角）。
#   其他 role：整个 provider dict empty。
# 与 zw-brain-web/src/lib/pageAccess.ts ROUTE_ROLE_OVERRIDES 对齐：
# MANAGER/BUSIAUDIT 进所有 /provider/inbox/*；OPERATER 进 /provider + /provider/wizard/inline-catalog
# + /provider/wizard/api-service，wizard 提交后 P5Provider/列表展示「我的目录」「我的 API 服务」，
# 故 OPERATER 需 catalogs + services（D54 GATE-1：代理服务注册 = 部门操作员 + 部门管理员；
# 操作员注册后须能看到并提交自己的 API 服务草稿）。
# 另需 resources：T9 供数侧「资源管理清单」只读浏览岗位含部门操作员（业务方 2026-06-09——操作员=
# 挂接/编制者也需看本部门已挂接资源跟踪状态），故操作员 snapshot 须带 provider.resources（只读，
# 无行内管理动作；与 requestFlowRoles.PROVIDER_ASSET_VIEWER_ROLES 对齐）。
_PROVIDER_FULL = frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
_PROVIDER_PARTIAL = frozenset({"ROLE_ORGAN_OPERATER"})
_PROVIDER_PARTIAL_KEYS = frozenset({"catalogs", "services", "resources"})
_COMPLIANCE = frozenset(
    # ROLE_SECURITY_ADMIN 随安全管理员本期退役而移除（D55/P16）。
    {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"}
)
_ZONES = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
_CAPABILITY = frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"})
_OPS = frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"})

_EMPTY_DISCOVERY: dict[str, Any] = {
    "zones": [],
    "resources": [],
    "catalogTree": [],
    "aiCopilot": {
        "summary": "",
        "missingQuestions": [],
        "nextActions": [],
        "evidence": [],
    },
}

_EMPTY_PROVIDER: dict[str, Any] = {
    "overview": [],
    "catalogs": [],
    "resources": [],
    "services": [],
    "field_decisions": [],
    "hookup_reviews": [],
    "demand_matches": [],
    "objection_cases": [],
    "aiGovernance": {
        "summary": "",
        "priorities": [],
        "draft": "",
        "evidence": [],
    },
}

_EMPTY_AUDIT_AI: dict[str, Any] = {"summary": "", "evidence": []}


def redact_webui_snapshot(full: dict[str, Any], role: str) -> dict[str, Any]:
    """Deep-copy *full* and clear collections the given Web UI role must not preload."""
    out = copy.deepcopy(full)
    if role not in _DISCOVERY:
        out["discovery"] = copy.deepcopy(_EMPTY_DISCOVERY)
    if role not in _REQUEST:
        out["requests"] = []
        out["approvals"] = []
    if role not in _DELIVERY:
        out["delivery_tasks"] = []
    if role in _PROVIDER_FULL:
        pass  # 保留完整 provider 视图
    elif role in _PROVIDER_PARTIAL:
        # 仅保留 _PROVIDER_PARTIAL_KEYS 列出的 sub-keys，其余清空到 _EMPTY_PROVIDER 默认。
        current = out.get("provider") or {}
        partial = copy.deepcopy(_EMPTY_PROVIDER)
        for key in _PROVIDER_PARTIAL_KEYS:
            if key in current:
                partial[key] = current[key]
        out["provider"] = partial
    else:
        out["provider"] = copy.deepcopy(_EMPTY_PROVIDER)
    if role not in _COMPLIANCE:
        out["disputes"] = []
        out["audit_events"] = []
        out["audit_ai"] = copy.deepcopy(_EMPTY_AUDIT_AI)
        out["alerts"] = []
        out["tickets"] = []
        out["knowledge_articles"] = []
    if role not in _ZONES:
        out["zones"] = []
    if role not in _CAPABILITY:
        out["capability_packages"] = []
    if role not in _OPS:
        out["api_resources"] = []
        out["gateway_runtime_statuses"] = []
        out["service_invocation_metrics"] = []
    return out
