"""Web UI snapshot redaction — align server-side preload with shell / ZW_PAGE_ACCESS.

Full runtime state remains in :meth:`zw_brain.command.brain.BrainService.snapshot` for
DB sync and tests; only ``system.snapshot`` / ``GET /api/snapshot`` serve this shape.
"""

from __future__ import annotations

import copy
from typing import Any

# D23 (2026-05-19): R1-R8 退役。Mirrors zw-brain-web/js/pages.js `window.ZW_PAGE_ACCESS` — update both when nav roles change.
# 新角色码：ROLE_BUSIAUDIT / ROLE_ORGAN_MANAGER / ROLE_ORGAN_OPERATER / ROLE_SECURITY_ADMIN / ROLE_SECURITY_AUDIT / ROLE_SYSTEM
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
# MANAGER/BUSIAUDIT 进所有 /provider/inbox/*；OPERATER 只进 /provider + /provider/wizard/inline-catalog，
# wizard 提交后 P5Provider 顶层展示「我的目录」，故只需 catalogs。
_PROVIDER_FULL = frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
_PROVIDER_PARTIAL = frozenset({"ROLE_ORGAN_OPERATER"})
_PROVIDER_PARTIAL_KEYS = frozenset({"catalogs"})
_COMPLIANCE = frozenset(
    {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM"}
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
