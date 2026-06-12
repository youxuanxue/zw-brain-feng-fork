"""J2 资源挂接 — 库表/文件物化资源全状态机 + 诚实校验 + 边界守卫。

补 Wave 1 挂数旅程缺的一半：库表/文件挂接（提交侧）。复用 kind-agnostic 资产状态机
（submit_review→review→publish），只补创建 + 诚实结构校验。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.errors import AccessDeniedError, InvalidStateError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
ORG = "11370000MB284651XL"
ORG_OTHER = "360002222211"
CAT = "cat-mount-target"
CAT_OTHER = "cat-other-org"

OPERATER = "ROLE_ORGAN_OPERATER"
BUSIAUDIT = "ROLE_BUSIAUDIT"
MANAGER = "ROLE_ORGAN_MANAGER"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "resource_mount.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_catalogs() -> None:
    repo = CatalogRepository()
    repo.upsert_from_resource(
        {"id": CAT, "name": "学生课程信息", "status": "active", "provider": ORG}, tenant_id=TENANT
    )
    repo.upsert_from_resource(
        {"id": CAT_OTHER, "name": "别家目录", "status": "active", "provider": ORG_OTHER}, tenant_id=TENANT
    )


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    _seed_catalogs()
    return BrainService(state_store=StateStore(database_store=ds))


def _table_payload(resource_code: str, *, mappings=True, owner=ORG, catalog=CAT) -> dict:
    return {
        "resource_code": resource_code,
        "catalog_code": catalog,
        "title": f"{resource_code} 库表",
        "owner_org_id": owner,
        "table_name": "t_student",
        "connection": {"host": "10.0.0.1", "database": "edu", "password": "should-be-redacted"},
        "field_mappings": [{"source": "name", "target": "stu_name"}] if mappings else [],
        "confirmed": True,
    }


def _file_payload(resource_code: str, *, owner=ORG, catalog=CAT) -> dict:
    return {
        "resource_code": resource_code,
        "catalog_code": catalog,
        "title": f"{resource_code} 文件",
        "owner_org_id": owner,
        "file_name": "students.csv",
        "access_path": "/data/students.csv",
        "content_hash": "sha256:abc123",
        "update_frequency": "daily",
        "confirmed": True,
    }


# B2 资源注册业务字段（对标旧平台资源「基本信息」标签页：库表/文件资源详情对标截图）。
_BUSINESS_FIELDS = {
    "shared_type": "2",
    "shared_condition": "按授权范围共享",
    "open_type": "3",
    "open_condition": "不可对社会开放",
    "resource_desc": "养老保险信息",
    "source_system": "养老保险建模系统",
    "resource_version": "V2.0",
    "tech_contact": "王四",
    "contact_phone": "17890786758",
}


# ── 库表挂接 ────────────────────────────────────────────────────────────────

def test_table_prepare_creates_draft_asset(brain: BrainService) -> None:
    res = invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-1"), role=OPERATER)
    assert res["result"]["mapping_ready"] is True
    assert res["result"]["connectivity"] == "not_probed"  # 诚实：不伪造连接成功
    # 落库 resource_kind=table + 去敏连接（password 不入库）
    got = invoke_trusted(brain, "resource.asset.query", {"resource_code": "res-tbl-1"}, role=OPERATER)
    asset = got["items"][0]
    assert asset["resource_kind"] == "table"
    assert "password" not in asset["summary_json"].get("connection_ref", {})


def test_table_full_state_machine_to_active(brain: BrainService) -> None:
    invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-2"), role=OPERATER)
    invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": "res-tbl-2", "confirmed": True}, role=OPERATER)
    invoke_trusted(brain, "resource.asset.review", {"resource_code": "res-tbl-2", "decision": "approve", "confirmed": True}, role=MANAGER)
    res = invoke_trusted(brain, "resource.asset.publish", {"resource_code": "res-tbl-2", "confirmed": True}, role=MANAGER)
    assert res["result"]["lifecycle_status"] == "active"


def test_table_missing_mappings_blocks_submit_review(brain: BrainService) -> None:
    res = invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-3", mappings=False), role=OPERATER)
    assert res["result"]["mapping_ready"] is False  # 允许存草稿
    with pytest.raises(InvalidStateError):  # 但阻断提交复核
        invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": "res-tbl-3", "confirmed": True}, role=OPERATER)


# ── 文件挂接 ────────────────────────────────────────────────────────────────

def test_file_prepare_captures_fingerprint(brain: BrainService) -> None:
    res = invoke_trusted(brain, "resource.mount.file.prepare", _file_payload("res-file-1"), role=OPERATER)
    assert res["result"]["content_fingerprint"] == "sha256:abc123"
    got = invoke_trusted(brain, "resource.asset.query", {"resource_code": "res-file-1"}, role=OPERATER)
    assert got["items"][0]["resource_kind"] == "file"


def test_file_full_state_machine_to_active(brain: BrainService) -> None:
    invoke_trusted(brain, "resource.mount.file.prepare", _file_payload("res-file-2"), role=OPERATER)
    invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": "res-file-2", "confirmed": True}, role=OPERATER)
    invoke_trusted(brain, "resource.asset.review", {"resource_code": "res-file-2", "decision": "approve", "confirmed": True}, role=MANAGER)
    res = invoke_trusted(brain, "resource.asset.publish", {"resource_code": "res-file-2", "confirmed": True}, role=MANAGER)
    assert res["result"]["lifecycle_status"] == "active"


# ── B2 资源注册业务字段对齐（共享/开放 → access_policy；描述/来源/联系人 → summary；
#       文件 格式/大小/存储类型 → 文件分型 binding，喂详情「文件信息」标签页）──────────

def test_table_business_fields_land_in_policy_and_summary(brain: BrainService) -> None:
    payload = {**_table_payload("res-tbl-biz"), **_BUSINESS_FIELDS}
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    asset = invoke_trusted(brain, "resource.asset.query", {"resource_code": "res-tbl-biz"}, role=OPERATER)["items"][0]
    policy = asset["access_policy_json"]
    # 存储键 = share_type / share_condition（0611 断点 C：写读键统一，与 legacy seed 及
    # 发现/共享方式回源读端 discovery_snapshot_projection 同键；payload 入参键不变）。
    assert policy["share_type"] == "2"
    assert policy["open_type"] == "3"
    assert policy["share_condition"] == "按授权范围共享"
    assert "shared_type" not in policy  # 漂移键禁回潮（读端只认 share_type）
    summary = asset["summary_json"]
    assert summary["source_system"] == "养老保险建模系统"
    assert summary["resource_version"] == "V2.0"
    assert summary["tech_contact"] == "王四"
    assert summary["resource_desc"] == "养老保险信息"


def test_file_format_size_store_feed_typed_detail(brain: BrainService) -> None:
    """文件采集端补 格式/大小/存储类型 → 详情端「文件信息」标签页有值（不再永远空态）。"""
    payload = {
        **_file_payload("res-file-typed"),
        **_BUSINESS_FIELDS,
        "file_format": "docx",
        "file_size": "17869",
        "file_store_type": "centerStore",
    }
    invoke_trusted(brain, "resource.mount.file.prepare", payload, role=OPERATER)
    # 走查 catalog.resource_view（聚焦该资源）应投影出 typedDetail 文件信息块且字段有值。
    out = invoke_trusted(brain, "catalog.resource_view", {"resource_id": "res-file-typed"}, role=OPERATER)
    detail = out["result"] if isinstance(out, dict) and "result" in out and "audit_id" in out else out
    typed = detail["typedDetail"]
    assert typed["kind"] == "file"
    rows = {r["label"]: r["value"] for r in typed["sections"][0]["rows"]}
    assert rows["文件名称"] == "students.csv"
    assert rows["文件类型"] == "docx"
    assert rows["文件大小"] == "17.5 KB"  # 17869 字节 → 人类可读
    assert rows["存储类型"] == "中心库存储"


# ── 边界守卫 ────────────────────────────────────────────────────────────────

def test_cross_org_catalog_rejected(brain: BrainService) -> None:
    """资源 owner_org 与目标目录 owner_org 不一致 → 拒（跨 org）。"""
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain, "resource.mount.table.prepare",
            _table_payload("res-tbl-x", owner=ORG, catalog=CAT_OTHER), role=OPERATER,
        )


def test_omitted_owner_to_owned_catalog_rejected(brain: BrainService) -> None:
    """省略 owner_org 也不能绕过跨 org 校验：目录有 owner 时未声明归属一律拒（R-001 堵漏）。"""
    payload = _table_payload("res-tbl-noowner", owner=ORG, catalog=CAT)
    payload.pop("owner_org_id", None)  # 省略归属
    with pytest.raises(AccessDeniedError):
        invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)


def test_owner_immutable_after_mount(brain: BrainService) -> None:
    invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-4", owner=ORG), role=OPERATER)
    with pytest.raises(InvalidStateError):
        invoke_trusted(
            brain, "resource.mount.table.prepare",
            _table_payload("res-tbl-4", owner="SOME-OTHER-ORG", catalog=CAT), role=OPERATER,
        )


def test_multi_materialization_same_catalog(brain: BrainService) -> None:
    """同目录可挂多形态资源（table + file）。"""
    invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-multi-tbl"), role=OPERATER)
    invoke_trusted(brain, "resource.mount.file.prepare", _file_payload("res-multi-file"), role=OPERATER)
    got = invoke_trusted(brain, "catalog.resource.list", {"catalog_code": CAT}, role=OPERATER)
    kinds = {it["resource_code"] for it in got["items"]}
    assert {"res-multi-tbl", "res-multi-file"} <= kinds


def test_operater_only_for_mount(brain: BrainService) -> None:
    """挂接提交侧仅 OPERATER；BUSIAUDIT 不能 prepare。"""
    with pytest.raises(AccessDeniedError):
        invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-deny"), role=BUSIAUDIT)


# ── api 路径不受 mapping 门影响（回归）────────────────────────────────────────

def test_api_submit_review_unaffected_by_mapping_gate(brain: BrainService) -> None:
    """api 资源无 mapping_ready 要求，submit_review 不被库表门拦。"""
    invoke_trusted(brain, "resource.api.register", {
        "resource_code": "res-api-1", "title": "API 资源", "catalog_code": CAT,
        "owner_org_id": ORG, "confirmed": True,
    }, role=MANAGER)
    # 不抛（api kind 跳过库表映射门）
    invoke_trusted(brain, "resource.api.submit_review", {"resource_code": "res-api-1", "confirmed": True}, role=MANAGER)
