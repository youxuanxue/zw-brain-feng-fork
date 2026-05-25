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
_REQUEST = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"})
_DELIVERY = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
_PROVIDER = frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
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
    if role not in _PROVIDER:
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
