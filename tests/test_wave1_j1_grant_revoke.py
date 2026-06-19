# Wave: 1
# Journey: J1
# Pages: P3 / P4
# Consumer-faces: API (brain.invoke_skill) | WebUI
# Roles: ROLE_BUSIAUDIT (审批人)
# Trace:
#   zw_brain/command/handlers/j1/application_grant.py
#   .testing/waves/wave-1-j1-j2-closed-loop/features/j1-credential-revoke.feature
"""J1 撤回 / 暂停授权 — H4 修复回归。

H4 旧 bug：_suspend / _revoke 仅当 request_id 以 "REQ-" 开头时才 find_by_id，
否则 request=None、跳过主体却仍返回 {"revoked": True} + 写 "ok" 审计 —— 撤回一个
不存在的授权会"假成功"。本测试守住：
  1) 撤回 / 暂停真实存在的授权 → 状态真落库 + 审计为 ok；
  2) 撤回 / 暂停不存在的申请号 → 抛 NotFoundError，不假成功、不写 ok 审计；
  3) 缺省申请号 → 抛 InvalidStateError；
  4) 已撤回再撤回（撤回不可逆）→ 抛 InvalidStateError。

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义），真实 sd-default 资源作锚。
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from tests._trusted_payload import invoke_trusted
from zw_brain.shared.db import get_database_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def _pg_read(sql: str, params: tuple = ()):
    """Read against the cloned realistic PG (app read-path's DB), never a file."""
    url = make_url(get_database_url())
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username,
        password=url.password, dbname=url.database,
    ) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture(scope="module")
def real_resource() -> dict:
    rows = _pg_read(
        "SELECT catalog_code, title FROM catalog_entry "
        "WHERE tenant_id=%s ORDER BY catalog_code LIMIT 1",
        (TENANT,),
    )
    assert rows, "realistic PG 应含 catalog_entry"
    row = rows[0]
    return {"resource_id": row[0], "resource_name": row[1]}


@pytest.fixture
def brain():
    # Function-scoped: conftest._isolate_db_env resets the audit-bus sink before
    # every test, so the sink must be (re)configured per test.
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _inject_granted_request(brain, request_id: str, real_resource: dict, **overrides) -> None:
    """注入一个已授权（status=granted）的申请，让撤回 / 暂停有真实主体可操作。

    Action D：申请单一事实源在 application_record——直接 upsert 注入（幂等覆盖）。"""
    brain._state_store.database_store.application_repo.upsert_from_request({
        "id": request_id,
        "status": "granted",
        "applicant": "U_OP_H4",
        "applicantDept": "部门A_公安",
        "resourceId": real_resource["resource_id"],
        "resourceName": real_resource["resource_name"],
        "purpose": "H4 撤回回归",
        "grant": {},
        "timeline": [],
        **overrides,
    }, tenant_id=TENANT)


def _record_card(brain, request_id: str) -> dict:
    rec = brain._state_store.database_store.application_repo.get_record(request_id, tenant_id=TENANT)
    assert rec is not None, f"application_record {request_id} 应存在"
    card = dict(rec.payload_json or {})
    card["status"] = rec.status
    return card


