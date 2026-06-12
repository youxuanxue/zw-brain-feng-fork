"""J2 资源挂接 — 库表/文件物化资源全状态机 + 诚实校验 + 边界守卫。

补 Wave 1 挂数旅程缺的一半：库表/文件挂接（提交侧）。复用 kind-agnostic 资产状态机
（submit_review→review→publish），只补创建 + 诚实结构校验。
"""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.j1.resource_mount import FIELD_METADATA_SNAPSHOT_KEYS
from zw_brain.domain.errors import AccessDeniedError, InvalidStateError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
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


# ── B2 字段级元数据 10 列（债 b2-field-metadata-10col，方案 A：注册写字段快照，
#       与 legacy 导入同源同形，详情 metadata.schema.query 读路径零改动）──────────

REPO_ROOT = Path(__file__).resolve().parent.parent

# 全 10 列逐项填写（对标旧 dc_resource_table_column；验收口径 = 详情逐列回显一致，不抽样）。
_FIELD_COLUMNS = [
    {
        "column_name": "xm",
        "comment": "姓名",
        "catalog_item_id": "目录信息项-姓名",
        "format": "C",
        "length": "50",
        "is_pk": 1,
        "is_null": 0,
        "is_up_id": 1,
        "is_up_time": 0,
        "meta_standard": "GB/T 2261.1",
        "data_dict": "姓名代码表",
    },
    {
        "column_name": "update_time",
        "comment": "更新时间",
        "catalog_item_id": None,
        "format": "T",
        "length": "",
        "is_pk": 0,
        "is_null": 1,
        "is_up_id": 0,
        "is_up_time": 1,
        "meta_standard": None,
        "data_dict": None,
    },
]


def _schema_items(brain: BrainService, resource_code: str) -> list[dict]:
    got = invoke_trusted(brain, "metadata.schema.query", {"resource_code": resource_code}, role=MANAGER)
    return got["items"]


def test_table_field_columns_write_snapshot_roundtrip(brain: BrainService) -> None:
    """注册逐列填 10 列 → 字段快照逐键同名落库 → 读路径逐列读回与输入一致（不抽样）。"""
    payload = {**_table_payload("res-tbl-10col"), "field_columns": _FIELD_COLUMNS}
    payload.pop("field_mappings", None)
    res = invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    assert res["result"]["mapping_ready"] is True
    assert res["result"]["field_metadata_count"] == 2

    items = _schema_items(brain, "res-tbl-10col")
    assert len(items) == 2
    by_name = {item["schema_json"]["column_name"]: item["schema_json"] for item in items}
    # 逐列全比（10 列全部），写读键同名：输入什么读回什么（空文本归 None，不造假）。
    xm = by_name["xm"]
    for key in FIELD_METADATA_SNAPSHOT_KEYS:
        assert xm[key] == _FIELD_COLUMNS[0][key], f"列 {key} 写读漂移"
    ut = by_name["update_time"]
    assert ut["comment"] == "更新时间"
    assert ut["catalog_item_id"] is None  # 未填 → None（详情端「—」），不捏造
    assert ut["length"] is None  # 空串归 None
    assert (ut["is_pk"], ut["is_null"], ut["is_up_id"], ut["is_up_time"]) == (0, 1, 0, 1)
    # order_id 按行序（读端排序键），与 legacy 快照同形。
    assert (xm["order_id"], ut["order_id"]) == (1, 2)

    # summary 同步承载：字段名清单（与 legacy 导入 summary.fields 同形）+ 派生映射。
    asset = invoke_trusted(brain, "resource.asset.query", {"resource_code": "res-tbl-10col"}, role=OPERATER)["items"][0]
    assert asset["summary_json"]["fields"] == ["xm", "update_time"]
    assert asset["summary_json"]["field_mappings"] == [{"source": "xm", "target": "目录信息项-姓名"}]
    # 全链状态机不受影响：提交→审核→发布照走。
    invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": "res-tbl-10col", "confirmed": True}, role=OPERATER)
    invoke_trusted(brain, "resource.asset.review", {"resource_code": "res-tbl-10col", "decision": "approve", "confirmed": True}, role=MANAGER)
    out = invoke_trusted(brain, "resource.asset.publish", {"resource_code": "res-tbl-10col", "confirmed": True}, role=BUSIAUDIT)
    assert out["result"]["lifecycle_status"] == "active"


