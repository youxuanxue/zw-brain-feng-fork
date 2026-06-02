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
    # C-1 删演示单后 seed 无演示申请；本测试关注 todo status 必须中文化（非 slug 泄漏），
    # 自注入合成申请（非 demo-id）使 _sync_request_todos 产出 todos 再校验本意。
    brain._snapshot["requests"] = [
        {"id": "REQ-TEST-WB-1", "status": "approved", "resourceName": "测试资源甲"},
        {"id": "REQ-TEST-WB-2", "status": "pending", "resourceName": "测试资源乙"},
        {"id": "REQ-TEST-WB-3", "status": "in_delivery", "resourceName": "测试资源丙"},
    ]
    brain._sync_request_todos()
    wb = brain._snapshot["workbench"]["ROLE_ORGAN_OPERATER"]
    statuses = [str(t["status"]) for t in wb["todos"]]
    assert statuses, "expected synced todos for organ operater"
    leaked = [s for s in statuses if _SLUG.match(s)]
    assert not leaked, f"workbench todo status must be localized, got slugs: {leaked}"
