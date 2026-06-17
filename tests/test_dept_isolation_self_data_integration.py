"""部门数据隔离·**真实写路径**集成测试（承 #298 / D61）——堵「seed 正确数据绕过 buggy 写路径」盲区。

既有 ``test_dept_isolation_snapshot_two_actor.py`` 走读路径，但它**直接 seed** 带正确
``applicant_org_code`` / ``owner_org_code`` 的申请记录（``ApplicationRepository.upsert_from_request``）。
那条路径证明读侧隔离 OK，但**绕过了写侧**——#298 的根因恰恰在写侧：``request.create`` 把
``applicant_org`` 钉成一个无关机构的硬编码常量（旧「市营商环境专班」/ ``11370000MB284651XL``），
于是隔离按 ``applicant_org`` 行级过滤时把申请人自己刚建的草稿也滤掉（「看不到自己刚提的单」）。

本测试**走真实 ``request.create`` handler**铸单（不预 seed 申请记录），以**非默认机构**的会话
创建草稿，再经 ``system.snapshot`` 读路径断言：

  ① 创建者本人（同会话机构同 actor）的 snapshot.requests 含该草稿且 ``mine=True``；
  ② 同机构部门管理员（不同 actor）也可见（经 request_party_in_scope 机构成员判定，非 mine）；
  ③ **别机构**会话不可见（隔离不破）；
  ④ DB 落库的 ``applicant_org_code`` == 会话机构码（**不是任何硬编码常量**）——写侧没钉死机构。

走 ``invoke_trusted``（build_trusted_skill_payload trust-stamp 链路，与 REST/MCP/CLI BFF 入口
同路径），actor_snapshot 携不同 ``current_org_code`` 模拟不同部门会话；机构经
``GovernanceProjectionRepository`` seed，刻意用**非** 11370000MB284651XL 的测试机构码。
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted

TENANT = "sd-default"

# 刻意用**非** 11370000MB284651XL（#298 旧硬编码常量）的测试机构码，证明写侧落的是会话机构、
# 不是钉死的常量。两个机构 18 位 USCC 形态、互不重叠、均无父级（下级子树恒为自身）。
ORG_SELF = "91370000TESTSELF01"   # 申请发起方（创建者所属机构）
ORG_OTHER = "91370000TESTOTHR02"  # 别部门（隔离对照——其会话不应看到 ORG_SELF 的草稿）
HARDCODED_LEGACY_ORG = "11370000MB284651XL"  # #298 旧硬编码常量，断言**绝不**等于它

OPERATER = "ROLE_ORGAN_OPERATER"  # 创建者：部门操作员（request.create 允许角色之一）
MANAGER = "ROLE_ORGAN_MANAGER"    # 部门管理员（同机构可见 / 别机构不可见对照）

_RESOURCE_ID = "res-dept-self-integration"


def _unwrap(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and "result" in result and isinstance(result["result"], dict):
        return result["result"]
    return result  # type: ignore[return-value]


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """全功能 brain（写路径需 durable audit sink + 运行时 DB），temp SQLite 隔离不污染主库。

    复用 G2 草稿流测试的真实栈搭法（runtime.get_service + 注入可申请资源），但额外 seed 两个
    **非默认**机构投影，供 caller_org_code 解析会话机构名 + 部门隔离 org_in_scope 成员判定。
    """
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("ZW_BRAIN_AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    from zw_brain.command import runtime as runtime_mod
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.audit import store as audit_store_mod

    audit_store_mod.set_default_store(None)
    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()

    service = runtime_mod.get_service()

    # seed 两个测试机构（非默认、互不重叠、无父级）。
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_SELF, "org_name": "测试·自机构局"}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_OTHER, "org_name": "测试·别机构局"}, tenant_id=TENANT)

    # 注入一条可申请的发现资源；provider/owner 落 ORG_SELF（申请方与提供方同机构→
    # 该草稿 applicant∨provider 全在 ORG_SELF 域、全在 ORG_OTHER 域外，隔离对照干净）。
    service._snapshot["discovery"]["resources"].append(
        {
            "id": _RESOURCE_ID,
            "name": "部门隔离自数据集成测试资源",
            "status": "可复用",
            "provider": ORG_SELF,
            "providerOrgId": ORG_SELF,
            "repository": {"shared_type": "1", "ownerOrgId": ORG_SELF},
        }
    )
    yield service

    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_store_mod.set_default_store(None)


def _create_draft(brain, *, role: str, org: str) -> dict[str, Any]:
    """走真实 request.create handler 铸一张草稿（会话机构 = org）。"""
    return _unwrap(
        invoke_trusted(
            brain,
            "request.create",
            {"resource_id": _RESOURCE_ID, "confirmed": True},
            role=role,
            snapshot=actor_snapshot(role, org_code=org),
        )
    )


def _snapshot_requests(brain, *, role: str, org: str) -> list[dict[str, Any]]:
    snap = invoke_trusted(
        brain,
        "system.snapshot",
        {"role": role},
        role=role,
        snapshot=actor_snapshot(role, org_code=org),
    )
    return list(snap.get("requests", []))


def _find(requests: list[dict[str, Any]], request_id: str) -> dict[str, Any] | None:
    return next((r for r in requests if str(r.get("id")) == request_id), None)


# ── ④ 写侧落库机构 = 会话机构，绝非硬编码常量（最直接的 #298 回归断言）──────────────────
def test_draft_records_session_org_not_hardcoded(brain) -> None:
    created = _create_draft(brain, role=OPERATER, org=ORG_SELF)
    rid = created["request_id"]
    store = brain._state_store.database_store
    rec = store.application_repo.get_record(rid, tenant_id=TENANT)
    assert rec is not None and rec.status == "draft", created
    payload = rec.payload_json or {}
    # 会话机构码落 applicant_org_code（隔离行级过滤快路径源）。
    assert payload.get("applicant_org_code") == ORG_SELF, payload
    # **绝不**是 #298 旧硬编码常量。
    assert payload.get("applicant_org_code") != HARDCODED_LEGACY_ORG
    assert HARDCODED_LEGACY_ORG not in (payload.get("applicantDept") or "")


# ── ① 创建者本人可见自己刚建的草稿，且 mine=True（#298「看不到自己刚提的单」根因回归）──────
def test_creator_sees_own_draft_mine_true(brain) -> None:
    created = _create_draft(brain, role=OPERATER, org=ORG_SELF)
    rid = created["request_id"]
    own = _find(_snapshot_requests(brain, role=OPERATER, org=ORG_SELF), rid)
    assert own is not None, "创建者必须能在 system.snapshot.requests 看到自己刚建的草稿（#298 根因）"
    assert own.get("mine") is True, "本人提的草稿 mine=True"


# ── ② 同机构部门管理员（不同 actor）也可见——经机构成员判定，非 mine 逃生口 ────────────────
def test_same_org_manager_sees_draft(brain) -> None:
    created = _create_draft(brain, role=OPERATER, org=ORG_SELF)
    rid = created["request_id"]
    seen = _find(_snapshot_requests(brain, role=MANAGER, org=ORG_SELF), rid)
    assert seen is not None, "同机构部门管理员应见本机构申请方/提供方参与的单（request_party_in_scope）"
    # MANAGER actor ≠ OPERATER 创建者 actor → 可见性来自机构成员判定，不是 mine。
    assert seen.get("mine") is False, "非本人提的单 mine=False（可见来自机构域，不是 mine 逃生口）"


# ── ③ 别机构会话不可见（隔离不破）──────────────────────────────────────────────────
def test_other_org_session_cannot_see_draft(brain) -> None:
    created = _create_draft(brain, role=OPERATER, org=ORG_SELF)
    rid = created["request_id"]
    other = _find(_snapshot_requests(brain, role=MANAGER, org=ORG_OTHER), rid)
    assert other is None, "别机构会话**不应**看到 ORG_SELF 的草稿——部门数据隔离不破（#298 口径不可回退）"
