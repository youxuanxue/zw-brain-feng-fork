"""Web UI snapshot redaction — align server-side preload with shell / ZW_PAGE_ACCESS.

Full runtime state remains in :meth:`zw_brain.command.brain.BrainService.snapshot` for
DB sync and tests; only ``system.snapshot`` / ``GET /api/snapshot`` serve this shape.
"""

from __future__ import annotations

import copy
from typing import Any

# Mirrors zw-brain-web/js/pages.js `window.ZW_PAGE_ACCESS` — update both when nav roles change.
_DISCOVERY = frozenset({"r1", "r2", "r6", "r7", "r8"})
_REQUEST = frozenset({"r1", "r2", "r3", "r4", "r5"})
_DELIVERY = frozenset({"r2", "r5", "r6", "r7", "r8"})
_PROVIDER = frozenset({"r6", "r7"})
_COMPLIANCE = frozenset({"r2", "r5", "r6", "r7", "r8"})
_ZONES = frozenset({"r1", "r2", "r6", "r7", "r8"})
_CAPABILITY = frozenset({"r7"})
_OPS = frozenset({"r7"})

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