def _invoke(brain, skill_id: str, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_BUSIAUDIT")
    out = invoke_trusted(brain, skill_id, payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# 正向：撤回 / 暂停真实存在的授权 → 状态真落库
# ──────────────────────────────────────────────────────────────────────


def test_revoke_existing_grant_marks_revoked(brain, real_resource):
    _inject_granted_request(brain, "REQ-H4-REV", real_resource)
    result = _invoke(brain, "application.grant.revoke", {
        "request_id": "REQ-H4-REV",
        "role": "ROLE_BUSIAUDIT",
        "confirmed": True,
        "reason": "近期对该资源调用合规风险高",
    })
    assert result["revoked"] is True
    target = _record_card(brain, "REQ-H4-REV")
    assert target["status"] == "revoked"
    assert target["grant"]["revoked"] is True


def test_suspend_existing_grant_marks_suspended(brain, real_resource):
    _inject_granted_request(brain, "REQ-H4-SUS", real_resource)
    result = _invoke(brain, "application.grant.suspend", {
        "request_id": "REQ-H4-SUS",
        "role": "ROLE_BUSIAUDIT",
        "confirmed": True,
        "reason": "临时暂停以核实使用边界",
    })
    assert result["suspended"] is True
    target = _record_card(brain, "REQ-H4-SUS")
    assert target["grant"]["suspended"] is True
    # R-001 回归：暂停必须落到 status（持久化的真值源），否则只置 grant 子字典是
    # 假成功——返回 ok 但 PersistMiddleware 不回写 grant、刷新即消失。
    assert target["status"] == "suspended"


# ──────────────────────────────────────────────────────────────────────
# H4 核心：撤回 / 暂停不存在的授权 → 报错，不假成功
# ──────────────────────────────────────────────────────────────────────


def test_revoke_missing_grant_raises_not_found(brain, real_resource):
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": "REQ-DOES-NOT-EXIST-999",
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
        })


def test_suspend_missing_grant_raises_not_found(brain, real_resource):
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        _invoke(brain, "application.grant.suspend", {
            "request_id": "REQ-DOES-NOT-EXIST-998",
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
        })


def test_revoke_non_req_prefixed_id_no_longer_fake_ok(brain, real_resource):
    """H4 旧 bug 的精确回归：非 REQ- 前缀的 id 旧实现 request=None → 返回 {"revoked":True}
    假成功。现应抛 NotFoundError（该 id 不存在）。"""
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": "DT-some-delivery-task",
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
        })


def test_revoke_blank_id_raises_invalid_state(brain, real_resource):
    from zw_brain.domain.errors import InvalidStateError

    with pytest.raises(InvalidStateError):
        _invoke(brain, "application.grant.revoke", {
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
        })


# ──────────────────────────────────────────────────────────────────────
# 撤回不可逆：已撤回再撤回 → 报错
# ──────────────────────────────────────────────────────────────────────


def test_revoke_already_revoked_raises_invalid_state(brain, real_resource):
    _inject_granted_request(brain, "REQ-H4-TWICE", real_resource)
    _invoke(brain, "application.grant.revoke", {
        "request_id": "REQ-H4-TWICE", "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    from zw_brain.domain.errors import InvalidStateError

    with pytest.raises(InvalidStateError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": "REQ-H4-TWICE", "role": "ROLE_BUSIAUDIT", "confirmed": True,
        })


# ──────────────────────────────────────────────────────────────────────
# R-004：真实库申请（M0 导入、hex id，**不在内存快照里**）撤回/暂停必须真落库。
# 这是本地走查逮到、而旧测试（只 _inject 内存）结构性漏掉的一类：旧实现对真实库申请
# find_by_id 拿到的是 DB 派生副本，改动不入库 → 返回 ok 却 DB 不变（假成功），不可逆
# 守卫永不触发可无限撤回。守住「真实记录」路径，不再只测演示单。
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def real_db_request() -> str:
    """从真实库取一条 hex-id（非 REQ- 演示）、处于可操作态的申请 application_code。"""
    rows = _pg_read(
        "SELECT application_code FROM application_record "
        "WHERE tenant_id=%s AND application_code NOT LIKE 'REQ-%%' "
        "AND status IN ('approved','effective','in_delivery','granted','suspended') "
        "ORDER BY application_code LIMIT 1",
        (TENANT,),
    )
    assert rows, "真实库无可操作态的非演示申请，无法守 R-004"
    return str(rows[0][0])


def _db_status(application_code: str) -> str | None:
    rows = _pg_read(
        "SELECT status FROM application_record WHERE tenant_id=%s AND application_code=%s",
        (TENANT, application_code),
    )
    return rows[0][0] if rows else None


def test_revoke_real_db_request_persists_and_guards(brain, real_db_request):
    """真实库申请撤回 → DB.status 真变 revoked + 再撤回触发不可逆守卫（非假成功）。"""
    from zw_brain.domain.errors import InvalidStateError

    assert _db_status(real_db_request) != "revoked"
    result = _invoke(brain, "application.grant.revoke", {
        "request_id": real_db_request, "role": "ROLE_BUSIAUDIT", "confirmed": True,
    })
    assert result["revoked"] is True
    # 真落库：DB 现状必须是 revoked（旧 bug 会停在原状态）。
    assert _db_status(real_db_request) == "revoked"
    # 不可逆守卫据 DB 现状判定 → 二次撤回报错，而非二次假成功。
    with pytest.raises(InvalidStateError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": real_db_request, "role": "ROLE_BUSIAUDIT", "confirmed": True,
        })


