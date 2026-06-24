"""工作台待办 status 必须面向用户的中文文案，禁止泄漏请求状态机 slug。"""

from __future__ import annotations

import re

import pytest

from zw_brain.command.brain import BrainService
from zw_brain.shared.state_store import StateStore

_SLUG = re.compile(r"^[a-z][a-z0-9_-]*$")


def _brain() -> BrainService:
    return BrainService(state_store=StateStore())


def _db_brain() -> BrainService:
    """库后端 brain（Action D：待办投影按 application_record 现算，需真库）。

    绑定 conftest autouse fixture 注入的每测试独立空 PG 克隆库；
    ensure_runtime_schema() 建表。
    """
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    return BrainService(state_store=StateStore(database_store=DatabaseStore()))


@pytest.mark.no_db
def test_request_status_text_maps_delivery_states() -> None:
    brain = _brain()
    approved = {"status": "approved"}
    in_delivery = {"status": "in_delivery"}
    assert brain._request_status_text(approved, "applicant") == "已通过"
    assert brain._request_status_text(in_delivery, "applicant") == "交付中"
    assert brain._request_status_text({"status": "granted"}, "applicant") == "已授权"
    assert brain._request_status_text({"status": "revoked"}, "applicant") == "已撤销"


def test_workbench_todos_never_expose_raw_request_slugs() -> None:
    # C-1 删演示单后 seed 无演示申请；本测试关注 todo status 必须中文化（非 slug 泄漏），
    # 自注入合成申请（非 demo-id）使 _sync_request_todos 产出 todos 再校验本意。
    # Action D：待办投影按 application_record 现算——注入走 DB upsert。
    brain = _db_brain()
    store = brain._state_store.database_store
    for rid, status, name in (
        ("REQ-TEST-WB-1", "approved", "测试资源甲"),
        ("REQ-TEST-WB-2", "pending", "测试资源乙"),
        ("REQ-TEST-WB-3", "in_delivery", "测试资源丙"),
    ):
        store.application_repo.upsert_from_request(
            {"id": rid, "status": status, "resourceName": name, "applicant": "测试人", "applicantDept": "测试单位"},
            tenant_id="sd-default",
        )
    brain._sync_request_todos()
    wb = brain._snapshot["workbench"]["ROLE_ORGAN_OPERATER"]
    statuses = [str(t["status"]) for t in wb["todos"]]
    assert statuses, "expected synced todos for organ operater"
    leaked = [s for s in statuses if _SLUG.match(s)]
    assert not leaked, f"workbench todo status must be localized, got slugs: {leaked}"