def test_field_columns_reprepare_overwrites_not_duplicates(brain: BrainService) -> None:
    """覆盖式 upsert：re-prepare 不产生重复行；改列后读回 = 最新一版。"""
    payload = {**_table_payload("res-tbl-rewrite"), "field_columns": _FIELD_COLUMNS}
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    changed = [{**_FIELD_COLUMNS[0], "comment": "姓名（修订）"}]
    invoke_trusted(brain, "resource.mount.table.prepare", {**payload, "field_columns": changed}, role=OPERATER)
    items = _schema_items(brain, "res-tbl-rewrite")
    assert len(items) == 1  # 第二版只有 1 列 → 旧 2 行被覆盖，无残留
    assert items[0]["schema_json"]["comment"] == "姓名（修订）"


def test_register_snapshots_never_touch_legacy(brain: BrainService) -> None:
    """存量不回归：同资源已有 legacy 导入快照时，注册覆盖写只动 register 来源行。"""
    repo = MetadataEvidenceRepository()
    repo.upsert_schema_snapshot(
        {
            "snapshot_ref": "res-tbl-mixed:db_meta_column:legacy-1",
            "resource_code": "res-tbl-mixed",
            "binding_code": "legacy-binding",
            "schema_json": {"column_name": "legacy_col", "format": "varchar", "is_pk": 0},
            "source_ref": "dsp:db_meta_column:legacy-1",
        },
        tenant_id=TENANT,
    )
    payload = {**_table_payload("res-tbl-mixed"), "field_columns": _FIELD_COLUMNS}
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)  # 再来一遍（幂等）
    items = _schema_items(brain, "res-tbl-mixed")
    refs = {item["snapshot_ref"] for item in items}
    assert "res-tbl-mixed:db_meta_column:legacy-1" in refs  # legacy 行原样保留
    assert len(items) == 3  # legacy 1 + register 2（无重复）


def test_field_columns_explicit_empty_clears_absent_key_keeps(brain: BrainService) -> None:
    """显式空列表 = 本次登记的全量真相（清空 register 旧行）；键缺省（legacy 调用方）不触碰快照。"""
    payload = {**_table_payload("res-tbl-clear"), "field_columns": _FIELD_COLUMNS}
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    assert len(_schema_items(brain, "res-tbl-clear")) == 2
    legacy_payload = _table_payload("res-tbl-clear")
    legacy_payload.pop("field_columns", None)
    invoke_trusted(brain, "resource.mount.table.prepare", legacy_payload, role=OPERATER)
    assert len(_schema_items(brain, "res-tbl-clear")) == 2  # 键缺省 → 原样
    invoke_trusted(brain, "resource.mount.table.prepare", {**legacy_payload, "field_columns": []}, role=OPERATER)
    assert _schema_items(brain, "res-tbl-clear") == []  # 显式清空 → 不残留陈旧字段模型


def test_register_snapshot_ref_capped_and_unique(brain: BrainService) -> None:
    """超长列名（用户输入无上限）→ snapshot_ref 截断 + 短哈希，守 String(128) 契约且保唯一。"""
    long_a = "超长字段名" * 40  # 200 字
    long_b = long_a[:-1] + "异"  # 同前缀、尾部不同
    cols = [
        {"column_name": long_a, "format": "varchar"},
        {"column_name": long_b, "format": "varchar"},
        # 与首列完全重名的超长列：去重必须发生在截断之后，否则两行截成同一 ref 撞 UNIQUE。
        {"column_name": long_a, "format": "text"},
    ]
    payload = {**_table_payload("res-tbl-longref"), "field_columns": cols}
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    items = _schema_items(brain, "res-tbl-longref")
    refs = [item["snapshot_ref"] for item in items]
    assert len(refs) == 3
    assert all(len(ref) <= 128 for ref in refs), f"snapshot_ref 越界 String(128): {[len(r) for r in refs]}"
    assert len(set(refs)) == 3, "同前缀/重名超长列名截断后必须仍唯一（哈希后缀 + 截断后去重）"
    # 覆盖式重写不撞 UNIQUE（确定性：同输入同 ref）
    invoke_trusted(brain, "resource.mount.table.prepare", payload, role=OPERATER)
    assert sorted(item["snapshot_ref"] for item in _schema_items(brain, "res-tbl-longref")) == sorted(refs)