# ──────────────────────────────────────────────────────────────────────
# 决策 A（已签字）：撤回 = 业务运营员合规 + 申请人本人主动放弃（owner 校验）；MANAGER 收回权限。
# ──────────────────────────────────────────────────────────────────────


def test_manager_can_no_longer_suspend_effective_policy():
    """决策 A：暂停仅业务运营员。MANAGER 经 ROLE_HIERARCHY 只继承 OPERATER（非 BUSIAUDIT），
    故 suspend={BUSIAUDIT} 的有效权限不含 MANAGER（REST 入口据此 403）。"""
    from zw_brain.domain import policy

    assert policy.PERMISSION_ROLES["application.grant.suspend.execute"] == {"ROLE_BUSIAUDIT"}
    assert "application.grant.suspend.execute" not in policy.permissions_for_role("ROLE_ORGAN_MANAGER")
    assert "application.grant.suspend.execute" in policy.permissions_for_role("ROLE_BUSIAUDIT")


def test_manager_cannot_compliance_revoke_handler_guard(brain, real_resource):
    """决策 A + SPEC 负向：MANAGER 经 hierarchy 继承 OPERATER 命中 revoke 权限位，但 handler
    显式收口合规撤回仅 BUSIAUDIT → MANAGER 撤回被拒（access_denied），不直接撤回。"""
    from zw_brain.domain.errors import AccessDeniedError

    _inject_granted_request(brain, "REQ-A-MGR", real_resource)
    with pytest.raises(AccessDeniedError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": "REQ-A-MGR", "role": "ROLE_ORGAN_MANAGER", "confirmed": True,
        })


def test_applicant_self_withdraw_own_grant(brain, real_resource):
    """申请人本人主动放弃自己的申请 → 成功 + initiated_by=applicant（owner 校验通过）。"""
    from zw_brain.domain import policy

    operater_actor = policy.actor_for_role("ROLE_ORGAN_OPERATER")
    # 把 applicant 设为操作员 actor（request.create 时即 applicant=actor）→ owner 校验通过。
    _inject_granted_request(brain, "REQ-A-SELF", real_resource, applicant=operater_actor)
    result = _invoke(brain, "application.grant.revoke", {
        "request_id": "REQ-A-SELF", "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
    })
    assert result["revoked"] is True
    assert result["initiated_by"] == "applicant"
    target = _record_card(brain, "REQ-A-SELF")
    assert target["status"] == "revoked"


def test_applicant_cannot_withdraw_others_grant(brain, real_resource):
    """SPEC 负向：申请人不能放弃他人的授权（applicant != actor）→ not_owner_of_application。"""
    from zw_brain.domain.errors import AccessDeniedError

    _inject_granted_request(brain, "REQ-A-OTHER", real_resource)  # applicant=U_OP_H4 ≠ 操作员 actor
    with pytest.raises(AccessDeniedError):
        _invoke(brain, "application.grant.revoke", {
            "request_id": "REQ-A-OTHER", "role": "ROLE_ORGAN_OPERATER", "confirmed": True,
        })
