"""G2 复用申请草稿态 — in-memory request.create → draft → submit 状态机守卫.

0605 反馈 6.4#8：P2「申请资源」此前一键直接提交（status=pending），用户没有「先看草稿、
确认无误再提交」的机会。本守卫钉死新状态机：

  - request.create（P2 走查入口）→ status='draft'，**不触发审批工作流**（草稿不进审批）。
  - 同资源重复 request.create → 幂等重入既有草稿（reused_draft），不刷出一堆草稿单。
  - request.submit（用户确认）→ draft → 'pending'，此刻才启动审批工作流。
  - application.resource.submit（供方直提路径，如受理起草）→ 仍直接 'pending'（行为不变）。
  - 非可提交态（如已 pending）再 submit → 拒绝。
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.domain.errors import BrainServiceError

_RESOURCE_ID = "res-g2-draft"
_OPERATER = "ROLE_ORGAN_OPERATER"


def _unwrap(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and "result" in result and isinstance(result["result"], dict):
        return result["result"]
    return result  # type: ignore[return-value]


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """全功能 brain（写路径需 durable audit sink + 运行时 DB），temp SQLite 隔离不污染主库。"""
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("ZW_BRAIN_AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    from zw_brain.command import runtime as runtime_mod
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.audit import store as audit_store_mod

    audit_store_mod.set_default_store(None)
    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()

    service = runtime_mod.get_service()
    # 注入一条可申请的发现资源，供 resolve_resource_for_application 命中。
    service._snapshot["discovery"]["resources"].append(
        {
            "id": _RESOURCE_ID,
            "name": "G2 草稿测试资源",
            "status": "可复用",
            "provider": "测试部门",
            "repository": {"shared_type": "1"},
        }
    )
    yield service

    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_store_mod.set_default_store(None)


def test_request_create_lands_draft_no_approval(brain) -> None:
    out = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    assert out["status"] == "draft", out
    # 草稿不触发审批工作流。
    assert "approval_case_id" not in out
    # Action D：application_record 单一事实源里申请单确为 draft。
    store = brain._state_store.database_store
    rec = store.application_repo.get_record(out["request_id"], tenant_id="sd-default")
    assert rec is not None and rec.status == "draft"


def test_repeat_create_reuses_existing_draft(brain) -> None:
    first = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    second = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    assert second.get("reused_draft") is True
    assert second["request_id"] == first["request_id"]
    # 只有一张草稿单（没有刷出第二张）——DB 现算。
    store = brain._state_store.database_store
    drafts = [
        r for r in store.application_repo.list_records(tenant_id="sd-default")
        if (r.payload_json or {}).get("resourceId") == _RESOURCE_ID and r.status == "draft"
    ]
    assert len(drafts) == 1


def test_draft_submit_transitions_to_pending(brain) -> None:
    created = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    rid = created["request_id"]
    submitted = _unwrap(invoke_trusted(brain, "request.submit", {"request_id": rid, "confirmed": True}, role=_OPERATER))
    assert submitted["status"] == "pending", submitted
    store = brain._state_store.database_store
    rec = store.application_repo.get_record(rid, tenant_id="sd-default")
    assert rec is not None and rec.status == "pending"
    # 提交后时间线含「已提交申请」（payload 卡随写落库）。
    labels = [t.get("label") for t in (rec.payload_json or {}).get("timeline", [])]
    assert "已提交申请" in labels


def test_approval_workflow_starts_at_submit_not_create(brain, monkeypatch) -> None:
    """审批触发点从 create 搬到 submit（D49 触发点搬移）：草稿创建**不**调审批 hook，
    用户确认提交（draft→pending）时才恰好调一次。spy 替身锁死「移动」契约，不依赖
    baseline schema 在 temp 库能否解析（解析与否是另一条覆盖线）。"""
    import zw_brain.command.handlers.j1.request as request_mod

    calls: list[str] = []

    def _spy(*, application_code: str, **_kw: Any) -> str:
        calls.append(application_code)
        return f"case-{application_code}"

    monkeypatch.setattr(request_mod, "_maybe_start_approval_workflow", _spy)

    created = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    assert calls == [], "草稿创建不应触发审批工作流"
    rid = created["request_id"]

    submitted = _unwrap(invoke_trusted(brain, "request.submit", {"request_id": rid, "confirmed": True}, role=_OPERATER))
    assert calls == [rid], "确认提交时应恰好触发一次审批工作流（且作用于该申请单）"
    assert submitted.get("approval_case_id") == f"case-{rid}"


def test_submit_rejects_already_pending(brain) -> None:
    created = _unwrap(invoke_trusted(brain, "request.create", {"resource_id": _RESOURCE_ID, "confirmed": True}, role=_OPERATER))
    rid = created["request_id"]
    invoke_trusted(brain, "request.submit", {"request_id": rid, "confirmed": True}, role=_OPERATER)
    # 已 pending，再次 submit 应被拒（非可提交态）。
    with pytest.raises(BrainServiceError):
        invoke_trusted(brain, "request.submit", {"request_id": rid, "confirmed": True}, role=_OPERATER)


def test_application_resource_submit_still_direct_pending(brain) -> None:
    """供方直提路径（application.resource.submit）保持直接 pending，不走草稿。"""
    out = _unwrap(
        invoke_trusted(
            brain,
            "application.resource.submit",
            {"resource_id": _RESOURCE_ID, "purpose": "供方受理直提", "confirmed": True},
            role=_OPERATER,
        )
    )
    assert out["status"] == "pending", out