def test_file_field_columns_optional_path(brain: BrainService) -> None:
    """文件资源字段登记可选：给了同走快照通路；不给零快照、提交不受影响。"""
    with_fields = {**_file_payload("res-file-cols"), "field_columns": _FIELD_COLUMNS}
    res = invoke_trusted(brain, "resource.mount.file.prepare", with_fields, role=OPERATER)
    assert res["result"]["field_metadata_count"] == 2
    assert len(_schema_items(brain, "res-file-cols")) == 2

    bare = invoke_trusted(brain, "resource.mount.file.prepare", _file_payload("res-file-nocols"), role=OPERATER)
    assert bare["result"]["field_metadata_count"] == 0
    assert _schema_items(brain, "res-file-nocols") == []
    invoke_trusted(brain, "resource.asset.submit_review", {"resource_code": "res-file-nocols", "confirmed": True}, role=OPERATER)


def test_legacy_two_col_mapping_payload_unchanged(brain: BrainService) -> None:
    """旧 field_mappings API surface 不破坏：就绪门照旧、不写字段快照（零行为漂移）。"""
    res = invoke_trusted(brain, "resource.mount.table.prepare", _table_payload("res-tbl-compat"), role=OPERATER)
    assert res["result"]["mapping_ready"] is True
    assert res["result"]["field_metadata_count"] == 0
    assert _schema_items(brain, "res-tbl-compat") == []


# ── 写读键对齐（#251 share_type 键漂移教训的机械兜底；任一端单改键名即红）────────

_TS_FIELD_DICT = REPO_ROOT / "zw-brain-web" / "src" / "lib" / "catalogCompileFields.ts"
_TS_SCHEMA_READER = REPO_ROOT / "zw-brain-web" / "src" / "composables" / "useResourceSchema.ts"


def test_field_metadata_write_read_keys_aligned() -> None:
    """后端写端字典 = 前端写端 payload 键 ⊆ 前端读端消费键，三方逐键同名。

    参照 #254 test_frontend_backend_required_dict_aligned 模式：无生成物同步机制的
    两端字典靠本测试机械钉死（写读键漂移 = 字段录入后在详情「消失」，#251 同病）。
    """
    backend_keys = set(FIELD_METADATA_SNAPSHOT_KEYS)

    # 前端写端：resourceFieldColumnToPayload 产出的 snake 键。
    ts_text = _TS_FIELD_DICT.read_text(encoding="utf-8")
    body = ts_text.split("export function resourceFieldColumnToPayload", 1)[1].split("\n}\n", 1)[0]
    frontend_write_keys = set(re.findall(r"^\s{4}([a-z_]+):", body, re.M))
    assert frontend_write_keys == backend_keys, (
        f"前端写端键 ≠ 后端字典：仅前端 {sorted(frontend_write_keys - backend_keys)} / "
        f"仅后端 {sorted(backend_keys - frontend_write_keys)}"
    )

    # 前端读端：normalizeSchemaColumns 消费的 schema_json 键须覆盖全部写端键。
    reader_text = _TS_SCHEMA_READER.read_text(encoding="utf-8")
    frontend_read_keys = set(re.findall(r"\brec\.([a-z_]+)", reader_text))
    missing = backend_keys - frontend_read_keys
    assert not missing, f"读端 normalizeSchemaColumns 未消费写端键：{sorted(missing)}"


def test_b2_field_metadata_debt_closed() -> None:
    """债 b2-field-metadata-10col 现算关闭 + 回潮守卫：10 列承载缩水即红。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_b2_field_metadata_columns", REPO_ROOT / "scripts" / "check_b2_field_metadata_columns.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.covered_dimension_count() == 10
    assert mod.field_metadata_debt_open() is False


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
