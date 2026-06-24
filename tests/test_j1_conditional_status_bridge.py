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

from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_PROVIDER = "ORG-B-MARKET-REG"


@pytest.fixture()
def brain():
    """Fresh brain on the conftest-supplied isolated empty PG clone
    （同 test_wave0_j1_approval_conditional_runtime 模式）。"""
    db_module.reset_engine_cache()
    ensure_runtime_schema()

    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    yield BrainService(state_store=ss)
    db_module.reset_engine_cache()


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


# ── 0611 断点 C（修复项 R-1）：UI 新编目→挂接有条件资源→申请 全新链路两级不旁路 ──────────────


def test_ui_new_mounted_conditional_resource_full_two_stage_chain(brain: Any) -> None:
    """0611 断点 C 回归（违 D55④ 修复）：**全新链路**（在线编目→挂接有条件资源→发布→申请）
    上受理→部门审核两级不得被旁路。双根因双 pin：

      1. 写读键漂移——挂接写 access_policy_json 此前用 'shared_type'，回源读端只认
         'share_type' → 有条件资源被判无条件、受理即终；
      2. 申请单 resourceId 此前落父目录码（j2-inline-*）而非资源码 → 共享方式按
         resourceId 回源 resource_asset 全失败。

    本测试不注入内存 discovery 行——走与 UI 完全相同的 DB 回源解析链。
    """
    org = "11370000MB284651XL"
    catalog_code = "j2-inline-0611-chain"
    resource_code = "res-0611-chain-tbl"

    from zw_brain.domain.repositories.catalog import CatalogRepository

    CatalogRepository().upsert_from_resource(
        {
            "id": catalog_code,
            "name": "0611 全新链路编目目录",
            "status": "active",
            "provider": org,
        },
        tenant_id=TENANT,
    )

    # 挂接有条件（shared_type=2）库表资源 → 审核 → 发布（active）。
    invoke_trusted(
        brain,
        "resource.mount.table.prepare",
        {
            "resource_code": resource_code,
            "catalog_code": catalog_code,
            "title": "0611 全新链路库表资源",
            "owner_org_id": org,
            "table_name": "t_chain_0611",
            "connection": {"host": "db.internal", "database": "biz"},
            "field_mappings": [{"source": "name", "target": "name"}],
            "shared_type": "2",
            "shared_condition": "按授权范围共享",
            "confirmed": True,
        },
        role="ROLE_ORGAN_OPERATER",
    )
    # 写读键统一 pin：落库即用读端认的 share_type 键。
    from zw_brain.domain.repositories.resource_api import ResourceApiRepository

    asset = ResourceApiRepository().get_asset(resource_code, tenant_id=TENANT)
    assert (asset.access_policy_json or {}).get("share_type") == "2"
    assert "shared_type" not in (asset.access_policy_json or {})

    invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": resource_code, "confirmed": True}, role="ROLE_ORGAN_OPERATER")
    invoke_trusted(brain, "resource.asset.review", {"resource_code": resource_code, "decision": "approve", "confirmed": True}, role="ROLE_ORGAN_MANAGER")
    invoke_trusted(brain, "resource.asset.publish", {"resource_code": resource_code, "confirmed": True}, role="ROLE_BUSIAUDIT")

    # 申请（与发现页 applyTo 同口径：resource_id=资源码）→ 草稿 → 提交。
    created = invoke_trusted(
        brain,
        "request.create",
        {"resource_id": resource_code, "confirmed": True, "purpose": "全新链路验证"},
        role="ROLE_ORGAN_OPERATER",
    )
    cres = created["result"] if "result" in created else created
    req_id = cres["request_id"]

    payload = _record_payload(req_id)
    # 申请单必须绑定资源码（非父目录码）——共享方式回源按 resourceId 查 resource_asset。
    assert payload.get("resourceId") == resource_code
    assert payload.get("sharedType") == 2
    assert payload.get("owner_org_code") == org

    submitted = invoke_trusted(
        brain, "request.submit", {"request_id": req_id, "confirmed": True}, role="ROLE_ORGAN_OPERATER"
    )
    sres = submitted["result"] if "result" in submitted else submitted
    # 有条件单必须进受理两级队列（submitted），不得被判无条件受理即终（pending）。
    assert sres["status"] == "submitted"

    # 两级走查：受理（业务运营员）→ 部门审核（部门管理员，org=提供方）。
    accepted = invoke_trusted(
        brain,
        "application.platform_approve",
        {"request_id": req_id, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )
    ares = accepted["result"] if "result" in accepted else accepted
    assert ares["status"] == "dept_approved"

    granted = invoke_trusted(
        brain,
        "application.dept_approve",
        {"request_id": req_id, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        snapshot=actor_snapshot("ROLE_ORGAN_MANAGER", org_code=org),
    )
    gres = granted["result"] if "result" in granted else granted
    assert gres["status"] == "granted"
    assert _record_status(req_id) == "granted"
