# Journey: J1
# Pages: P3
# Consumer-faces: API (brain.invoke_skill — 运行时直提/提交 → 受理两级全链)
# Roles: ROLE_ORGAN_OPERATER (申请人) | ROLE_BUSIAUDIT (受理第一级) | ROLE_ORGAN_MANAGER (部门审核第二级)
# Trace:
#   zw_brain/command/handlers/j1/request.py (_resolved_shared_type / _create_request / _submit_request)
#   zw_brain/command/card_session.py (Action D 写路径单源化)
#   zw_brain/domain/services/conditional_approval.py (_persist_payload)
#   .testing/debt/j1-runtime-write-path-dual-track.debt.yaml (方案 B 2026-06-11 → Action D 收账)
"""状态词汇桥接（方案 B）+ 写路径单源化（Action D）运行时 pytest.

此前运行时直提/提交单一律落旧词汇 'pending'，而 D55/P21 受理两级状态机只认
'submitted' → UI 新建的有条件共享申请受理岗无任何可办动作（单据卡死）。方案 B：

  1. 有条件 (shared_type=2) 直提/草稿提交单落 status='submitted' 进受理两级队列；
     无条件保持 'pending'（单步受理即终路径不变）。
  2. shared_type 解析链：payload 显式值 → resource.accessPolicy → resource_asset
     access_policy 回源（与申请卡投影同源口径）。
  3. 运行时单随单存档 owner_org_code（R11 方向 guard 对空 owner fail-closed，
     缺位则二级部门审核对任何管理员 403、单据永卡 dept_approved）。
  4. （Action D 收账）内存快照行整体退役——application_record 即唯一真相，
     状态机迁移直接落库，凭据自动签发 hook / 待办投影读库无陈旧态。

数据隔离：临时 DB + ensure_runtime_schema()；资源行直接注入内存 discovery（
resolve_resource_for_application 的读源），不触真实 seed 库。
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_PROVIDER = "ORG-B-MARKET-REG"


@pytest.fixture()
def brain(monkeypatch: pytest.MonkeyPatch):
    """Fresh temp DB + brain bound to it（同 test_wave0_j1_approval_conditional_runtime 模式）。"""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "conditional_status_bridge.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()

        import zw_brain.shared.audit as audit_bus
        from zw_brain.command.brain import BrainService
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore

        ds = DatabaseStore()
        audit_bus.configure_sink(ds.append_audit_event)
        ss = StateStore(database_store=ds)
        yield BrainService(state_store=ss)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _inject_resource(brain: Any, rid: str, share_type: str) -> None:
    """注入一条内存 discovery 资源行（resolve_resource_for_application 的读源）。

    accessPolicy.shareType 即 _resolved_shared_type 解析链第二级；providerOrgId
    供 owner_org_code 存档。
    """
    brain._snapshot["discovery"]["resources"].append(
        {
            "id": rid,
            "name": f"桥接测试资源-{rid}",
            "status": "已发布",
            "lifecycleStatus": "active",
            "provider": "部门B_市场监管",
            "providerOrgId": ORG_PROVIDER,
            "accessPolicy": {"shareType": share_type, "shareTypeLabel": "有条件共享" if share_type == "2" else "无条件共享"},
            "fields": [],
            "explain": [],
            "nextHints": [],
        }
    )


def _record_status(code: str) -> str:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None, f"application_record {code} 应存在（运行时单直写落库）"
    return rec.status


def _record_payload(code: str) -> dict[str, Any]:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None, f"application_record {code} 应存在（运行时单直写落库）"
    return dict(rec.payload_json or {})


def _direct_submit(brain: Any, rid: str) -> dict[str, Any]:
    out = invoke_trusted(
        brain,
        "application.resource.submit",
        {"resource_id": rid, "confirmed": True, "purpose": "桥接测试", "query": "bridge"},
        role="ROLE_ORGAN_OPERATER",
    )
    return out["result"] if "result" in out else out


def test_conditional_direct_submit_lands_submitted(brain: Any) -> None:
    """有条件直提单落 'submitted'（受理两级入口态），且镜像 application_record 同态。"""
    _inject_resource(brain, "RES-COND-1", "2")
    res = _direct_submit(brain, "RES-COND-1")
    assert res["status"] == "submitted"
    assert _record_status(res["request_id"]) == "submitted"


def test_unconditional_direct_submit_keeps_pending(brain: Any) -> None:
    """无条件直提单保持 'pending'（单步受理即终路径不变）。"""
    _inject_resource(brain, "RES-OPEN-1", "1")
    res = _direct_submit(brain, "RES-OPEN-1")
    assert res["status"] == "pending"


def test_conditional_request_carries_owner_org_code(brain: Any) -> None:
    """运行时单随单存档 owner_org_code（R11 方向 guard 的 owner 源，空则二级永 403）。"""
    _inject_resource(brain, "RES-COND-2", "2")
    res = _direct_submit(brain, "RES-COND-2")
    payload = _record_payload(res["request_id"])
    assert payload.get("owner_org_code") == ORG_PROVIDER
    assert payload.get("sharedType") == 2


def test_conditional_draft_submit_lands_submitted(brain: Any) -> None:
    """G2 草稿路径：request.create（draft）→ request.submit → 有条件落 'submitted'。"""
    _inject_resource(brain, "RES-COND-3", "2")
    created = invoke_trusted(
        brain,
        "request.create",
        {"resource_id": "RES-COND-3", "confirmed": True, "query": "桥接草稿"},
        role="ROLE_ORGAN_OPERATER",
    )
    cres = created["result"] if "result" in created else created
    assert cres["status"] == "draft"
    submitted = invoke_trusted(
        brain,
        "request.submit",
        {"request_id": cres["request_id"], "confirmed": True},
        role="ROLE_ORGAN_OPERATER",
    )
    sres = submitted["result"] if "result" in submitted else submitted
    assert sres["status"] == "submitted"


def test_single_step_review_rejects_conditional(brain: Any) -> None:
    """D55/P21 挡板：单步受理（application.resource.review）拒收有条件单。

    无挡板则 BUSIAUDIT 可 API 直调单步 approve_reuse 把有条件单直接 granted，
    绕过部门审核二级（连带绕过 R11 方向 + self-approval guard）。
    """
    from zw_brain.domain.errors import InvalidStateError

    _inject_resource(brain, "RES-COND-5", "2")
    res = _direct_submit(brain, "RES-COND-5")
    with pytest.raises(InvalidStateError, match="受理两级"):
        invoke_trusted(
            brain,
            "application.resource.review",
            {"request_id": res["request_id"], "decision": "approve", "confirmed": True},
            role="ROLE_BUSIAUDIT",
        )
    # 单据未被旁路放行，仍在受理队列。
    assert _record_status(res["request_id"]) == "submitted"


def test_two_stage_chain_on_runtime_minted_request(brain: Any) -> None:
    """UI 新建有条件单全链：直提(submitted) → 受理(dept_approved) → 部门审核(granted)。

    终审响应必须干净返回（Action D：application_record 即唯一真相，凭据自动签发
    hook 与待办投影读库，不存在陈旧内存行可炸 409）。
    """
    _inject_resource(brain, "RES-COND-4", "2")
    res = _direct_submit(brain, "RES-COND-4")
    req_id = res["request_id"]

    accepted = invoke_trusted(
        brain,
        "application.platform_approve",
        {"request_id": req_id, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    ares = accepted["result"] if "result" in accepted else accepted
    assert ares["status"] == "dept_approved"
    # DB 即时同态（管理员待办投影 / 凭据 hook 的读源）。
    assert _record_status(req_id) == "dept_approved"

    granted = invoke_trusted(
        brain,
        "application.dept_approve",
        {"request_id": req_id, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        snapshot=actor_snapshot("ROLE_ORGAN_MANAGER", org_code=ORG_PROVIDER),
    )
    gres = granted["result"] if "result" in granted else granted
    assert gres["status"] == "granted"
    assert _record_status(req_id) == "granted"
    # 凭据自动签发 hook 全链兑现（终审即签，AK-SELF 自签口径）。
    # Action D：secret 不落库——DB 只存签发事实，凭据本体读时确定性重导出；
    # 经真实消费面 credential.query 验证（与 P4 凭据领取页同源）。
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    task = DeliveryRepository().get_task_by_application_code(req_id, tenant_id=TENANT)
    assert task is not None
    grant_snapshot = (task.payload_json or {}).get("accessGrantSnapshot") or {}
    assert grant_snapshot.get("issued_audit_id"), "终审后应留有签发事实"
    assert not grant_snapshot.get("credential"), "secret 不得落库（safe_json 剥除）"
    queried = invoke_trusted(
        brain, "credential.query", {"request_id": req_id}, role="ROLE_ORGAN_OPERATER"
    )
    qres = queried["result"] if "result" in queried else queried
    assert qres.get("status") == "issued"
    assert (qres.get("credential") or {}).get("app_key", "").startswith("AK-SELF"), "读时应重导出 AK-SELF 凭据"
