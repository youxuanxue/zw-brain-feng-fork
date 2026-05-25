"""工作台待办 status 必须面向用户的中文文案，禁止泄漏请求状态机 slug。"""

from __future__ import annotations

import re

from zw_brain.command.brain import BrainService
from zw_brain.shared.state_store import StateStore

_SLUG = re.compile(r"^[a-z][a-z0-9_-]*$")


def _brain() -> BrainService:
    return BrainService(state_store=StateStore())


def test_request_status_text_maps_delivery_states() -> None:
    brain = _brain()
    approved = {"status": "approved"}
    in_delivery = {"status": "in_delivery"}
    assert brain._request_status_text(approved, "applicant") == "已通过"
    assert brain._request_status_text(in_delivery, "applicant") == "交付中"
    assert brain._request_status_text({"status": "granted"}, "applicant") == "已授权"
    assert brain._request_status_text({"status": "revoked"}, "applicant") == "已撤销"


def test_workbench_todos_never_expose_raw_request_slugs() -> None:
    brain = _brain()
    brain._sync_request_todos()
    wb = brain._snapshot["workbench"]["ROLE_ORGAN_OPERATER"]
    statuses = [str(t["status"]) for t in wb["todos"]]
    assert statuses, "expected synced todos for organ operater"
    leaked = [s for s in statuses if _SLUG.match(s)]
    assert not leaked, f"workbench todo status must be localized, got slugs: {leaked}"
