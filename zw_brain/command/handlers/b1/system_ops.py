"""B1 system_ops handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.domain.schemas import describe_schemas
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _toggle_outage(brain, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        brain._ui_state["brainOutage"] = not brain._ui_state["brainOutage"]
        brain._append_audit_feed(
            "dashboard.snapshot-toggle",
            "brain",
            "warning" if brain._ui_state["brainOutage"] else "ok",
            actor,
        )
        return {"brainOutage": brain._ui_state["brainOutage"]}

    return brain._mutate("system.toggle_outage", role, confirmed, {}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_system_toggle_outage(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _toggle_outage(brain, str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

def handler_system_snapshot(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return redact_webui_snapshot(brain.snapshot(), str(payload.get("role", brain._ui_state.get("role", "ROLE_ORGAN_OPERATER"))))

def handler_system_schema_info(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return {"schemas": describe_schemas()}

