"""部门数据隔离 端到端（两 actor 走全 system.snapshot 路径）——核心证据。

证明读路径**真按调用者机构收口**（非仅 projection 单测）：两个不同部门的管理员登录后，
``system.snapshot`` 返回的 provider.catalogs / requests **不同**、各为自机构子集；全局角色
（业务运营员）见全量。这正是用户最初反馈缺失的隔离——「所有用户登录后看到的资源/目录都一样」。

走 ``invoke_trusted``（build_trusted_skill_payload trust-stamp 链路，与 REST/MCP/CLI BFF
入口同路径），actor_snapshot 携不同 current_org_code 模拟两个部门会话。这是计划里「后端双
actor 断言」——真·双账号浏览器测受 dev-bypass 单 org 夹具限制（记债），此断言等价覆盖隔离保证。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
ORG_A = "11370000MB284651XL"   # A 部门（管理员甲所属）
ORG_B = "36010000876"          # B 部门（管理员乙所属）
MANAGER = "ROLE_ORGAN_MANAGER"
BUSIAUDIT = "ROLE_BUSIAUDIT"   # 全局口径角色（业务运营员）


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dept_e2e.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed() -> None:
    gov = GovernanceProjectionRepository()
    gov.upsert_org({"org_code": ORG_A, "org_name": "省大数据局"}, tenant_id=TENANT)
    gov.upsert_org({"org_code": ORG_B, "org_name": "省人力资源和社会保障厅"}, tenant_id=TENANT)
    cat = CatalogRepository()
    # 两部门各持目录（owner_org_id 由 provider 落）。
    cat.upsert_from_resource({"id": "cat-a-1", "name": "A部门目录甲", "status": "active", "provider": ORG_A}, tenant_id=TENANT)
    cat.upsert_from_resource({"id": "cat-a-2", "name": "A部门目录乙", "status": "active", "provider": ORG_A}, tenant_id=TENANT)
    cat.upsert_from_resource({"id": "cat-b-1", "name": "B部门目录甲", "status": "active", "provider": ORG_B}, tenant_id=TENANT)
    # 两部门各一张申请（applicant_org 由 applicantDept 落）——验 requests 也按机构隔离。
    app = ApplicationRepository()
    app.upsert_from_request(
        {"id": "APP-A", "status": "submitted", "applicant": "actor-a", "applicantDept": ORG_A,
         "kind": "apply", "resource_name": "A申请", "resourceId": "res-app-a"},
        tenant_id=TENANT,
    )
    app.upsert_from_request(
        {"id": "APP-B", "status": "submitted", "applicant": "actor-b", "applicantDept": ORG_B,
         "kind": "apply", "resource_name": "B申请", "resourceId": "res-app-b"},
        tenant_id=TENANT,
    )
    # 两部门各一张交付任务（requestId 映各自申请，运行时卡形态：有 requestId、无 legacy kind）——
    # 验 delivery_tasks 随申请单按机构隔离（#294 集成期遗漏补口）。
    dlv = DeliveryRepository()
    dlv.upsert_from_delivery(
        {"id": "DLV-A", "requestId": "APP-A", "status": "completed", "channel": "内部修复"},
        tenant_id=TENANT,
    )
    dlv.upsert_from_delivery(
        {"id": "DLV-B", "requestId": "APP-B", "status": "completed", "channel": "内部修复"},
        tenant_id=TENANT,
    )


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    _seed()
    return BrainService(state_store=StateStore(database_store=ds))


def _snapshot_for(brain: BrainService, role: str, org: str) -> dict:
    return invoke_trusted(
        brain, "system.snapshot", {"role": role}, role=role,
        snapshot=actor_snapshot(role, org_code=org),
    )


def _catalog_ids(snap: dict) -> set[str]:
    return {str(c.get("id")) for c in snap.get("provider", {}).get("catalogs", [])}


def _request_ids(snap: dict) -> set[str]:
    return {str(r.get("id")) for r in snap.get("requests", [])}


def _delivery_request_ids(snap: dict) -> set[str]:
    return {str(t.get("requestId")) for t in snap.get("delivery_tasks", [])}


# ── 核心证据：两部门管理员看到的目录不同、各为自机构子集 ──────────────────────────
def test_two_dept_managers_see_disjoint_catalogs(brain: BrainService) -> None:
    a = _catalog_ids(_snapshot_for(brain, MANAGER, ORG_A))
    b = _catalog_ids(_snapshot_for(brain, MANAGER, ORG_B))
    assert {"cat-a-1", "cat-a-2"} <= a, "A 管理员见本机构两目录"
    assert "cat-b-1" not in a, "A 管理员**不**见 B 部门目录（隔离）"
    assert "cat-b-1" in b, "B 管理员见本机构目录"
    assert not ({"cat-a-1", "cat-a-2"} & b), "B 管理员**不**见 A 部门目录（隔离）"
    assert a != b, "两部门管理员看到的目录集不同——正是用户最初反馈缺失的部门隔离"


def test_two_dept_managers_see_disjoint_requests(brain: BrainService) -> None:
    a = _request_ids(_snapshot_for(brain, MANAGER, ORG_A))
    b = _request_ids(_snapshot_for(brain, MANAGER, ORG_B))
    assert "APP-A" in a, "A 部门发起的申请对 A 管理员可见"
    assert "APP-A" not in b, "A 部门的申请对 B 管理员不可见（applicant_org 隔离）"


def test_two_dept_managers_see_disjoint_delivery_tasks(brain: BrainService) -> None:
    # #294 集成期遗漏补口：交付任务随申请单按机构隔离（此前 delivery_tasks 全量泄漏给部门角色）。
    a = _delivery_request_ids(_snapshot_for(brain, MANAGER, ORG_A))
    b = _delivery_request_ids(_snapshot_for(brain, MANAGER, ORG_B))
    assert "APP-A" in a, "A 部门申请的交付任务对 A 管理员可见"
    assert "APP-B" not in a, "B 部门的交付任务对 A 管理员**不**可见（随申请单隔离）"
    assert "APP-B" in b, "B 部门申请的交付任务对 B 管理员可见"
    assert "APP-A" not in b, "A 部门的交付任务对 B 管理员**不**可见（随申请单隔离）"


# ── 全局角色（业务运营员）见全量——发现/全局口径不被部门收口 ─────────────────────
def test_global_role_sees_all_catalogs(brain: BrainService) -> None:
    ids = _catalog_ids(_snapshot_for(brain, BUSIAUDIT, ORG_A))
    assert {"cat-a-1", "cat-a-2", "cat-b-1"} <= ids, "业务运营员（全局口径）见全部门目录"
